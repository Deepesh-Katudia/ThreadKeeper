"""Ripple review: the three human gates after an approved episode is edited (see story/ripple.py)."""

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from api.jobs import running_job, start_job
from api.schemas import MemoryConfirm, ReplanApproval, RippleDecision
from api.views import job_view, ripple_view
from story import ripple
from story.db import session_scope
from story.errors import NotAllowed
from story.models import Ripple
from story.queries import get_story

router = APIRouter(prefix="/stories/{story_id}/ripples", tags=["ripples"])


def view(story_id: int, ripple_id: int) -> dict:
    with session_scope() as session:
        found = ripple.get_ripple(session, story_id, ripple_id)
        return ripple_view(found, ripple.items_of(session, ripple_id))


@router.get("")
def list_ripples(story_id: int):
    """Every ripple for the History page, newest first."""
    with session_scope() as session:
        get_story(session, story_id)
        rows = session.scalars(select(Ripple).where(Ripple.story_id == story_id).order_by(Ripple.id.desc()))
        return [ripple_view(r, ripple.items_of(session, r.id)) for r in rows]


@router.get("/{ripple_id}")
def read_ripple(story_id: int, ripple_id: int):
    return view(story_id, ripple_id)


@router.post("/{ripple_id}/confirm-memory")
def confirm_memory(story_id: int, ripple_id: int, body: MemoryConfirm, background: BackgroundTasks):
    """Gate 1: apply the memory diff now, then check later episodes in the background."""
    if running_job(story_id) is not None:
        raise NotAllowed("Something is already running for this story. Wait for it to finish.")
    ripple.confirm_memory(story_id, ripple_id, body.diff)
    job = start_job(background, story_id, "ripple_scan", ripple.scan, story_id, ripple_id)
    return {"ripple": view(story_id, ripple_id), "job": job_view(job)}


@router.post("/{ripple_id}/cancel")
def cancel(story_id: int, ripple_id: int):
    ripple.cancel_ripple(story_id, ripple_id)
    return view(story_id, ripple_id)


@router.post("/{ripple_id}/items/{number}/decide")
def decide(story_id: int, ripple_id: int, number: int, body: RippleDecision, background: BackgroundTasks):
    """Gate 2, one episode. Keep answers at once; the others call models, so they run as a job."""
    if body.decision == "keep":
        ripple.decide_item(story_id, ripple_id, number, "keep", note=body.note)
        return {"ripple": view(story_id, ripple_id), "job": None}
    ripple.check_decision(story_id, ripple_id, number, body.decision, body.text)  # fail early, before queuing
    job = start_job(
        background, story_id, f"ripple_{body.decision}", ripple.decide_item,
        story_id, ripple_id, number, body.decision, body.text, body.note,
    )
    return {"ripple": view(story_id, ripple_id), "job": job_view(job)}


@router.post("/{ripple_id}/accept-minor")
def accept_minor(story_id: int, ripple_id: int, background: BackgroundTasks):
    with session_scope() as session:
        ripple.get_ripple(session, story_id, ripple_id, "reviewing")
    job = start_job(background, story_id, "ripple_accept_minor", ripple.accept_all_minor, story_id, ripple_id)
    return {"ripple": view(story_id, ripple_id), "job": job_view(job)}


@router.post("/{ripple_id}/approve-replan")
def approve_replan(story_id: int, ripple_id: int, body: ReplanApproval):
    """Gate 3: apply the chosen beat changes and close the ripple."""
    ripple.approve_replan(story_id, ripple_id, body.episodes)
    return view(story_id, ripple_id)
