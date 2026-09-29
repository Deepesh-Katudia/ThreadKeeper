"""Stories and the arc plan: create, view, edit, approve."""

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from api.jobs import running_job, start_job
from api.schemas import ArcEdit, NewStory
from api.views import act_view, character_view, episode_brief, job_view, story_view
from story.db import session_scope
from story.models import Character, Job, Story
from story.pipeline import NotAllowed
from story.planner import MISSING_BEAT, plan_arc, reset_plan
from story.queries import acts, all_episodes, characters, get_episode, get_story

router = APIRouter(prefix="/stories", tags=["stories"])


@router.get("")
def list_stories():
    with session_scope() as session:
        stories = list(session.scalars(select(Story).order_by(Story.id.desc())))
        result = []
        for story in stories:
            episodes = all_episodes(session, story.id)
            result.append({
                **story_view(story),
                "approved_episodes": sum(1 for e in episodes if e.status == "approved"),
            })
        return result


@router.post("")
def create_story(body: NewStory, background: BackgroundTasks):
    with session_scope() as session:
        story = Story(premise=body.premise.strip(), total_episodes=body.total_episodes)
        session.add(story)
        session.flush()
        story_id = story.id
    job = start_job(background, story_id, "plan_arc", plan_arc_or_mark_failed, story_id)
    return {"story_id": story_id, "job": job_view(job)}


def plan_arc_or_mark_failed(story_id: int) -> str:
    try:
        plan_arc(story_id)
    except Exception:
        with session_scope() as session:
            get_story(session, story_id).status = "planning_failed"
        raise
    return "Arc planned. Review it before writing starts."


@router.post("/{story_id}/plan")
def replan_from_scratch(story_id: int, background: BackgroundTasks):
    """Throw away the plan and plan again. Only allowed before writing starts."""
    with session_scope() as session:
        status = get_story(session, story_id).status
    if status not in ("arc_review", "planning_failed"):
        raise NotAllowed("The arc can only be re-planned before writing starts.")
    reset_plan(story_id)
    job = start_job(background, story_id, "plan_arc", plan_arc_or_mark_failed, story_id)
    return {"job": job_view(job)}


@router.get("/{story_id}")
def get_story_overview(story_id: int):
    with session_scope() as session:
        story = get_story(session, story_id)
        episodes = all_episodes(session, story_id)
        latest_job = session.scalar(select(Job).where(Job.story_id == story_id).order_by(Job.id.desc()))
        return {
            "story": story_view(story),
            "acts": [act_view(a) for a in acts(session, story_id)],
            "characters": [character_view(c) for c in characters(session, story_id)],
            "episodes": [episode_brief(e) for e in episodes],
            "next_episode": next((e.number for e in episodes if e.status != "approved"), None),
            "running_job": job_view(running_job(story_id)),
            "latest_job": job_view(latest_job),
        }


@router.put("/{story_id}/arc")
def edit_arc(story_id: int, body: ArcEdit):
    with session_scope() as session:
        story = get_story(session, story_id)
        if story.status not in ("arc_review", "writing"):
            raise NotAllowed("The arc can't be edited right now.")
        for edit in body.beats:
            episode = get_episode(session, story_id, edit.number)
            if episode.status == "approved":
                raise NotAllowed(f"Episode {edit.number} is already written; edit its text instead.")
            episode.beat = edit.beat.strip()
        for edit in body.characters:
            person = session.get(Character, edit.id) if edit.id else None
            if person is None or person.story_id != story_id:
                person = Character(story_id=story_id)
                session.add(person)
            person.name, person.role = edit.name.strip(), edit.role
            person.description, person.planned_arc = edit.description, edit.planned_arc
    return {"ok": True}


@router.post("/{story_id}/arc/approve")
def approve_arc(story_id: int):
    with session_scope() as session:
        story = get_story(session, story_id)
        if story.status != "arc_review":
            raise NotAllowed(f"The story is '{story.status}', not waiting for arc approval.")
        missing = [e.number for e in all_episodes(session, story_id) if e.beat == MISSING_BEAT]
        if missing:
            raise NotAllowed(f"Episodes {missing[:10]} have no beat yet. Fill them in first.")
        story.status = "writing"
    return {"ok": True}
