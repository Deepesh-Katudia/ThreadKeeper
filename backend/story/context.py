"""Builds what the writer and critic see for one episode.

This is the answer to "how does it remember at episode 150?". The prompt is assembled from
layers, each with a fixed budget, so it stays roughly the same size however long the story gets:

  1. where we are in the arc (act goal, this beat, the next few beats)
  2. the rolling "story so far" recap, refreshed every 10 episodes
  3. summaries of the last 8 episodes, plus the last lines of the previous one
  4. the characters and facts relevant to this beat (not all of them)
  5. open threads, sorted by how soon they are due
  6. the human's standing instructions
"""

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from story import config, prompts
from story.models import Character, Episode, Story
from story.queries import (
    act_for_episode, active_directives, approved_episodes_before, characters,
    episodes_between, facts, get_episode, get_story, threads,
)

MAIN_ROLES = ("protagonist", "antagonist")


@dataclass
class EpisodeContext:
    number: int
    system: str
    sections: dict[str, str] = field(default_factory=dict)
    earlier_episodes_index: str = ""
    known_summaries: dict[int, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(f"## {name}\n{body}" for name, body in self.sections.items() if body.strip())


def build_episode_context(session: Session, story_id: int, number: int) -> EpisodeContext:
    story = get_story(session, story_id)
    cast = characters(session, story_id)
    recent = approved_episodes_before(session, story_id, number, config.RECENT_SUMMARIES)
    beats_ahead = episodes_between(session, story_id, number, number + config.UPCOMING_BEATS)
    relevant_people = pick_relevant_characters(cast, recent, beats_ahead)

    context = EpisodeContext(number=number, system=prompts.writer_system(story, describe_main_cast(cast)))
    context.sections = {
        "Where we are": describe_position(session, story, number),
        "Story so far": story.story_so_far or "(This is the beginning of the story.)",
        "Recent episodes": describe_recent(recent),
        "How the previous episode ended": previous_ending(session, story_id, number),
        "This episode's beat and what comes next": describe_beats(session, story_id, number, beats_ahead),
        "Characters in play": describe_characters(relevant_people, cast),
        "Canon facts to respect": describe_facts(session, story_id, relevant_people, beats_ahead),
        "Open threads": describe_threads(session, story_id, number),
        "Standing instructions from the editor": describe_directives(session, story_id, number),
    }
    context.earlier_episodes_index = describe_earlier_episodes(session, story_id, number, len(recent))
    context.known_summaries = {
        e.number: e.summary for e in approved_episodes_before(session, story_id, number, 10_000) if e.summary
    }
    return context


# --- Individual layers ---------------------------------------------------------


def describe_position(session: Session, story: Story, number: int) -> str:
    act = act_for_episode(session, story.id, number)
    if act is None:
        return f"Episode {number} of {story.total_episodes}."
    episodes_left = act.last_episode - number
    return (
        f"Episode {number} of {story.total_episodes}. Act {act.number}: \"{act.title}\" "
        f"(episodes {act.first_episode}-{act.last_episode}, {episodes_left} left in this act).\n"
        f"Act goal: {act.goal}\nThe act ends on: {act.turning_point}"
    )


def describe_recent(recent: list[Episode]) -> str:
    if not recent:
        return "(No episodes written yet.)"
    return "\n".join(f"Ep {e.number} \"{e.title}\": {e.summary} Ended on: {e.hook}" for e in recent)


def previous_ending(session: Session, story_id: int, number: int) -> str:
    if number <= 1:
        return ""
    previous = get_episode(session, story_id, number - 1)
    if previous.status != "approved" or not previous.text:
        return ""
    words = previous.text.split()
    return "..." + " ".join(words[-config.LAST_WORDS_OF_PREVIOUS:])


def describe_beats(session: Session, story_id: int, number: int, beats_ahead: list[Episode]) -> str:
    lines = []
    if number > 1:
        lines.append(f"Previous beat (ep {number - 1}): {get_episode(session, story_id, number - 1).beat}")
    for episode in beats_ahead:
        if episode.number == number:
            lines.append(f">>> THIS EPISODE (ep {number}): {episode.beat}")
        else:
            lines.append(f"Coming later (ep {episode.number}, don't do this yet): {episode.beat}")
    return "\n".join(lines)


def pick_relevant_characters(cast: list[Character], recent: list[Episode], beats_ahead: list[Episode]) -> list[Character]:
    """Main cast, whoever was on the page lately, and whoever the upcoming beats mention."""
    recently_present = {name.lower() for e in recent[-3:] for name in e.characters_present}
    beat_text = " ".join(e.beat for e in beats_ahead)
    chosen = []
    for person in cast:
        if (
            person.role in MAIN_ROLES
            or person.name.lower() in recently_present
            or first_name(person).lower() in recently_present
            or mentions(beat_text, person)
        ):
            chosen.append(person)
    return chosen


def describe_main_cast(cast: list[Character]) -> str:
    # Kept status-free on purpose: this goes in the cached system prompt, so it should rarely change.
    planned = [c for c in cast if c.first_episode == 0]
    return "\n".join(f"- {c.name} ({c.role}): {c.description}" for c in planned)


def describe_characters(relevant: list[Character], cast: list[Character]) -> str:
    lines = [
        f"- {c.name} ({c.role}, {c.status.upper()}, last seen ep {c.last_seen_episode or '-'}): {c.description}"
        for c in relevant
    ]
    gone = [c for c in cast if c.status in ("dead", "missing") and c not in relevant]
    if gone:
        lines.append("Also gone from the story: " + ", ".join(f"{c.name} ({c.status} since ep {c.status_changed_in})" for c in gone))
    return "\n".join(lines)


def describe_facts(session: Session, story_id: int, relevant: list[Character], beats_ahead: list[Episode]) -> str:
    all_facts = facts(session, story_id)
    beat_text = " ".join(e.beat for e in beats_ahead).lower()
    names = {c.name.lower() for c in relevant} | {first_name(c).lower() for c in relevant}

    def is_relevant(fact) -> bool:
        subject = fact.subject.lower()
        return subject in names or subject in beat_text or any(n in fact.statement.lower() for n in names)

    picked = [f for f in all_facts if is_relevant(f)]
    newest = all_facts[-10:]
    chosen = {f.id: f for f in picked + newest}
    ordered = sorted(chosen.values(), key=lambda f: f.source_episode)[-config.MAX_FACTS_IN_CONTEXT:]
    if not ordered:
        return "(Nothing established yet.)"
    return "\n".join(f"- (ep {f.source_episode}) {f.subject}: {f.statement}" for f in ordered)


def describe_threads(session: Session, story_id: int, number: int) -> str:
    lines = []
    for thread in threads(session, story_id, ("open", "planned")):
        if thread.status == "planned" and number <= thread.opened_episode <= number + 2:
            lines.append(f"- INTRODUCE SOON (planned for ep {thread.opened_episode}): {thread.title}: {thread.description}")
        elif thread.status == "open":
            if thread.payoff_episode and thread.payoff_episode < number:
                label = f"OVERDUE (was due ep {thread.payoff_episode})"
            elif thread.payoff_episode and thread.payoff_episode <= number + 3:
                label = f"DUE SOON (ep {thread.payoff_episode})"
            else:
                label = f"open since ep {thread.opened_episode}"
            lines.append(f"- {label}: {thread.title}: {thread.description}")
    return "\n".join(lines[: config.MAX_THREADS_IN_CONTEXT]) or "(No open threads.)"


def describe_directives(session: Session, story_id: int, number: int) -> str:
    rules = active_directives(session, story_id, number)
    return "\n".join(f"- {d.text} (given after ep {d.given_after_episode})" for d in rules) or "(None.)"


def describe_earlier_episodes(session: Session, story_id: int, number: int, skip_recent: int) -> str:
    """One line per older episode, so the critic can spot repeated beats cheaply."""
    older = approved_episodes_before(session, story_id, number, 10_000)
    older = older[: max(0, len(older) - skip_recent)]
    return "\n".join(f"Ep {e.number} \"{e.title}\": {e.hook}" for e in older)


# --- Tiny text helpers -----------------------------------------------------------


def first_name(person: Character) -> str:
    return person.name.split()[0]


def mentions(text: str, person: Character) -> bool:
    for name in {person.name, first_name(person)}:
        if re.search(rf"\b{re.escape(name)}\b", text, flags=re.IGNORECASE):
            return True
    return False
