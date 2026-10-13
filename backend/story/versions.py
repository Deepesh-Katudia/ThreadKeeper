"""Every text an approved episode has had, and how to go back to one.

Each version stores the memory it produced and the exact facts that were active after it. That
makes undo a lookup instead of a re-extraction: restoring version 1 re-activates version 1's
facts and puts characters and threads back the way version 1 left them, with no model call, so
the same text always gives the same canon.

Episodes approved before versions existed have none. The first time one is needed, version 1 is
built from what is in canon for that episode right now (`ensure_v1`).
"""

import hashlib

from sqlalchemy import func, select

from story.memory import best_thread_match, load_update
from story.memory_diff import apply_diff, is_invented_by, validate_diff
from story.models import EpisodeVersion
from story.queries import (
    characters, episode_facts, find_character, get_episode, threads, versions_of,
)
from story.schemas import CharacterChange, MemoryDiff, MemoryUpdate, NewCharacter, NewFact, ThreadOpened


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def save_version(
    session, story_id: int, number: int, title: str, text: str, source: str,
    memory: dict | None = None, note: str = "", ripple_id: int | None = None,
) -> EpisodeVersion:
    latest = session.scalar(select(func.max(EpisodeVersion.version)).where(
        EpisodeVersion.story_id == story_id, EpisodeVersion.episode_number == number,
    ))
    row = EpisodeVersion(
        story_id=story_id, episode_number=number, version=(latest or 0) + 1, title=title, text=text,
        text_hash=text_hash(text), memory=memory, source=source, note=note, ripple_id=ripple_id,
    )
    session.add(row)
    session.flush()
    return row


def version_with_same_text(session, story_id: int, number: int, text: str) -> EpisodeVersion | None:
    wanted = text_hash(text)
    return next((v for v in versions_of(session, story_id, number) if v.text_hash == wanted and v.memory), None)


# --- What a version left in canon ---------------------------------------------------


def snapshot_memory(session, story_id: int, number: int) -> MemoryUpdate:
    """This episode's footprint in canon right now, as a MemoryUpdate."""
    episode = get_episode(session, story_id, number)
    cast = characters(session, story_id)
    all_threads = threads(session, story_id)
    resolved_here = [t for t in all_threads if t.status == "resolved" and t.resolved_episode == number]
    return MemoryUpdate(
        summary=episode.summary, hook=episode.hook, characters_present=list(episode.characters_present or []),
        new_characters=[
            NewCharacter(name=c.name, role=c.role, description=c.description) for c in cast if c.first_episode == number
        ],
        character_changes=[
            CharacterChange(name=c.name, new_status=c.status, reason="") for c in cast if c.status_changed_in == number
        ],
        new_facts=[NewFact(subject=f.subject, statement=f.statement) for f in episode_facts(session, story_id, number)],
        threads_opened=[
            ThreadOpened(title=t.title, description=t.description)
            for t in all_threads if t.opened_episode == number and t.payoff_episode == 0
        ],
        resolved_thread_ids=[t.id for t in resolved_here],
        threads_resolved=[t.title for t in resolved_here],
    )


def memory_record(session, story_id: int, number: int) -> dict:
    """What gets stored on a version: its memory plus the ids of the facts active after it."""
    return {
        **snapshot_memory(session, story_id, number).model_dump(),
        "fact_ids": [f.id for f in episode_facts(session, story_id, number)],
    }


def stored_update(version: EpisodeVersion) -> MemoryUpdate:
    fields = {k: v for k, v in (version.memory or {}).items() if k in MemoryUpdate.model_fields}
    return load_update(fields)


def record_written_version(session, story_id: int, number: int) -> EpisodeVersion:
    """Called on approval: the text the human approved becomes the episode's first version."""
    episode = get_episode(session, story_id, number)
    row = save_version(
        session, story_id, number, episode.title, episode.text, "written", memory_record(session, story_id, number),
    )
    episode.current_version = row.version
    return row


def ensure_v1(session, story_id: int, number: int) -> None:
    """Give an episode approved before versions existed a version 1, built from current canon."""
    episode = get_episode(session, story_id, number)
    if episode.status != "approved" or versions_of(session, story_id, number):
        return
    for fact in episode_facts(session, story_id, number, active_only=False):
        if fact.source_version is None:
            fact.source_version = 1
    session.flush()
    row = save_version(
        session, story_id, number, episode.title, episode.text, "written",
        memory_record(session, story_id, number), note="Recorded from canon (episode predates versions).",
    )
    episode.current_version = row.version


# --- Going back to a version -------------------------------------------------------


def restore_diff(session, story_id: int, number: int, target: EpisodeVersion) -> tuple[MemoryDiff, list[int]]:
    """The change that takes canon from now back to `target`, worked out in code.

    Returns the diff and the ids of retracted facts to bring back.
    """
    wanted = stored_update(target)
    wanted_fact_ids = set((target.memory or {}).get("fact_ids", []))
    own_facts = episode_facts(session, story_id, number, active_only=False)
    is_active = {f.id: f.is_active is not False for f in own_facts}

    diff = MemoryDiff(
        summary=wanted.summary, hook=wanted.hook, characters_present=wanted.characters_present,
        retract_fact_ids=[i for i, active in is_active.items() if active and i not in wanted_fact_ids],
        new_facts=[],
        **character_restore(session, story_id, number, wanted),
        **thread_restore(session, story_id, number, wanted),
    )
    reactivate = [i for i, active in is_active.items() if not active and i in wanted_fact_ids]
    return validate_diff(session, story_id, number, diff), reactivate


def character_restore(session, story_id: int, number: int, wanted: MemoryUpdate) -> dict:
    cast = characters(session, story_id)
    wanted_names = {c.name.lower() for c in wanted.new_characters}
    wanted_changes = {c.name.lower(): c for c in wanted.character_changes}
    changes = []
    for change in wanted.character_changes:
        person = find_character(session, story_id, change.name)
        if person is None or person.status != change.new_status or person.status_changed_in != number:
            changes.append(change)
    for person in cast:  # changes made here now that the target version didn't make
        if person.status_changed_in == number and person.name.lower() not in wanted_changes:
            changes.append(CharacterChange(name=person.name, new_status="alive", reason="restored"))
    return {
        "new_characters": [c for c in wanted.new_characters if not introduced_here(session, story_id, number, c.name)],
        "remove_character_ids": [c.id for c in cast if c.first_episode == number and c.name.lower() not in wanted_names],
        "character_changes": changes,
    }


def introduced_here(session, story_id: int, number: int, name: str) -> bool:
    person = find_character(session, story_id, name)
    return person is not None and person.first_episode == number


def thread_restore(session, story_id: int, number: int, wanted: MemoryUpdate) -> dict:
    all_threads = threads(session, story_id)
    by_id = {t.id: t for t in all_threads}
    invented_here = [t for t in all_threads if is_invented_by(t, number)]
    kept = [t for t in invented_here if any(best_thread_match([t], o.title) for o in wanted.threads_opened)]
    answered = {i for i in wanted.resolved_thread_ids if i in by_id}
    if not answered:
        answered = {t.id for t in (best_thread_match(all_threads, title) for title in wanted.threads_resolved) if t}
    return {
        "threads_opened": [o for o in wanted.threads_opened if best_thread_match(all_threads, o.title) is None],
        "remove_thread_ids": [t.id for t in invented_here if t not in kept],
        "resolve_thread_ids": [i for i in answered if by_id[i].resolved_episode != number],
        "reopen_thread_ids": [t.id for t in all_threads if t.resolved_episode == number and t.id not in answered],
    }


def apply_version(
    session, story_id: int, number: int, row: EpisodeVersion, diff: MemoryDiff,
    reactivate_fact_ids: list[int] | None = None, ripple_id: int | None = None,
) -> None:
    """Make `row` the episode's current version: its text, its title and the memory change."""
    reason = f"ep {number} v{row.version} " + ("restore" if reactivate_fact_ids is not None else "edit")
    apply_diff(session, story_id, number, diff, row.version, reason, ripple_id, reactivate_fact_ids)
    episode = get_episode(session, story_id, number)
    episode.text, episode.title, episode.current_version = row.text, row.title or episode.title, row.version
    if row.memory is None or "fact_ids" not in row.memory:
        row.memory = memory_record(session, story_id, number)
