"""Writing episodes and the human review controls."""

from fastapi import APIRouter, BackgroundTasks

from api.jobs import start_job
from api.schemas import EpisodeEdit, Feedback, Rejection, WriteRequest
from api.views import episode_full, job_view, ripple_view, version_view
from story import pipeline, ripple
from story.db import session_scope
from story.queries import get_episode, versions_of

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
    """Editing a draft returns the episode. Editing an approved one also returns the ripple it started."""
    ripple_id = pipeline.edit_episode(story_id, number, body.text, body.title)
    with session_scope() as session:
        episode = episode_full(get_episode(session, story_id, number))
        if ripple_id is None:
            return {"episode": episode, "ripple": None}
        found = ripple.get_ripple(session, story_id, ripple_id)
        return {"episode": episode, "ripple": ripple_view(found, ripple.items_of(session, ripple_id))}


@router.get("/episodes/{number}/versions")
def list_versions(story_id: int, number: int):
    with session_scope() as session:
        episode = get_episode(session, story_id, number)
        return [version_view(v, episode.current_version) for v in versions_of(session, story_id, number)]


@router.post("/episodes/{number}/versions/{version}/restore")
def restore(story_id: int, number: int, version: int):
    """Restoring starts a ripple too, but its memory diff is worked out in code, not by a model."""
    ripple_id = ripple.start_restore(story_id, number, version)
    with session_scope() as session:
        return ripple_view(ripple.get_ripple(session, story_id, ripple_id), ripple.items_of(session, ripple_id))


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
