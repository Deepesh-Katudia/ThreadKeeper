"""Writing episodes and the human review controls."""

from fastapi import APIRouter, BackgroundTasks

from api.jobs import start_job
from api.schemas import EpisodeEdit, Feedback, Rejection, WriteRequest
from api.views import episode_full, job_view
from story import pipeline
from story.db import session_scope
from story.queries import get_episode

router = APIRouter(prefix="/stories/{story_id}", tags=["episodes"])


@router.post("/episodes/next")
def write_next(story_id: int, body: WriteRequest, background: BackgroundTasks):
    number = pipeline.next_episode_to_write(story_id)  # fails early with a clear message
    if number is None:
        raise pipeline.NotAllowed("Every episode is already written.")
    job = start_job(background, story_id, "write", pipeline.write_batch, story_id, body.count, body.auto_approve)
    return {"episode": number, "job": job_view(job)}


@router.get("/episodes/{number}")
def read_episode(story_id: int, number: int):
    with session_scope() as session:
        return episode_full(get_episode(session, story_id, number))


@router.post("/episodes/{number}/approve")
def approve(story_id: int, number: int):
    pipeline.approve_episode(story_id, number)
    return {"ok": True}


@router.put("/episodes/{number}")
def edit(story_id: int, number: int, body: EpisodeEdit):
    pipeline.edit_episode(story_id, number, body.text, body.title)
    with session_scope() as session:
        return episode_full(get_episode(session, story_id, number))


@router.post("/episodes/{number}/reject")
def reject(story_id: int, number: int, body: Rejection, background: BackgroundTasks):
    pipeline.reject_episode(story_id, number, body.reason)
    if not body.rewrite_now:
        return {"job": None}
    job = start_job(background, story_id, "rewrite", pipeline.write_episode, story_id, number)
    return {"job": job_view(job)}


@router.post("/feedback")
def feedback(story_id: int, body: Feedback, background: BackgroundTasks):
    def save_and_replan():
        directive = pipeline.give_feedback(story_id, body.text, body.expires_after_episode)
        return directive.replan_summary

    job = start_job(background, story_id, "feedback", save_and_replan)
    return {"job": job_view(job)}


@router.delete("/directives/{directive_id}")
def retire(story_id: int, directive_id: int):
    pipeline.retire_directive(story_id, directive_id)
    return {"ok": True}
