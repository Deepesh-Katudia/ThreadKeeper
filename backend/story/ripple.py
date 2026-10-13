"""Ripple review: what happens to the rest of the story when a human edits an approved episode.

Editing episode 5 used to rebuild episode 5's memory and stop there, so episode 6 could go on
describing a handprint that no longer exists. A ripple is a tracked change request with three
human gates:

  1. confirm_memory  the edit is saved as a pending version and the memory diff is shown.
                     Nothing in canon changes until the human confirms (and can trim) it.
  2. reviewing       later episodes are checked cheapest-first (see ripple_scan) and each flagged
                     one gets a proposed fix. The human accepts, edits, keeps or asks for a
                     rewrite, in episode order. An accepted fix can itself change canon, so
                     later episodes are re-checked (the cascade), within the window and cost cap.
  3. replan_review   recaps are rebuilt and the planner proposes new upcoming beats. Nothing is
                     written to the plan until the human approves.

While a ripple is open, writing and other edits wait, the same way they wait for a draft in review.
"""

from datetime import datetime, timezone

from langsmith import traceable
from sqlalchemy import select

from story import config, evaluation
from story.db import session_scope
from story.errors import NotAllowed
from story.memory import refresh_story_so_far, summarise_act
from story.memory_diff import extract_diff, validate_diff
from story.models import EpisodeVersion, Ripple, RippleItem
from story.planner import apply_replan, propose_replan
from story.queries import NotFound, acts, all_episodes, episodes_between, get_episode, get_story, get_version
from story.ripple_scan import (
    canon_between, change_lines, changes_anything, check_episode, describe_change, propose_patch, ripple_cost,
    signals_for,
)
from story.schemas import MemoryDiff
from story.versions import apply_version, ensure_v1, restore_diff, save_version, text_hash, version_with_same_text

OPEN = ("confirm_memory", "scanning", "reviewing", "replan_review")
DECISIONS = ("accept", "edit", "keep", "rewrite")


# --- Looking things up ------------------------------------------------------------------


def open_ripple(session, story_id: int) -> Ripple | None:
    return session.scalar(select(Ripple).where(Ripple.story_id == story_id, Ripple.status.in_(OPEN)))


def block_if_open(session, story_id: int) -> None:
    ripple = open_ripple(session, story_id)
    if ripple is not None:
        raise NotAllowed(f"Finish the ripple review for episode {ripple.source_episode} first.")


def get_ripple(session, story_id: int, ripple_id: int, status: str | None = None) -> Ripple:
    ripple = session.get(Ripple, ripple_id)
    if ripple is None or ripple.story_id != story_id:
        raise NotFound(f"ripple {ripple_id} does not exist in story {story_id}")
    if status and ripple.status != status:
        raise NotAllowed(f"This ripple is at '{ripple.status}', not '{status}'.")
    return ripple


def items_of(session, ripple_id: int) -> list[RippleItem]:
    return list(session.scalars(
        select(RippleItem).where(RippleItem.ripple_id == ripple_id).order_by(RippleItem.episode_number)
    ))


def get_item(session, ripple_id: int, number: int) -> RippleItem:
    item = next((i for i in items_of(session, ripple_id) if i.episode_number == number), None)
    if item is None:
        raise NotFound(f"episode {number} is not part of ripple {ripple_id}")
    return item


def needs_decision(item: RippleItem) -> bool:
    return item.decision is None and item.check_status != "unaffected"


def trace_of(session, story_id: int, number: int) -> str | None:
    return (get_episode(session, story_id, number).critic_report or {}).get("trace_run_id")


# --- Starting, and gate 1 ---------------------------------------------------------------


@traceable(name="ripple_start")
def start_ripple(story_id: int, number: int, new_text: str, new_title: str | None = None) -> int:
    """Save the edit as a pending version and work out what memory would change. Canon is untouched."""
    with session_scope() as session:
        block_if_open(session, story_id)
        ensure_v1(session, story_id, number)
        episode = get_episode(session, story_id, number)
        if text_hash(new_text) == text_hash(episode.text):
            raise NotAllowed("That is already the episode's text.")
        ripple = Ripple(story_id=story_id, source_episode=number, from_version=episode.current_version or 1)
        session.add(ripple)
        session.flush()
        same = version_with_same_text(session, story_id, number, new_text)
        staled = park_later_drafts(session, story_id, number)
        if same is not None:  # going back to a known version: the diff is worked out in code
            diff, reactivate = restore_diff(session, story_id, number, same)
            ripple.to_version = same.version
            ripple.memory_diff = diff_record(session, story_id, number, diff, staled, same.version, reactivate)
            return ripple.id
        row = save_version(
            session, story_id, number, new_title or episode.title, new_text, "human_edit", ripple_id=ripple.id,
        )
        ripple.to_version = row.version
        ripple.memory_diff = {"staled": staled}
        ripple_id, old_text = ripple.id, episode.text

    try:
        diff = extract_diff(story_id, number, old_text, new_text)
    except Exception:
        cancel_ripple(story_id, ripple_id)
        raise
    with session_scope() as session:
        ripple = session.get(Ripple, ripple_id)
        ripple.memory_diff = diff_record(session, story_id, number, diff, ripple.memory_diff["staled"])
        ripple.cost_usd = ripple_cost(session, ripple)
    return ripple_id


def diff_record(session, story_id, number, diff, staled, restore_version=None, reactivate=None) -> dict:
    return {
        "diff": diff.model_dump(), "change": describe_change(session, story_id, number, diff),
        "restore_version": restore_version, "reactivate_fact_ids": reactivate or [], "staled": staled,
    }


def park_later_drafts(session, story_id: int, number: int) -> list[dict]:
    """Drafts after the edit were written against old memory: mark them stale, but remember them for a cancel."""
    parked = []
    for episode in all_episodes(session, story_id):
        if episode.number > number and episode.status == "in_review":
            parked.append({"number": episode.number, "pending_memory": episode.pending_memory})
            episode.status, episode.pending_memory = "stale", {}
    return parked


@traceable(name="ripple_confirm_memory")
def confirm_memory(story_id: int, ripple_id: int, edited_diff: dict | None = None) -> None:
    """Gate 1. Apply the (possibly trimmed) memory diff and line up the later episodes to check."""
    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id, "confirm_memory")
        record, number = ripple.memory_diff or {}, ripple.source_episode
        diff = validate_diff(session, story_id, number, MemoryDiff.model_validate(edited_diff or record["diff"]))
        change = describe_change(session, story_id, number, diff)
        row = get_version(session, story_id, number, ripple.to_version)
        reactivate = record.get("reactivate_fact_ids") if record.get("restore_version") else None
        apply_version(session, story_id, number, row, diff, reactivate, ripple.id)
        get_episode(session, story_id, number).was_edited_by_human = True
        ripple.memory_diff = {**record, "diff": diff.model_dump(), "change": change}
        ripple.status = "scanning"
        window = episodes_between(session, story_id, number + 1, number + config.RIPPLE_WINDOW)
        for episode in window:
            if episode.status == "approved":
                session.add(RippleItem(ripple_id=ripple.id, episode_number=episode.number))
                episode.continuity = {"ripple_id": ripple.id, "check_status": "pending", "decision": None}
        trace = trace_of(session, story_id, number)
    evaluation.log_human_decision(trace, "ripple_memory_confirmed", f"ripple {ripple_id}")


def cancel_ripple(story_id: int, ripple_id: int) -> None:
    """Only before the memory is confirmed: drop the pending version; canon was never changed."""
    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id, "confirm_memory")
        record = ripple.memory_diff or {}
        if not record.get("restore_version"):
            pending = session.scalar(select(EpisodeVersion).where(
                EpisodeVersion.story_id == story_id, EpisodeVersion.episode_number == ripple.source_episode,
                EpisodeVersion.version == ripple.to_version, EpisodeVersion.ripple_id == ripple.id,
            ))
            if pending is not None:
                session.delete(pending)
        for parked in record.get("staled", []):
            episode = get_episode(session, story_id, parked["number"])
            if episode.status == "stale":
                episode.status, episode.pending_memory = "in_review", parked["pending_memory"]
        ripple.status, ripple.closed_at = "cancelled", datetime.now(timezone.utc)
        ripple.summary = "Cancelled before the memory changed."


# --- Scanning ----------------------------------------------------------------------------


@traceable(name="ripple_scan")
def scan(story_id: int, ripple_id: int) -> str:
    """Check every later episode in the window, cheapest tier first."""
    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id, "scanning")
        numbers = [i.episode_number for i in items_of(session, ripple_id)]
        change, source = ripple.memory_diff["change"], ripple.source_episode
    check_items(story_id, ripple_id, numbers, change, source, recheck=False)
    with session_scope() as session:
        get_ripple(session, story_id, ripple_id).status = "reviewing"
    return finish_if_decided(story_id, ripple_id) or progress_message(story_id, ripple_id)


def check_items(story_id: int, ripple_id: int, numbers: list[int], change: dict, source: int, recheck: bool) -> None:
    for number in numbers:
        if not check_one(story_id, ripple_id, number, change, source, recheck):
            with session_scope() as session:
                ripple = get_ripple(session, story_id, ripple_id)
                ripple.summary = (
                    f"Stopped checking at episode {number}: this ripple reached its "
                    f"${config.RIPPLE_COST_CAP_USD:.2f} cost cap. Unchecked episodes are marked pending."
                )
            return


def check_one(story_id: int, ripple_id: int, number: int, change: dict, source: int, recheck: bool) -> bool:
    """Run the tiers on one episode. Returns False when the cost cap stopped it."""
    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id)
        item, episode = get_item(session, ripple_id, number), get_episode(session, story_id, number)
        reasons = signals_for(episode, source, change)
        if not reasons:
            if not recheck:
                set_check(session, story_id, item, "unaffected", {"reasons": [], "verdict": None}, [], None)
            return True
        if ripple_cost(session, ripple) >= config.RIPPLE_COST_CAP_USD:
            set_check(session, story_id, item, "pending", {"reasons": reasons, "verdict": None}, [], None)
            return False
        page = {"number": number, "text": episode.text, "title": episode.title}
        canon = canon_between(session, story_id, ripple.source_episode, number)
        retcon = get_story(session, story_id).history_mode == "retcon"

    change_text = change_lines(source, change)
    verdict, conflicts = check_episode(story_id, number, page["text"], change_text, canon)
    proposal = None
    if verdict != "unaffected" and not retcon and within_cap(story_id, ripple_id):
        proposal = propose_patch(story_id, page, change_text, conflicts)

    with session_scope() as session:
        item = get_item(session, ripple_id, number)
        status = "recheck" if recheck and verdict != "unaffected" else verdict
        set_check(session, story_id, item, status, {"reasons": reasons, "verdict": verdict}, conflicts, proposal)
        if retcon and verdict != "unaffected":
            record_decision(session, story_id, item, "keep", "Retcon mode: published episodes stay as they are.")
        ripple = get_ripple(session, story_id, ripple_id)
        ripple.cost_usd = ripple_cost(session, ripple)
    return True


def within_cap(story_id: int, ripple_id: int) -> bool:
    with session_scope() as session:
        return ripple_cost(session, get_ripple(session, story_id, ripple_id)) < config.RIPPLE_COST_CAP_USD


def set_check(session, story_id: int, item: RippleItem, status: str, signals: dict, conflicts, proposal) -> None:
    item.check_status, item.signals, item.conflicts, item.proposal = status, signals, conflicts, proposal
    update_continuity(session, story_id, item)


def update_continuity(session, story_id: int, item: RippleItem) -> None:
    get_episode(session, story_id, item.episode_number).continuity = {
        "ripple_id": item.ripple_id, "check_status": item.check_status, "decision": item.decision,
        "resulting_version": item.resulting_version, "fix_kind": (item.proposal or {}).get("kind"),
    }


# --- Gate 2: deciding, episode by episode ----------------------------------------------------


@traceable(name="ripple_decide")
def decide_item(story_id: int, ripple_id: int, number: int, decision: str, text: str | None = None, note: str = "") -> str:
    """The human's call on one later episode. Items are decided in episode order."""
    proposal = check_decision(story_id, ripple_id, number, decision, text)
    if decision == "keep":
        with session_scope() as session:
            record_decision(session, story_id, get_item(session, ripple_id, number), "keep", note or "Kept as written.")
    elif decision == "rewrite":
        return propose_rewrite(story_id, ripple_id, number)
    else:
        if decision == "accept":
            new_text, title = proposal["text"], proposal.get("title")
            source = "ripple_patch" if proposal.get("kind") == "patch" else "ripple_rewrite"
        else:
            new_text, title, source = text, None, "human_edit"
        change = apply_new_text(story_id, ripple_id, number, new_text, title, source)
        with session_scope() as session:
            record_decision(session, story_id, get_item(session, ripple_id, number), decision, note)
        if changes_anything(change):
            cascade(story_id, ripple_id, number, change)
    return finish_if_decided(story_id, ripple_id) or progress_message(story_id, ripple_id)


def check_decision(story_id: int, ripple_id: int, number: int, decision: str, text: str | None) -> dict:
    if decision not in DECISIONS:
        raise NotAllowed(f"Decision must be one of: {', '.join(DECISIONS)}.")
    with session_scope() as session:
        get_ripple(session, story_id, ripple_id, "reviewing")
        items = items_of(session, ripple_id)
        item = get_item(session, ripple_id, number)
        if not needs_decision(item):
            raise NotAllowed(f"Episode {number} doesn't need a decision.")
        earlier = next((i.episode_number for i in items if i.episode_number < number and needs_decision(i)), None)
        if earlier is not None:
            raise NotAllowed(f"Decide episode {earlier} first: later episodes depend on it.")
        proposal = item.proposal or {}
    if decision == "accept" and not proposal.get("text"):
        raise NotAllowed("There is no ready fix to accept. Edit it yourself, keep it, or ask for a rewrite.")
    if decision == "edit" and not (text or "").strip():
        raise NotAllowed("The episode text can't be empty.")
    return proposal


def record_decision(session, story_id: int, item: RippleItem, decision: str, note: str) -> None:
    item.decision, item.decision_note, item.decided_at = decision, note, datetime.now(timezone.utc)
    update_continuity(session, story_id, item)
    evaluation.log_human_decision(trace_of(session, story_id, item.episode_number), f"ripple_{decision}", note)


def apply_new_text(story_id: int, ripple_id: int, number: int, new_text: str, title: str | None, source: str) -> dict:
    """A later episode gets new text: a new version, and its memory changed by difference."""
    with session_scope() as session:
        ensure_v1(session, story_id, number)
        old_text = get_episode(session, story_id, number).text
    diff = extract_diff(story_id, number, old_text, new_text)
    with session_scope() as session:
        episode = get_episode(session, story_id, number)
        change = describe_change(session, story_id, number, diff)
        row = save_version(session, story_id, number, title or episode.title, new_text, source, ripple_id=ripple_id)
        apply_version(session, story_id, number, row, diff, None, ripple_id)
        episode.was_edited_by_human = True
        get_item(session, ripple_id, number).resulting_version = row.version
    return change


def propose_rewrite(story_id: int, ripple_id: int, number: int) -> str:
    """A full new draft, written against the corrected canon. It is a proposal like any patch."""
    from story.pipeline import draft_until_good_enough  # pipeline imports this module

    with session_scope() as session:
        item = get_item(session, ripple_id, number)
        note = "Keep this episode's events, but fix what now contradicts canon: " + "; ".join(
            f"\"{c['quote']}\" ({c['reason']})" for c in item.conflicts or []
        )
    spent = lambda: ripple_spent(story_id, ripple_id)  # noqa: E731
    _, draft, _, _ = draft_until_good_enough(
        story_id, number, note, step_prefix="ripple_", budget=(spent, config.RIPPLE_COST_CAP_USD),
    )
    with session_scope() as session:
        item = get_item(session, ripple_id, number)
        item.proposal = {"kind": "rewrite", "edits": [], "text": draft.text, "title": draft.title, "note": "Full rewrite."}
        ripple = get_ripple(session, story_id, ripple_id)
        ripple.cost_usd = ripple_cost(session, ripple)
    return f"A rewrite of episode {number} is ready. Accept it, or edit it yourself."


def ripple_spent(story_id: int, ripple_id: int) -> float:
    with session_scope() as session:
        return ripple_cost(session, get_ripple(session, story_id, ripple_id))


def cascade(story_id: int, ripple_id: int, number: int, change: dict) -> None:
    """A fix to episode `number` changed canon too, so re-check the undecided episodes after it."""
    with session_scope() as session:
        later = [i.episode_number for i in items_of(session, ripple_id) if i.episode_number > number and i.decision is None]
    check_items(story_id, ripple_id, later, change, number, recheck=True)


def accept_all_minor(story_id: int, ripple_id: int) -> str:
    """Accept every ready minor fix, in order, stopping at the first episode that needs a human."""
    accepted = 0
    while True:
        with session_scope() as session:
            get_ripple(session, story_id, ripple_id, "reviewing")
            nxt = next((i for i in items_of(session, ripple_id) if needs_decision(i)), None)
            ready = nxt is not None and nxt.check_status == "minor" and (nxt.proposal or {}).get("kind") == "patch"
            number = nxt.episode_number if nxt else None
        if not ready:
            stop = f" Episode {number} needs your decision." if number else ""
            return f"Accepted {accepted} minor fixes.{stop}"
        decide_item(story_id, ripple_id, number, "accept", note="Accepted with 'accept all minor'.")
        accepted += 1
        with session_scope() as session:
            if get_ripple(session, story_id, ripple_id).status != "reviewing":
                return f"Accepted {accepted} minor fixes."


def progress_message(story_id: int, ripple_id: int) -> str:
    with session_scope() as session:
        waiting = [i.episode_number for i in items_of(session, ripple_id) if needs_decision(i)]
    return f"{len(waiting)} episodes need your decision: {waiting}." if waiting else "Every episode is decided."


# --- Gate 3: recaps and new beats ---------------------------------------------------------------


def finish_if_decided(story_id: int, ripple_id: int) -> str | None:
    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id)
        if ripple.status != "reviewing" or any(needs_decision(i) for i in items_of(session, ripple_id)):
            return None
    return finish_review(story_id, ripple_id)


@traceable(name="ripple_replan")
def finish_review(story_id: int, ripple_id: int) -> str:
    """Rebuild recaps over the changed history, then propose (not apply) new upcoming beats."""
    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id)
        number = ripple.source_episode
        touched = [number] + [i.episode_number for i in items_of(session, ripple_id) if i.resulting_version]
        story = get_story(session, story_id)
        recap_through = story.story_so_far_through
        if recap_through >= number:
            story.story_so_far, story.story_so_far_through = "", 0
        summarised_acts = [
            a.last_episode for a in acts(session, story_id)
            if a.summary and a.first_episode <= max(touched) and a.last_episode >= min(touched)
        ]
        written = [e.number for e in all_episodes(session, story_id) if e.status == "approved"]
        now_true = change_lines(number, ripple.memory_diff["change"])
        feedback = f"Editor changed episode {number}. What is now true: {now_true} Make upcoming beats follow from this."

    if recap_through >= number:
        refresh_story_so_far(story_id, recap_through, step_prefix="ripple_")
    for last_episode in summarised_acts:
        summarise_act(story_id, last_episode, step_prefix="ripple_")
    what_changed, changes = propose_replan(story_id, feedback, max(written, default=0), step="ripple_replan")

    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id)
        ripple.replan = {"what_changed": what_changed, "changes": changes, "applied": []}
        ripple.status = "replan_review"
        ripple.cost_usd = ripple_cost(session, ripple)
    return f"Every episode is decided. {len(changes)} upcoming beats are proposed for your approval."


def approve_replan(story_id: int, ripple_id: int, keep_episode_numbers: list[int] | None = None) -> None:
    """Gate 3. Apply the chosen beat changes and close the ripple; writing can resume."""
    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id, "replan_review")
        changes = (ripple.replan or {}).get("changes", [])
        chosen = [c for c in changes if keep_episode_numbers is None or c["episode"] in keep_episode_numbers]
    apply_replan(story_id, chosen)
    with session_scope() as session:
        ripple = get_ripple(session, story_id, ripple_id)
        ripple.replan = {**ripple.replan, "applied": [c["episode"] for c in chosen]}
        ripple.status, ripple.closed_at = "closed", datetime.now(timezone.utc)
        ripple.summary = (ripple.summary + " " if ripple.summary else "") + closing_summary(items_of(session, ripple_id), chosen)
        ripple.cost_usd = ripple_cost(session, ripple)
        trace = trace_of(session, story_id, ripple.source_episode)
    evaluation.log_human_decision(trace, "ripple_closed", f"applied {len(chosen)} beat changes")


def closing_summary(items: list[RippleItem], applied: list[dict]) -> str:
    def count(test) -> int:
        return sum(1 for i in items if test(i))
    return (
        f"Checked {len(items)} later episodes: {count(lambda i: i.check_status == 'unaffected')} unaffected, "
        f"{count(lambda i: i.decision in ('accept', 'edit'))} changed, {count(lambda i: i.decision == 'keep')} kept. "
        f"{len(applied)} upcoming beats changed."
    )


def start_restore(story_id: int, number: int, version: int) -> int:
    """Going back to an earlier version is an edit like any other, with a diff worked out in code."""
    with session_scope() as session:
        row = get_version(session, story_id, number, version)
        if get_episode(session, story_id, number).current_version == version:
            raise NotAllowed(f"Version {version} is already the current one.")
        text, title = row.text, row.title
    return start_ripple(story_id, number, text, title)
