"""Evaluation: run a LangSmith experiment, list past results, compare critic and human."""

from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from api.jobs import start_job
from api.views import job_view
from story import evaluation
from story.db import session_scope
from story.models import Evaluation
from story.pipeline import NotAllowed
from story.queries import all_episodes, get_story

router = APIRouter(prefix="/stories/{story_id}/evaluations", tags=["evaluations"])

# Three judge calls per episode on a small model; replaced by the measured cost once one has run.
ESTIMATED_COST_PER_EPISODE = 0.003


@lru_cache(maxsize=1)
def cached_project_url() -> str | None:
    return evaluation.project_url()


@router.get("")
def list_evaluations(story_id: int):
    with session_scope() as session:
        get_story(session, story_id)
        runs = list(session.scalars(
            select(Evaluation).where(Evaluation.story_id == story_id).order_by(Evaluation.id.desc())
        ))
        episodes = all_episodes(session, story_id)
        approved = sum(1 for e in episodes if e.status == "approved")
        return {
            "langsmith_enabled": evaluation.langsmith_enabled(),
            "project_url": cached_project_url(),
            "judge_model": evaluation.JUDGE_MODEL,
            "approved_episodes": approved,
            "estimated_cost_usd": round(approved * cost_per_episode(runs), 4),
            "evaluations": [evaluation_view(run) for run in runs],
            "critic_vs_human": critic_vs_human(episodes),
        }


@router.post("")
def start_evaluation(story_id: int, background: BackgroundTasks):
    if not evaluation.langsmith_enabled():
        raise NotAllowed("LangSmith isn't configured. Set LANGSMITH_API_KEY and LANGSMITH_TRACING=true in backend/.env.")

    def run() -> str:
        result = evaluation.run_experiment(story_id)
        return f"Scored {result.episodes_scored} episodes for ${result.cost_usd:.4f}."

    job = start_job(background, story_id, "evaluate", run)
    return {"job": job_view(job)}


def cost_per_episode(runs: list[Evaluation]) -> float:
    measured = [r.cost_usd / r.episodes_scored for r in runs if r.episodes_scored and r.cost_usd]
    return measured[0] if measured else ESTIMATED_COST_PER_EPISODE


def evaluation_view(run: Evaluation) -> dict:
    return {
        "id": run.id,
        "experiment_name": run.experiment_name,
        "experiment_url": run.experiment_url,
        "episodes_scored": run.episodes_scored,
        "scores": run.scores,
        "per_episode": run.per_episode,
        "cost_usd": run.cost_usd,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def critic_vs_human(episodes) -> dict:
    """How often did the human agree with the critic? The same labels are also in LangSmith as feedback."""
    rows = []
    for episode in episodes:
        report = episode.critic_report or {}
        if "passed" not in report:
            continue
        human = "approved" if episode.status == "approved" else episode.status
        if episode.was_edited_by_human:
            human = f"{human} (edited)"
        rows.append({
            "episode": episode.number,
            "critic_passed": report.get("passed"),
            "hook_score": (report.get("final") or {}).get("hook_score"),
            "revisions": max(0, len(report.get("attempts", [])) - 1),
            "human": human,
            "agrees": report.get("passed") == (episode.status == "approved" and not episode.was_edited_by_human),
        })
    decided = [r for r in rows if not r["human"].startswith("in_review")]
    agreement = sum(r["agrees"] for r in decided) / len(decided) if decided else None
    return {"rows": rows, "agreement": round(agreement, 3) if agreement is not None else None}
