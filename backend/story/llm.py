"""The only file that talks to model providers.

Everything else calls `write_text` or `write_json` with a step name and a model. We record
every call (tokens, cost, latency, errors) in the llm_calls table and, when LangSmith
tracing is switched on, as a LangSmith run.
"""

import json
import logging
import time
from dataclasses import dataclass

import anthropic
import httpx
from langsmith import get_current_run_tree, traceable
from pydantic import BaseModel
from sqlalchemy import func, select

from story import config
from story.db import session_scope
from story.models import LLMCall

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None  # OpenRouter tells us the cost directly


_anthropic_client: anthropic.Anthropic | None = None


def anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        if not config.ANTHROPIC_API_KEY:
            raise LLMError("ANTHROPIC_API_KEY is not set. Add it to backend/.env.")
        _anthropic_client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY, timeout=config.LLM_TIMEOUT_SECONDS
        )
    return _anthropic_client


def is_openrouter_model(model: str) -> bool:
    # OpenRouter model ids look like "vendor/model"; Anthropic ids never have a slash.
    return "/" in model


def direct_anthropic_model(openrouter_model: str) -> str:
    """'anthropic/claude-sonnet-5.5' -> 'claude-sonnet-5-5'. Non-Claude models get a Claude stand-in."""
    vendor, _, name = openrouter_model.partition("/")
    if vendor == "anthropic":
        return name.replace(".", "-")
    return config.DIRECT_FALLBACK_MODEL


def price_of(model: str, usage: Usage) -> float:
    if usage.cost_usd is not None:
        return usage.cost_usd
    price = config.PRICES.get(model)
    if price is None:
        return 0.0
    dollars = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    )
    return round(dollars / 1_000_000, 6)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def write_text(
    step: str,
    system: str,
    prompt: str,
    model: str,
    story_id: int = 0,
    episode: int = 0,
    max_tokens: int = 8000,
) -> str:
    """Ask a model for prose and return it."""
    return _call(
        step, system, prompt, model, story_id, episode, max_tokens, schema=None,
        langsmith_extra=_trace_labels(step, model, story_id, episode),
    )


def write_json(
    step: str,
    system: str,
    prompt: str,
    schema: type[BaseModel],
    model: str,
    story_id: int = 0,
    episode: int = 0,
    max_tokens: int = 16000,
):
    """Ask a model for JSON that matches `schema` and return the parsed object."""
    return _call(
        step, system, prompt, model, story_id, episode, max_tokens, schema=schema,
        langsmith_extra=_trace_labels(step, model, story_id, episode),
    )


def _trace_labels(step: str, model: str, story_id: int, episode: int) -> dict:
    """Name each LangSmith run after its step, and tag it so runs can be filtered by story and episode."""
    provider = "openrouter" if is_openrouter_model(model) else "anthropic"
    return {
        "name": step,
        "metadata": {
            "story_id": story_id, "episode": episode,
            "ls_provider": provider, "ls_model_name": model,
        },
        "tags": [f"story:{story_id}", f"step:{step}"],
    }


def episode_cost(story_id: int, episode: int) -> float:
    """Dollars spent so far on one episode, across every attempt."""
    with session_scope() as session:
        total = session.scalar(
            select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
                LLMCall.story_id == story_id, LLMCall.episode_number == episode
            )
        )
    return float(total or 0.0)


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


@traceable(run_type="llm", name="llm_call")
def _call(step, system, prompt, model, story_id, episode, max_tokens, schema):
    if is_openrouter_model(model) and not config.OPENROUTER_API_KEY:
        direct = direct_anthropic_model(model)
        log.warning("OPENROUTER_API_KEY missing; %s falls back to %s on the Anthropic API", step, direct)
        model = direct

    started = time.perf_counter()
    try:
        if is_openrouter_model(model):
            result, usage = _call_openrouter(system, prompt, model, max_tokens, schema)
        else:
            result, usage = _call_anthropic(system, prompt, model, max_tokens, schema)
    except Exception as error:
        _record_call(step, model, story_id, episode, Usage(), started, error=str(error))
        raise LLMError(f"{step} failed on {model}: {error}") from error

    _record_call(step, model, story_id, episode, usage, started)
    _attach_usage_to_trace(model, usage)
    return result


def _attach_usage_to_trace(model: str, usage: Usage) -> None:
    """Put tokens and dollars on the LangSmith run, so the trace view shows what each step cost."""
    run = get_current_run_tree()
    if run is None:
        return
    run.set(
        usage_metadata={
            "input_tokens": usage.input_tokens + usage.cache_write_tokens + usage.cache_read_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.input_tokens + usage.cache_write_tokens + usage.cache_read_tokens + usage.output_tokens,
            "input_token_details": {"cache_read": usage.cache_read_tokens, "cache_creation": usage.cache_write_tokens},
            "total_cost": price_of(model, usage),
        },
        metadata={"cost_usd": price_of(model, usage), "model_used": model},
    )


def _call_anthropic(system, prompt, model, max_tokens, schema):
    client = anthropic_client()
    request = {
        "model": model,
        "max_tokens": max_tokens,
        # The system prompt (story bible, style guide) repeats across calls, so cache it.
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": prompt}],
    }
    if model in config.MODELS_WITH_EFFORT:
        effort = config.PLANNER_EFFORT if model == config.PLANNER_MODEL else config.WRITER_EFFORT
        request["output_config"] = {"effort": effort}
        # If a safety classifier declines (dark themes happen in fiction), let the API
        # retry on a fallback model instead of failing the whole episode.
        request["betas"] = [FALLBACK_BETA]
        request["fallbacks"] = "default"

    if schema is None:
        if "betas" in request:
            response = client.beta.messages.create(**request)
        else:
            response = client.messages.create(**request)
    else:
        if "betas" in request:
            response = client.beta.messages.parse(output_format=schema, **request)
        else:
            response = client.messages.parse(output_format=schema, **request)

    if response.stop_reason == "refusal":
        raise LLMError("the model declined this request")
    if response.stop_reason == "max_tokens":
        raise LLMError(f"ran out of tokens (max_tokens={max_tokens})")

    usage = Usage(
        input_tokens=response.usage.input_tokens or 0,
        output_tokens=response.usage.output_tokens or 0,
        cache_read_tokens=response.usage.cache_read_input_tokens or 0,
        cache_write_tokens=response.usage.cache_creation_input_tokens or 0,
    )
    if schema is not None:
        return response.parsed_output, usage
    text = "".join(block.text for block in response.content if block.type == "text")
    return text.strip(), usage


def _call_openrouter(system, prompt, model, max_tokens, schema):
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": _openrouter_system(system, model)},
            {"role": "user", "content": prompt},
        ],
        "usage": {"include": True},
    }
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "strict": True, "schema": schema.model_json_schema()},
        }
        # Only route to providers that actually enforce the schema.
        body["provider"] = {"require_parameters": True}
    if model in config.MODELS_WITH_EFFORT:
        # Same thinking budget as the direct API; left unset, Sonnet 5.5 thinks at "high" and costs ~2x.
        body["reasoning"] = {"effort": config.WRITER_EFFORT}

    response = httpx.post(
        config.OPENROUTER_URL,
        headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"},
        json=body,
        timeout=config.LLM_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise LLMError(str(data["error"]))

    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise LLMError(f"ran out of tokens (max_tokens={max_tokens})")
    text = choice["message"]["content"] or ""
    raw_usage = data.get("usage") or {}
    cached = (raw_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    usage = Usage(
        input_tokens=raw_usage.get("prompt_tokens", 0) - cached,
        output_tokens=raw_usage.get("completion_tokens", 0),
        cache_read_tokens=cached,
        cost_usd=raw_usage.get("cost"),
    )
    if schema is None:
        return text.strip(), usage
    return schema.model_validate(json.loads(_strip_code_fence(text))), usage


def _openrouter_system(system: str, model: str):
    """Claude models on OpenRouter honour Anthropic's cache_control, so cache the stable system prompt."""
    if model.startswith("anthropic/"):
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    return system


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text


def _record_call(step, model, story_id, episode, usage: Usage, started: float, error: str = ""):
    latency_ms = int((time.perf_counter() - started) * 1000)
    call = LLMCall(
        story_id=story_id,
        episode_number=episode,
        step=step,
        model=model,
        input_tokens=usage.input_tokens + usage.cache_write_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cost_usd=price_of(model, usage),
        latency_ms=latency_ms,
        succeeded=not error,
        error=error[:2000],
    )
    with session_scope() as session:
        session.add(call)
    log.info(
        "%s | %s | in=%s out=%s | $%.4f | %sms%s",
        step, model, call.input_tokens, call.output_tokens, call.cost_usd, latency_ms,
        f" | ERROR {error[:120]}" if error else "",
    )
