"""Evaluation in LangSmith, at two levels.

1. Online, on every episode, at no extra model cost:
   - when an episode is written, the critic's verdict, hook score, length check and revision
     count are attached to that episode's trace as LangSmith feedback;
   - when a human approves, edits or rejects it, that decision is attached to the same trace.
   Over time LangSmith holds, for every episode, what the machine thought and what the human did,
   which is exactly the data needed to check whether the critic agrees with people.

2. Offline, on demand ("Run evaluation" in the app, or `python -m evals.run_evals --story N`):
   a LangSmith experiment over every approved episode with five evaluators: word count and
   repetition (code), plus hook, consistency and directive-following (LLM judge from another
   model family). Results are stored in the evaluations table and linked from the app.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache

from langsmith import Client, evaluate, get_current_run_tree
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from story import config, llm
from story.critic import similar_earlier_episodes
from story.db import session_scope
from story.models import Directive, Evaluation, LLMCall
from story.queries import all_episodes, facts, get_story

log = logging.getLogger(__name__)

JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", config.CRITIC_MODEL)
EVALUATOR_KEYS = ["word_count", "no_repetition", "hook", "consistency", "follows_directives"]

# Feedback is sent in the background so a slow LangSmith never slows down the app.
_sender = ThreadPoolExecutor(max_workers=2, thread_name_prefix="langsmith-feedback")
_client: Client | None = None


def langsmith_enabled() -> bool:
    tracing = os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes")
    return tracing and bool(os.getenv("LANGSMITH_API_KEY"))


def langsmith_client() -> Client:
    global _client
    if _client is None:
        _client = Client()
    return _client


def current_trace_run_id() -> str | None:
    """The id of the LangSmith run we're inside, so feedback can be attached to it later."""
    run = get_current_run_tree()
    return str(run.id) if run is not None else None


@lru_cache(maxsize=1)
def tracing_project():
    """The LangSmith project our traces go to (looked up once)."""
    return langsmith_client().read_project(project_name=os.getenv("LANGSMITH_PROJECT", "default"))


def project_url() -> str | None:
    if not langsmith_enabled():
        return None
    try:
        return tracing_project().url
    except Exception as error:
        log.warning("couldn't look up the LangSmith project URL: %s", error)
        return None


# ---------------------------------------------------------------------------
# 1. Online feedback on each episode's trace
# ---------------------------------------------------------------------------


def log_feedback(run_id: str | None, key: str, score: float | None = None, value=None, comment: str = "") -> None:
    if not run_id or not langsmith_enabled():
        return
    _sender.submit(_send_feedback, run_id, key, score, value, comment)


def _send_feedback(run_id, key, score, value, comment) -> None:
    try:
        # Naming the project (session) is required by newer LangSmith versions.
        langsmith_client().create_feedback(
            run_id, key, score=score, value=value, comment=comment or None, session_id=tracing_project().id,
        )
    except Exception as error:  # feedback is nice to have; never break the story over it
        log.warning("LangSmith feedback %s on run %s failed: %s", key, run_id, error)


def log_critic_scores(run_id: str | None, report: dict, word_count: int) -> None:
    """What the machine thought of a draft, attached to the trace that wrote it."""
    final = report.get("final") or {}
    problems = final.get("problems") or []
    log_feedback(run_id, "critic_passed", score=1 if report.get("passed") else 0, comment=final.get("advice", ""))
    log_feedback(run_id, "critic_hook", score=(final.get("hook_score") or 0) / 5)
    log_feedback(run_id, "word_count_ok", score=int(config.MIN_WORDS <= word_count <= config.MAX_WORDS), value=word_count)
    log_feedback(run_id, "critic_problems", score=len(problems), comment="; ".join(p.get("detail", "") for p in problems)[:2000])
    log_feedback(run_id, "revisions", score=max(0, len(report.get("attempts", [])) - 1))
    log_feedback(run_id, "possible_repeat", score=int(bool(report.get("possible_repeats_of"))))


def log_human_decision(run_id: str | None, decision: str, comment: str = "") -> None:
    """What the human did with the draft: the label that matters most."""
    score = {"approved": 1, "edited": 0.5, "rejected": 0}.get(decision)
    log_feedback(run_id, "human_decision", score=score, value=decision, comment=comment)


# ---------------------------------------------------------------------------
# 2. Offline experiment over all approved episodes
# ---------------------------------------------------------------------------


class Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int
    reason: str


def episode_snapshot(story_id: int, number: int) -> dict:
    """Everything the evaluators need for one episode, as the story stood when it was written."""
    with session_scope() as session:
        episodes = {e.number: e for e in all_episodes(session, story_id)}
        episode = episodes[number]
        canon = [f"{f.subject}: {f.statement}" for f in facts(session, story_id) if f.source_episode < number][-60:]
        directives = [
            d.text for d in session.scalars(select(Directive).where(Directive.story_id == story_id))
            if d.given_after_episode < number and (d.expires_after_episode == 0 or d.expires_after_episode >= number)
        ]
        earlier = {n: e.summary for n, e in episodes.items() if n < number and e.status == "approved" and e.summary}
        return {
            "story_id": story_id, "episode": number,
            "text": episode.text, "summary": episode.summary, "beat": episode.beat,
            "canon": canon, "directives": directives, "earlier_summaries": earlier,
        }


def judge(step: str, question: str, outputs: dict) -> Judgement:
    # Logged against episode 0 with an "eval_" step, so it never counts toward an episode's cost cap.
    return llm.write_json(
        f"eval_{step}", "You are a strict, fair judge of serial fiction. Score 1-5 and explain briefly.",
        question, Judgement, JUDGE_MODEL, story_id=outputs["story_id"], max_tokens=1500,
    )


def word_count(outputs: dict) -> dict:
    words = len(outputs["text"].split())
    return {"key": "word_count", "score": int(config.MIN_WORDS <= words <= config.MAX_WORDS), "comment": f"{words} words"}


def repetition(outputs: dict) -> dict:
    earlier = {int(k): v for k, v in outputs["earlier_summaries"].items()}
    repeats = similar_earlier_episodes(outputs["summary"], earlier)
    return {"key": "no_repetition", "score": int(not repeats), "comment": f"similar to episodes {repeats}" if repeats else "no near-repeats"}


def hook(outputs: dict) -> dict:
    ending = " ".join(outputs["text"].split()[-120:])
    result = judge("hook", f"""Here is how an episode of a daily serial ends:
<ending>{ending}</ending>
Score 1-5: how strongly does this ending make a reader need the next episode?
5 = a real cliffhanger earned by the scene; 1 = it just stops.""", outputs)
    return {"key": "hook", "score": result.score / 5, "comment": result.reason}


def consistency(outputs: dict) -> dict:
    canon = "\n".join(f"- {line}" for line in outputs["canon"]) or "(nothing established yet)"
    result = judge("consistency", f"""Canon established before this episode:
{canon}

Episode:
<episode>{outputs["text"]}</episode>

Score 1-5: 5 = fully consistent with the canon, 1 = clear contradictions (dead people acting,
facts reversed, people knowing things they couldn't). Quote any contradiction.""", outputs)
    return {"key": "consistency", "score": result.score / 5, "comment": result.reason}


def follows_directives(outputs: dict) -> dict:
    if not outputs["directives"]:
        return {"key": "follows_directives", "score": None, "comment": "no instructions were in force"}
    rules = "\n".join(f"- {d}" for d in outputs["directives"])
    result = judge("directives", f"""The editor's standing instructions when this episode was written:
{rules}

Episode:
<episode>{outputs["text"]}</episode>

Score 1-5: does the episode respect every instruction? 5 = clearly, 1 = ignores them.""", outputs)
    return {"key": "follows_directives", "score": result.score / 5, "comment": result.reason}


def sync_dataset(client: Client, story_id: int, title: str, approved: list[int]):
    """One dataset per story; each approved episode becomes an example the first time it's seen."""
    name = f"threadkeeper-story-{story_id}"
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
    else:
        dataset = client.create_dataset(dataset_name=name, description=f"Approved episodes of '{title}'")
    known = {ex.inputs.get("episode") for ex in client.list_examples(dataset_id=dataset.id)}
    new = [{"inputs": {"story_id": story_id, "episode": n}, "metadata": {"episode": n}} for n in approved if n not in known]
    if new:
        client.create_examples(dataset_id=dataset.id, examples=new)
    examples = [ex for ex in client.list_examples(dataset_id=dataset.id) if ex.inputs.get("episode") in set(approved)]
    return dataset, examples


def run_experiment(story_id: int) -> Evaluation:
    """Score every approved episode in LangSmith and store a summary. Raises if LangSmith isn't set up."""
    if not langsmith_enabled():
        raise RuntimeError("LangSmith isn't configured. Set LANGSMITH_API_KEY and LANGSMITH_TRACING=true in backend/.env.")

    with session_scope() as session:
        story = get_story(session, story_id)
        title = story.title or f"story {story_id}"
        approved = [e.number for e in all_episodes(session, story_id) if e.status == "approved"]
    if not approved:
        raise RuntimeError("There are no approved episodes to evaluate yet.")

    started = datetime.now(timezone.utc)
    client = langsmith_client()
    _dataset, examples = sync_dataset(client, story_id, title, approved)

    results = evaluate(
        lambda inputs: episode_snapshot(inputs["story_id"], inputs["episode"]),
        data=examples,
        evaluators=[word_count, repetition, hook, consistency, follows_directives],
        experiment_prefix=f"story-{story_id}",
        metadata={"story_id": story_id, "judge_model": JUDGE_MODEL, "episodes": len(approved)},
        max_concurrency=4,
        client=client,
    )
    per_episode = summarise_rows(results)
    return save_evaluation(story_id, results, per_episode, started)


def summarise_rows(results) -> list[dict]:
    rows = []
    for row in results:
        entry = {"episode": row["example"].inputs.get("episode"), "comments": {}}
        for result in row["evaluation_results"]["results"]:
            entry[result.key] = result.score
            entry["comments"][result.key] = result.comment or ""
        rows.append(entry)
    return sorted(rows, key=lambda r: r["episode"])


def average_scores(per_episode: list[dict]) -> dict:
    averages = {}
    for key in EVALUATOR_KEYS:
        values = [row[key] for row in per_episode if isinstance(row.get(key), (int, float))]
        averages[key] = round(sum(values) / len(values), 3) if values else None
    return averages


def save_evaluation(story_id: int, results, per_episode: list[dict], started: datetime) -> Evaluation:
    with session_scope() as session:
        judge_cost = session.scalar(
            select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
                LLMCall.story_id == story_id, LLMCall.step.like("eval_%"), LLMCall.created_at >= started
            )
        )
        evaluation = Evaluation(
            story_id=story_id,
            experiment_name=results.experiment_name,
            experiment_url=getattr(results, "url", "") or "",
            episodes_scored=len(per_episode),
            scores=average_scores(per_episode),
            per_episode=per_episode,
            cost_usd=round(float(judge_cost or 0.0), 4),
        )
        session.add(evaluation)
        session.flush()
        return evaluation
