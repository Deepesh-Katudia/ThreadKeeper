"""Planning the arc, and re-planning upcoming beats when the human steers."""

import logging
from concurrent.futures import ThreadPoolExecutor

from langsmith import traceable
from sqlalchemy import delete

from story import config, llm, prompts
from story.db import session_scope
from story.models import Act, Character, Episode, Thread
from story.queries import acts, characters, episodes_between, get_story, threads
from story.schemas import ActBeats, Replan, StoryBible

log = logging.getLogger(__name__)

MISSING_BEAT = "(no beat planned: edit this before approving the arc)"
REPLAN_WINDOW = 20


@traceable(name="plan_arc")
def plan_arc(story_id: int) -> None:
    """Premise in, full 200-episode plan out. Leaves the story waiting for human review."""
    with session_scope() as session:
        story = get_story(session, story_id)
        premise, total = story.premise, story.total_episodes

    bible = llm.write_json(
        "plan_bible", prompts.planner_system(), prompts.bible_prompt(premise, total),
        StoryBible, config.PLANNER_MODEL, story_id=story_id,
    )
    planned_acts = tidy_act_ranges(bible.acts, total)
    save_bible(story_id, bible, planned_acts)

    with session_scope() as session:
        bible_text = describe_bible(session, story_id)

    # Acts are planned in parallel: each one already knows its goal and turning point
    # from the bible, so they don't need to wait for each other.
    with ThreadPoolExecutor(max_workers=4) as pool:
        beats_per_act = list(pool.map(lambda act: plan_act_beats(story_id, bible_text, act, total), planned_acts))

    with session_scope() as session:
        for act, beats in zip(planned_acts, beats_per_act):
            for number in range(act.first_episode, act.last_episode + 1):
                session.add(Episode(
                    story_id=story_id, number=number, act_number=act.number,
                    beat=beats.get(number, MISSING_BEAT),
                ))
        get_story(session, story_id).status = "arc_review"


def tidy_act_ranges(planned_acts, total: int):
    """Make the acts cover 1..total exactly, even if the model's numbers overlap or leave gaps."""
    ordered = sorted(planned_acts, key=lambda act: act.first_episode)
    tidy = []
    next_first = 1
    for index, act in enumerate(ordered):
        is_last = index == len(ordered) - 1
        last = total if is_last else min(max(act.last_episode, next_first), total)
        tidy.append(act.model_copy(update={"number": index + 1, "first_episode": next_first, "last_episode": last}))
        next_first = last + 1
    return tidy


def save_bible(story_id: int, bible: StoryBible, planned_acts) -> None:
    with session_scope() as session:
        story = get_story(session, story_id)
        story.title = bible.title
        story.logline = bible.logline
        story.setting = bible.setting
        story.style_guide = bible.style_guide
        for person in bible.characters:
            session.add(Character(
                story_id=story_id, name=person.name, role=person.role,
                description=person.description, planned_arc=person.planned_arc,
            ))
        for act in planned_acts:
            session.add(Act(
                story_id=story_id, number=act.number, title=act.title, goal=act.goal,
                turning_point=act.turning_point, first_episode=act.first_episode,
                last_episode=act.last_episode,
            ))
        for thread in bible.threads:
            session.add(Thread(
                story_id=story_id, title=thread.title, description=thread.description,
                opened_episode=thread.opened_episode, payoff_episode=thread.payoff_episode,
            ))


def plan_act_beats(story_id: int, bible_text: str, act, total: int) -> dict[int, str]:
    """Ask for one act's beats. Try twice; whatever is still missing gets a placeholder for the human."""
    wanted = set(range(act.first_episode, act.last_episode + 1))
    beats: dict[int, str] = {}
    for _attempt in range(2):
        result = llm.write_json(
            f"plan_act_{act.number}", prompts.planner_system(),
            prompts.act_beats_prompt(bible_text, act, total),
            ActBeats, config.PLANNER_MODEL, story_id=story_id,
        )
        beats.update({b.episode: b.beat for b in result.beats if b.episode in wanted})
        if wanted <= beats.keys():
            break
        log.warning("act %s came back with %s of %s beats", act.number, len(beats), len(wanted))
    return beats


def describe_bible(session, story_id: int) -> str:
    """The story bible as plain text, for planning prompts."""
    story = get_story(session, story_id)
    cast = "\n".join(
        f"- {c.name} ({c.role}, {c.status}): {c.description} Arc: {c.planned_arc}"
        for c in characters(session, story_id)
    )
    act_lines = "\n".join(
        f"- Act {a.number} \"{a.title}\" (ep {a.first_episode}-{a.last_episode}): {a.goal} "
        f"Turning point: {a.turning_point}"
        for a in acts(session, story_id)
    )
    thread_lines = "\n".join(
        f"- {t.title} [{t.status}] opens ep {t.opened_episode}, pays off ep {t.payoff_episode}: {t.description}"
        for t in threads(session, story_id)
    )
    return f"""\
Title: {story.title}
Logline: {story.logline}
Premise: {story.premise}
Setting: {story.setting}

Characters:
{cast}

Acts:
{act_lines}

Threads:
{thread_lines}"""


@traceable(name="replan_upcoming_beats")
def replan_upcoming_beats(story_id: int, feedback: str, after_episode: int) -> str:
    """Rewrite the next few unwritten beats so they follow the human's feedback."""
    with session_scope() as session:
        upcoming = [
            e for e in episodes_between(session, story_id, after_episode + 1, after_episode + REPLAN_WINDOW)
            if e.status in ("planned", "stale", "failed")
        ]
        if not upcoming:
            return "No unwritten beats left to change."
        bible_text = describe_bible(session, story_id)
        beats_text = "\n".join(f"{e.number}. {e.beat}" for e in upcoming)
        numbers = {e.number for e in upcoming}

    result = llm.write_json(
        "replan_beats", prompts.planner_system(),
        prompts.replan_prompt(bible_text, feedback, after_episode, beats_text),
        Replan, config.PLANNER_MODEL, story_id=story_id,
    )

    with session_scope() as session:
        for new_beat in result.beats:
            if new_beat.episode in numbers:
                episode = next(e for e in episodes_between(session, story_id, new_beat.episode, new_beat.episode))
                episode.beat = new_beat.beat
    return result.what_changed


def reset_plan(story_id: int) -> None:
    """Throw away a failed plan so planning can start again cleanly."""
    with session_scope() as session:
        for table in (Episode, Act, Character, Thread):
            session.execute(delete(table).where(table.story_id == story_id))
        get_story(session, story_id).status = "planning"
