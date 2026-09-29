"""The episode loop and every human decision point.

    write_next_episode   draft -> critic -> (revise, at most twice) -> extract memory -> wait for human
    approve_episode      commit the memory, refresh recaps
    edit_episode         human rewrites text; memory is re-extracted (even for past episodes)
    reject_episode       send it back with a note; the next draft sees the note
    give_feedback        a standing instruction + re-planned upcoming beats

Resuming needs nothing special: every episode has a status in the database, and the next one
to write is simply the first that isn't approved.
"""

import logging

from langsmith import traceable
from sqlalchemy import select

from story import config, evaluation, llm
from story.context import build_episode_context
from story.critic import needs_revision, review_draft, similar_earlier_episodes
from story.db import session_scope
from story.memory import commit_memory, extract_memory, forget_episode, refresh_story_so_far, summarise_act
from story.models import Directive, Episode, Job
from story.planner import replan_upcoming_beats
from story.queries import act_for_episode, all_episodes, characters, get_episode, get_story
from story.schemas import MemoryUpdate
from story.writer import count_words, draft_episode, revise_episode

log = logging.getLogger(__name__)


class NotAllowed(ValueError):
    """The request makes sense, just not right now (e.g. writing before the arc is approved)."""


# --- Where are we? -------------------------------------------------------------------


def next_episode_to_write(story_id: int) -> int | None:
    with session_scope() as session:
        story = get_story(session, story_id)
        if story.status != "writing":
            raise NotAllowed(f"The story is '{story.status}'. Approve the arc plan before writing.")
        for episode in all_episodes(session, story_id):
            if episode.status == "in_review":
                raise NotAllowed(f"Episode {episode.number} is waiting for your review first.")
            if episode.status == "drafting":
                raise NotAllowed(f"Episode {episode.number} is being written right now.")
            if episode.status != "approved":
                return episode.number
    return None


# --- Writing ------------------------------------------------------------------------


@traceable(name="write_episode")
def write_episode(story_id: int, number: int) -> None:
    """Write one episode and leave it waiting for review. Never raises; failures are stored on the episode."""
    with session_scope() as session:
        episode = get_episode(session, story_id, number)
        editor_note = episode.human_note
        episode.status, episode.error = "drafting", ""

    try:
        context, draft, report, attempts = draft_until_good_enough(story_id, number, editor_note)
        update = extract_memory(story_id, number, draft.text)
        report_dict = build_report(story_id, number, context, report, attempts, update)
        report_dict["trace_run_id"] = evaluation.current_trace_run_id()
    except Exception as error:  # we want the reason on screen, not a dead background task
        log.exception("episode %s failed", number)
        with session_scope() as session:
            episode = get_episode(session, story_id, number)
            episode.status, episode.error = "failed", str(error)[:2000]
        return

    with session_scope() as session:
        episode = get_episode(session, story_id, number)
        episode.title = draft.title
        episode.text = draft.text
        episode.critic_report = report_dict
        episode.pending_memory = update.model_dump()
        episode.revision_count = len(attempts) - 1
        episode.was_edited_by_human = False
        episode.status = "in_review"

    evaluation.log_critic_scores(report_dict["trace_run_id"], report_dict, count_words(draft.text))


def draft_until_good_enough(story_id: int, number: int, editor_note: str):
    """Draft, then revise while the critic objects. Stops at MAX_REVISIONS or the cost cap."""
    with session_scope() as session:
        context = build_episode_context(session, story_id, number)
        cast = characters(session, story_id)

    draft = draft_episode(story_id, context, editor_note)
    report = review_draft(story_id, context, draft, cast)
    attempts = [summarise_attempt(draft, report, "draft")]

    for _ in range(config.MAX_REVISIONS):
        if not needs_revision(report):
            break
        if llm.episode_cost(story_id, number) >= config.EPISODE_COST_CAP_USD:
            attempts.append({"stage": "stopped", "reason": "cost cap reached"})
            break
        draft = revise_episode(story_id, context, draft, report)
        report = review_draft(story_id, context, draft, cast)
        attempts.append(summarise_attempt(draft, report, "revision"))

    return context, draft, report, attempts


def summarise_attempt(draft, report, stage: str) -> dict:
    return {
        "stage": stage,
        "words": count_words(draft.text),
        "verdict": report.verdict,
        "hook_score": report.hook_score,
        "problems": [p.model_dump() for p in report.problems],
    }


def build_report(story_id: int, number: int, context, report, attempts: list[dict], update: MemoryUpdate) -> dict:
    return {
        "final": report.model_dump(),
        "attempts": attempts,
        "passed": not needs_revision(report),
        "possible_repeats_of": similar_earlier_episodes(update.summary, context.known_summaries),
        "cost_usd": round(llm.episode_cost(story_id, number), 4),
        "context_sent": context.sections,
    }


@traceable(name="write_batch")
def write_batch(story_id: int, count: int, auto_approve: bool) -> str:
    """Write up to `count` episodes. With auto_approve, only episodes the critic is unhappy with stop for a human."""
    written = 0
    for _ in range(count):
        number = next_episode_to_write(story_id)
        if number is None:
            return f"Story complete after {written} new episodes."
        write_episode(story_id, number)
        written += 1
        with session_scope() as session:
            episode = get_episode(session, story_id, number)
            status, passed = episode.status, episode.critic_report.get("passed", False)
        if status == "failed":
            return f"Stopped: episode {number} failed."
        if not auto_approve:
            return f"Episode {number} is ready for review."
        if not passed:
            return f"Stopped at episode {number}: the critic flagged problems, please review."
        approve_episode(story_id, number)
    return f"Wrote and approved {written} episodes."


# --- Human decisions ------------------------------------------------------------------


def approve_episode(story_id: int, number: int) -> None:
    with session_scope() as session:
        episode = get_episode(session, story_id, number)
        if episode.status != "in_review":
            raise NotAllowed(f"Episode {number} is '{episode.status}', not waiting for review.")
        commit_memory(session, story_id, number, MemoryUpdate.model_validate(episode.pending_memory))
        episode.pending_memory = {}
        episode.status = "approved"
        trace_run_id = episode.critic_report.get("trace_run_id")
        story = get_story(session, story_id)
        is_last_episode = number == story.total_episodes
        act = act_for_episode(session, story_id, number)
        ends_act = act is not None and act.last_episode == number
        if is_last_episode:
            story.status = "finished"

    evaluation.log_human_decision(trace_run_id, "approved")

    if number % config.STORY_SO_FAR_EVERY == 0 or ends_act:
        refresh_story_so_far(story_id, number)
    if ends_act:
        summarise_act(story_id, number)


def edit_episode(story_id: int, number: int, new_text: str, new_title: str | None = None) -> None:
    """A human rewrites an episode. Works on drafts under review and on already-approved history."""
    if not new_text.strip():
        raise NotAllowed("The episode text can't be empty.")
    with session_scope() as session:
        episode = get_episode(session, story_id, number)
        if episode.status not in ("in_review", "approved"):
            raise NotAllowed(f"Episode {number} has no text to edit yet.")
        was_approved = episode.status == "approved"
        trace_run_id = episode.critic_report.get("trace_run_id")

    evaluation.log_human_decision(trace_run_id, "edited", "approved episode rewritten" if was_approved else "draft edited before approval")

    update = extract_memory(story_id, number, new_text)

    with session_scope() as session:
        episode = get_episode(session, story_id, number)
        episode.text = new_text
        episode.title = new_title or episode.title
        episode.was_edited_by_human = True
        if not was_approved:
            episode.pending_memory = update.model_dump()
            return
        forget_episode(session, story_id, number)
        commit_memory(session, story_id, number, update)
        mark_later_drafts_stale(session, story_id, number)
        story = get_story(session, story_id)
        rebuild_recap_through = story.story_so_far_through
        if rebuild_recap_through >= number:
            story.story_so_far, story.story_so_far_through = "", 0

    if rebuild_recap_through >= number:
        refresh_story_so_far(story_id, rebuild_recap_through)


def mark_later_drafts_stale(session, story_id: int, number: int) -> None:
    """Unapproved drafts after an edited episode were written against old memory."""
    for episode in all_episodes(session, story_id):
        if episode.number > number and episode.status == "in_review":
            episode.status = "stale"
            episode.pending_memory = {}


def reject_episode(story_id: int, number: int, reason: str) -> None:
    with session_scope() as session:
        episode = get_episode(session, story_id, number)
        if episode.status not in ("in_review", "failed", "stale"):
            raise NotAllowed(f"Episode {number} is '{episode.status}' and can't be rejected.")
        evaluation.log_human_decision(episode.critic_report.get("trace_run_id"), "rejected", reason.strip())
        episode.status = "planned"
        episode.human_note = reason.strip()
        episode.pending_memory = {}


@traceable(name="give_feedback")
def give_feedback(story_id: int, text: str, expires_after_episode: int = 0) -> Directive:
    """Save feedback as a standing instruction and re-plan the next beats around it."""
    if not text.strip():
        raise NotAllowed("Feedback can't be empty.")
    with session_scope() as session:
        approved = [e.number for e in all_episodes(session, story_id) if e.status == "approved"]
        after_episode = max(approved, default=0)
        directive = Directive(
            story_id=story_id, text=text.strip(), given_after_episode=after_episode,
            expires_after_episode=expires_after_episode,
        )
        session.add(directive)
        session.flush()
        directive_id = directive.id

    # Only unwritten beats are re-planned. A draft already waiting for review stays as it is:
    # the human decides whether to approve it or reject it with the same note.
    what_changed = replan_upcoming_beats(story_id, text, after_episode)
    evaluation.log_feedback(evaluation.current_trace_run_id(), "story_direction", value=text.strip(), comment=what_changed)

    with session_scope() as session:
        directive = session.get(Directive, directive_id)
        directive.replan_summary = what_changed
    return directive


def retire_directive(story_id: int, directive_id: int) -> None:
    with session_scope() as session:
        directive = session.get(Directive, directive_id)
        if directive is None or directive.story_id != story_id:
            raise NotAllowed("No such instruction.")
        directive.is_active = False


def recover_interrupted_work() -> None:
    """After a restart, anything that was mid-flight is marked failed so it can be retried."""
    with session_scope() as session:
        for episode in session.scalars(select(Episode).where(Episode.status == "drafting")):
            episode.status, episode.error = "failed", "Interrupted by a server restart. Write it again."
        for job in session.scalars(select(Job).where(Job.status == "running")):
            job.status, job.detail = "failed", "Interrupted by a server restart."
