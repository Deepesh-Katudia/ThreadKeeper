"""Rules the story's memory must always satisfy, checked in code.

Each problem comes back as one readable line, for the Memory page and for the end of a ripple.
These are cheap, exact checks: they catch bookkeeping mistakes (a thread answered before it
was asked, canon that doesn't match the episode's current version), not storytelling ones.
"""

from story.db import session_scope
from story.models import Ripple, RippleItem
from story.queries import (
    all_episodes, characters, facts, facts_including_retracted, get_story, threads, versions_of,
)
from story.versions import ensure_v1


def check_memory(story_id: int) -> list[str]:
    """Also gives legacy approved episodes their version 1 (idempotent), so this is not read-only."""
    with session_scope() as session:
        get_story(session, story_id)
        approved = [e for e in all_episodes(session, story_id) if e.status == "approved"]
        for episode in approved:
            ensure_v1(session, story_id, episode.number)  # legacy episodes get their version 1 lazily
        session.flush()
        return (
            thread_problems(session, story_id)
            + version_problems(session, story_id, approved)
            + death_problems(session, story_id, approved)
            + context_problems(session, story_id, approved)
            + ripple_problems(session, story_id)
        )


def thread_problems(session, story_id: int) -> list[str]:
    return [
        f"Thread \"{t.title}\" is resolved in episode {t.resolved_episode}, before it opens in episode {t.opened_episode}."
        for t in threads(session, story_id) if t.resolved_episode and t.resolved_episode < t.opened_episode
    ]


def version_problems(session, story_id: int, approved) -> list[str]:
    """Every approved episode has a current version, and its active facts are exactly that version's."""
    problems = []
    active_by_episode: dict[int, set[int]] = {}
    for fact in facts(session, story_id):
        active_by_episode.setdefault(fact.source_episode, set()).add(fact.id)
    for episode in approved:
        if not episode.current_version:
            problems.append(f"Episode {episode.number} is approved but has no current version.")
            continue
        current = next((v for v in versions_of(session, story_id, episode.number) if v.version == episode.current_version), None)
        if current is None or not current.memory or "fact_ids" not in current.memory:
            continue
        expected, active = set(current.memory["fact_ids"]), active_by_episode.get(episode.number, set())
        if expected != active:
            problems.append(
                f"Episode {episode.number}: active facts don't match its current version v{episode.current_version} "
                f"(unexpected {sorted(active - expected) or 'none'}, missing {sorted(expected - active) or 'none'})."
            )
    return problems


def death_problems(session, story_id: int, approved) -> list[str]:
    """Reported, not blocked: a dead character can appear in a memory or a flashback."""
    problems = []
    for person in characters(session, story_id):
        if person.status != "dead":
            continue
        names = {person.name.lower(), person.name.split()[0].lower()}
        for episode in approved:
            present = {n.lower() for n in episode.characters_present or []}
            if episode.number > person.status_changed_in and present & names:
                problems.append(
                    f"{person.name} died in episode {person.status_changed_in} but is present in episode {episode.number}. "
                    "Fine if it's a memory or flashback."
                )
    return problems


def context_problems(session, story_id: int, approved) -> list[str]:
    """The writer of episode N must only have been shown canon from episodes before N."""
    source_of = {f.id: f.source_episode for f in facts_including_retracted(session, story_id)}
    problems = []
    for episode in approved:
        ids = episode.context_ids or {}
        later_facts = [i for i in ids.get("facts", []) if source_of.get(i, 0) >= episode.number]
        later_summaries = [n for n in ids.get("summaries", []) if n >= episode.number]
        if later_facts or later_summaries:
            problems.append(f"Episode {episode.number}'s writer was shown canon from episode {episode.number} or later.")
    return problems


def ripple_problems(session, story_id: int) -> list[str]:
    closed = session.query(Ripple).filter(Ripple.story_id == story_id, Ripple.status == "closed").all()
    problems = []
    for ripple in closed:
        undecided = session.query(RippleItem).filter(
            RippleItem.ripple_id == ripple.id, RippleItem.decision.is_(None), RippleItem.check_status != "unaffected",
        ).count()
        if undecided:
            problems.append(f"Ripple #{ripple.id} is closed with {undecided} episodes still undecided.")
    return problems
