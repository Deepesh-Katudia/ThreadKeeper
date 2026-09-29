"""Turning finished episodes into memory, and undoing that when history is rewritten.

Everything written to memory carries the episode it came from (facts.source_episode,
characters.first_episode / status_changed_in, threads.opened_episode / resolved_episode).
That provenance is what lets a human rewrite episode 40 and have the memory follow.
"""

from langsmith import traceable
from sqlalchemy import delete

from story import config, llm, prompts
from story.critic import content_words
from story.db import session_scope
from story.models import Act, Character, Fact, Thread
from story.queries import (
    act_for_episode, approved_episodes_before, characters, episodes_between, find_character,
    get_episode, get_story, threads,
)
from story.schemas import MemoryUpdate, Recap

THREAD_TITLE_MATCH = 0.5


@traceable(name="extract_memory")
def extract_memory(story_id: int, number: int, episode_text: str) -> MemoryUpdate:
    with session_scope() as session:
        known_cast = ", ".join(c.name for c in characters(session, story_id)) or "(none)"
        open_threads = "; ".join(t.title for t in threads(session, story_id, ("open",))) or "(none)"
    return llm.write_json(
        "extract_memory", prompts.extractor_system(),
        prompts.extractor_prompt(number, episode_text, known_cast, open_threads),
        MemoryUpdate, config.EXTRACTOR_MODEL, story_id=story_id, episode=number, max_tokens=4000,
    )


def commit_memory(session, story_id: int, number: int, update: MemoryUpdate) -> None:
    """Write an approved episode's memory into the story's records."""
    episode = get_episode(session, story_id, number)
    episode.summary = update.summary
    episode.hook = update.hook
    episode.characters_present = update.characters_present

    for person in update.new_characters:
        if find_character(session, story_id, person.name) is None:
            session.add(Character(
                story_id=story_id, name=person.name, role=person.role or "minor",
                description=person.description, first_episode=number, last_seen_episode=number,
            ))
    session.flush()

    for name in update.characters_present:
        person = find_character(session, story_id, name)
        if person is not None:
            person.last_seen_episode = max(person.last_seen_episode, number)

    for change in update.character_changes:
        person = find_character(session, story_id, change.name)
        if person is not None:
            person.status = change.new_status.lower()
            person.status_changed_in = number

    for fact in update.new_facts:
        session.add(Fact(story_id=story_id, subject=fact.subject, statement=fact.statement, source_episode=number))

    record_threads(session, story_id, number, update)


def record_threads(session, story_id: int, number: int, update: MemoryUpdate) -> None:
    all_threads = threads(session, story_id)

    # Threads the arc planned for this point are now on the page.
    for thread in all_threads:
        if thread.status == "planned" and thread.opened_episode <= number:
            thread.status = "open"

    for opened in update.threads_opened:
        existing = best_thread_match(all_threads, opened.title)
        if existing is None:
            session.add(Thread(
                story_id=story_id, title=opened.title, description=opened.description,
                opened_episode=number, status="open",
            ))
        elif existing.status == "planned":
            existing.status = "open"

    for title in update.threads_resolved:
        existing = best_thread_match(all_threads, title)
        if existing is not None and existing.status != "resolved":
            existing.status = "resolved"
            existing.resolved_episode = number


def best_thread_match(candidates: list[Thread], title: str) -> Thread | None:
    wanted = content_words(title)
    best, best_score = None, 0.0
    for thread in candidates:
        have = content_words(thread.title)
        if not wanted or not have:
            continue
        score = len(wanted & have) / len(wanted | have)
        if score > best_score:
            best, best_score = thread, score
    return best if best_score >= THREAD_TITLE_MATCH else None


def forget_episode(session, story_id: int, number: int) -> None:
    """Undo everything an episode added to memory, so it can be re-extracted after an edit."""
    session.execute(delete(Fact).where(Fact.story_id == story_id, Fact.source_episode == number))

    for person in characters(session, story_id):
        if person.first_episode == number and person.last_seen_episode <= number:
            session.delete(person)
        elif person.status_changed_in == number:
            person.status, person.status_changed_in = "alive", 0

    for thread in threads(session, story_id):
        if thread.resolved_episode == number:
            thread.status, thread.resolved_episode = "open", 0
        elif thread.opened_episode == number and thread.payoff_episode == 0:
            session.delete(thread)  # it was invented by that episode, not by the arc plan
    session.flush()


@traceable(name="refresh_story_so_far")
def refresh_story_so_far(story_id: int, through_episode: int) -> None:
    """Fold the latest episode summaries into the running recap."""
    with session_scope() as session:
        story = get_story(session, story_id)
        newer = [
            e for e in episodes_between(session, story_id, story.story_so_far_through + 1, through_episode)
            if e.status == "approved"
        ]
        previous_recap = story.story_so_far
    if not newer:
        return
    summaries = "\n".join(f"Ep {e.number}: {e.summary}" for e in newer)
    recap = llm.write_json(
        "story_so_far", prompts.extractor_system(),
        prompts.story_so_far_prompt(previous_recap, summaries),
        Recap, config.EXTRACTOR_MODEL, story_id=story_id, episode=through_episode, max_tokens=2000,
    )
    with session_scope() as session:
        story = get_story(session, story_id)
        story.story_so_far = recap.text
        story.story_so_far_through = through_episode


@traceable(name="summarise_act")
def summarise_act(story_id: int, number: int) -> None:
    with session_scope() as session:
        act = act_for_episode(session, story_id, number)
        if act is None:
            return
        written = approved_episodes_before(session, story_id, act.last_episode + 1, 10_000)
        in_act = [e for e in written if e.number >= act.first_episode]
        act_title, act_id = act.title, act.id
    summaries = "\n".join(f"Ep {e.number}: {e.summary}" for e in in_act)
    recap = llm.write_json(
        "act_summary", prompts.extractor_system(), prompts.act_summary_prompt(act_title, summaries),
        Recap, config.EXTRACTOR_MODEL, story_id=story_id, episode=number, max_tokens=1500,
    )
    with session_scope() as session:
        session.get(Act, act_id).summary = recap.text
