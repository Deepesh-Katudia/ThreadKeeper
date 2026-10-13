"""Changing an approved episode's memory by difference, not by starting again.

Re-extracting an edited episode from scratch gave different memory each time, even for the
same text: facts the edit never touched were reworded, new threads appeared. So for edits the
extractor sees the old text, the new text and the current records *with their ids*, and returns
only what changed. Code then checks every id it returned, and applies the change by retracting
(never deleting) facts, so any earlier version can be restored exactly.
"""

from langsmith import traceable

from story import config, llm, prompts
from story.db import session_scope
from story.memory import best_thread_match, can_resolve_in, known_by, open_threads_at
from story.models import Character, Fact, Thread
from story.queries import characters, episode_facts, episodes_between, find_character, get_episode, threads
from story.schemas import MemoryDiff


@traceable(name="ripple_diff")
def extract_diff(story_id: int, number: int, old_text: str, new_text: str) -> MemoryDiff:
    with session_scope() as session:
        fact_lines = "\n".join(
            f"[{f.id}] {f.subject}: {f.statement}" for f in episode_facts(session, story_id, number)
        ) or "(none)"
        thread_lines = "\n".join(
            f"[{t.id}] {t.title} ({describe_thread_state(t, number)})" for t in threads_known_at(session, story_id, number)
        ) or "(none)"
        cast_lines = "\n".join(
            f"[{c.id}] {c.name} ({c.status}{', first seen in this episode' if c.first_episode == number else ''})"
            for c in known_by(session, story_id, number)
        ) or "(none)"
    diff = llm.write_json(
        "ripple_diff", prompts.extractor_system(),
        prompts.diff_prompt(number, old_text, new_text, fact_lines, thread_lines, cast_lines),
        MemoryDiff, config.EXTRACTOR_MODEL, story_id=story_id, episode=number, max_tokens=4000, temperature=0,
    )
    with session_scope() as session:
        return validate_diff(session, story_id, number, diff)


def threads_known_at(session, story_id: int, number: int) -> list[Thread]:
    """Threads open by this episode, plus the ones this episode itself resolved."""
    resolved_here = [t for t in threads(session, story_id, ("resolved",)) if t.resolved_episode == number]
    return open_threads_at(session, story_id, number) + resolved_here


def describe_thread_state(thread: Thread, number: int) -> str:
    if thread.status == "resolved" and thread.resolved_episode == number:
        return "resolved in this episode"
    if thread.opened_episode == number:
        return "opened in this episode"
    return f"open since ep {thread.opened_episode}"


def validate_diff(session, story_id: int, number: int, diff: MemoryDiff) -> MemoryDiff:
    """Keep only ids that belong to this episode and story, and changes that respect time order."""
    own_facts = {f.id for f in episode_facts(session, story_id, number)}
    own_characters = {c.id for c in characters(session, story_id) if c.first_episode == number}
    all_threads = {t.id: t for t in threads(session, story_id)}
    new_names = {c.name.lower() for c in diff.new_characters}

    def can_change(name: str) -> bool:
        person = find_character(session, story_id, name)
        return (person is not None and person.first_episode <= number) or name.lower() in new_names

    return diff.model_copy(update={
        "retract_fact_ids": unique(i for i in diff.retract_fact_ids if i in own_facts),
        "remove_character_ids": unique(i for i in diff.remove_character_ids if i in own_characters),
        "character_changes": [c for c in diff.character_changes if can_change(c.name)],
        "resolve_thread_ids": unique(
            i for i in diff.resolve_thread_ids if i in all_threads and can_resolve_in(all_threads[i], number)
        ),
        "reopen_thread_ids": unique(
            i for i in diff.reopen_thread_ids if i in all_threads and all_threads[i].resolved_episode == number
        ),
        "remove_thread_ids": unique(
            i for i in diff.remove_thread_ids if i in all_threads and is_invented_by(all_threads[i], number)
        ),
    })


def is_invented_by(thread: Thread, number: int) -> bool:
    """A thread this episode made up (not the arc plan's) and no later episode has answered."""
    return (
        thread.opened_episode == number and thread.payoff_episode == 0
        and thread.resolved_episode in (0, number)
    )


def unique(ids) -> list[int]:
    return list(dict.fromkeys(ids))


def apply_diff(
    session, story_id: int, number: int, diff: MemoryDiff, version: int,
    reason: str = "", ripple_id: int | None = None, reactivate_fact_ids: list[int] | None = None,
) -> None:
    """Make canon match the edited episode. Facts are retracted, never deleted."""
    episode = get_episode(session, story_id, number)
    episode.summary, episode.hook = diff.summary, diff.hook
    episode.characters_present = diff.characters_present

    for fact in episode_facts(session, story_id, number, active_only=False):
        if fact.id in diff.retract_fact_ids:
            fact.is_active, fact.retracted_reason, fact.retracted_by_ripple = False, reason, ripple_id
        elif fact.id in (reactivate_fact_ids or []):
            fact.is_active, fact.retracted_reason, fact.retracted_by_ripple = True, None, None
    for fact in diff.new_facts:
        session.add(Fact(
            story_id=story_id, subject=fact.subject, statement=fact.statement,
            source_episode=number, source_version=version, is_active=True,
        ))

    apply_character_changes(session, story_id, number, diff)
    apply_thread_changes(session, story_id, number, diff)
    session.flush()


def apply_character_changes(session, story_id: int, number: int, diff: MemoryDiff) -> None:
    for person in characters(session, story_id):
        if person.id in diff.remove_character_ids:
            remove_character(session, story_id, number, person)
    session.flush()

    for person in diff.new_characters:
        existing = find_character(session, story_id, person.name)
        if existing is not None and existing.first_episode > number:
            existing.first_episode = number  # they now appear earlier than they used to
        elif existing is None:
            session.add(Character(
                story_id=story_id, name=person.name, role=person.role or "minor",
                description=person.description, first_episode=number, last_seen_episode=number,
            ))
    session.flush()

    for name in diff.characters_present:
        person = find_character(session, story_id, name)
        if person is not None:
            person.last_seen_episode = max(person.last_seen_episode, number)

    for change in diff.character_changes:
        person = find_character(session, story_id, change.name)
        if person is None:
            continue
        status = change.new_status.lower()
        if status == "alive" and person.status_changed_in == number:
            person.status, person.status_changed_in = "alive", 0  # this episode no longer changes them
        else:
            person.status, person.status_changed_in = status, number


def remove_character(session, story_id: int, number: int, person: Character) -> None:
    """Someone this episode introduced is gone from it. If a later episode has them, they start there."""
    later = [e for e in episodes_between(session, story_id, number + 1, 100_000) if e.status == "approved"]
    appears_in = next((e.number for e in later if mentions_name(e.characters_present or [], person.name)), None)
    if appears_in is None:
        session.delete(person)
    else:
        person.first_episode = appears_in


def mentions_name(names: list[str], name: str) -> bool:
    wanted = {name.lower(), name.lower().split()[0]}
    return any(n.lower() in wanted or n.lower().split()[0] in wanted for n in names if n.strip())


def apply_thread_changes(session, story_id: int, number: int, diff: MemoryDiff) -> None:
    all_threads = threads(session, story_id)
    for thread in all_threads:
        if thread.id in diff.remove_thread_ids:
            session.delete(thread)
        elif thread.id in diff.reopen_thread_ids:
            thread.status, thread.resolved_episode = "open", 0
        elif thread.id in diff.resolve_thread_ids:
            thread.status, thread.resolved_episode = "resolved", number
    remaining = [t for t in all_threads if t.id not in diff.remove_thread_ids]
    for opened in diff.threads_opened:
        existing = best_thread_match(remaining, opened.title)
        if existing is None:
            session.add(Thread(
                story_id=story_id, title=opened.title, description=opened.description,
                opened_episode=number, status="open",
            ))
        elif existing.status == "planned":
            existing.status = "open"


def is_empty(diff: MemoryDiff) -> bool:
    """True when the diff changes nothing beyond the summary text."""
    return not any((
        diff.retract_fact_ids, diff.new_facts, diff.new_characters, diff.remove_character_ids,
        diff.character_changes, diff.threads_opened, diff.remove_thread_ids,
        diff.resolve_thread_ids, diff.reopen_thread_ids,
    ))
