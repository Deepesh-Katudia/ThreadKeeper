"""Read-only views: the story's memory, costs, and background jobs."""

from collections import defaultdict

from fastapi import APIRouter
from sqlalchemy import select

from api.views import (
    act_view, call_view, character_view, directive_view, fact_view, job_view, thread_view,
)
from story import config
from story.db import session_scope
from story.models import Directive, Job, LLMCall
from story.queries import NotFound, acts, all_episodes, characters, facts, get_story, threads

router = APIRouter(tags=["memory"])


@router.get("/stories/{story_id}/memory")
def memory(story_id: int):
    with session_scope() as session:
        story = get_story(session, story_id)
        directives = session.scalars(
            select(Directive).where(Directive.story_id == story_id).order_by(Directive.id)
        )
        return {
            "story_so_far": story.story_so_far,
            "story_so_far_through": story.story_so_far_through,
            "acts": [act_view(a) for a in acts(session, story_id)],
            "characters": [character_view(c) for c in characters(session, story_id)],
            "facts": [fact_view(f) for f in facts(session, story_id)],
            "threads": [thread_view(t) for t in threads(session, story_id)],
            "directives": [directive_view(d) for d in directives],
        }


@router.get("/stories/{story_id}/costs")
def costs(story_id: int):
    with session_scope() as session:
        story = get_story(session, story_id)
        calls = list(session.scalars(select(LLMCall).where(LLMCall.story_id == story_id).order_by(LLMCall.id)))
        approved = [e.number for e in all_episodes(session, story_id) if e.status == "approved"]
        total_episodes = story.total_episodes

    per_episode = summarise_by_episode(calls)
    evals = [c for c in calls if c.step.startswith("eval_")]
    planning = [c for c in calls if c.episode_number == 0 and c not in evals]
    written = [per_episode[n] for n in approved if n in per_episode]
    return {
        "total_cost_usd": round(sum(c.cost_usd for c in calls), 4),
        "planning_cost_usd": round(sum(c.cost_usd for c in planning), 4),
        "eval_cost_usd": round(sum(c.cost_usd for c in evals), 4),
        "per_episode": [per_episode[n] for n in sorted(per_episode)],
        "projection": project_full_run(written, total_episodes, planning),
        "cost_cap_per_episode_usd": config.EPISODE_COST_CAP_USD,
        "recent_calls": [call_view(c) for c in calls[-200:]],
    }


def summarise_by_episode(calls: list[LLMCall]) -> dict[int, dict]:
    totals: dict[int, dict] = defaultdict(lambda: {
        "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "latency_ms": 0, "calls": 0, "failed_calls": 0,
        "revisions": 0,
    })
    for call in calls:
        if call.episode_number == 0:
            continue
        row = totals[call.episode_number]
        row["episode"] = call.episode_number
        row["cost_usd"] = round(row["cost_usd"] + call.cost_usd, 5)
        row["input_tokens"] += call.input_tokens
        row["output_tokens"] += call.output_tokens
        row["latency_ms"] += call.latency_ms
        row["calls"] += 1
        row["failed_calls"] += 0 if call.succeeded else 1
        row["revisions"] += 1 if call.step == "revise" else 0
    return dict(totals)


def project_full_run(written: list[dict], total_episodes: int, planning: list[LLMCall]) -> dict:
    """Extrapolate cost and time for the whole serial from the episodes written so far."""
    if not written:
        return {"based_on_episodes": 0}
    average_cost = sum(r["cost_usd"] for r in written) / len(written)
    average_seconds = sum(r["latency_ms"] for r in written) / len(written) / 1000
    planning_cost = sum(c.cost_usd for c in planning)
    return {
        "based_on_episodes": len(written),
        "average_cost_per_episode_usd": round(average_cost, 4),
        "average_seconds_per_episode": round(average_seconds, 1),
        "estimated_total_cost_usd": round(average_cost * total_episodes + planning_cost, 2),
        "estimated_total_hours": round(average_seconds * total_episodes / 3600, 2),
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise NotFound(f"job {job_id} does not exist")
        return job_view(job)
