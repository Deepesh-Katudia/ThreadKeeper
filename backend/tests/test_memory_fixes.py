"""Memory bugs found by editing episode 5 of the live demo story, one test per fix."""

from story import config, prompts
from story.context import build_episode_context
from story.db import session_scope
from story.memory import extract_memory, forget_episode, record_threads
from story.queries import get_episode, get_story, threads
from story.schemas import MemoryUpdate, NewFact
from tests.test_pipeline import new_story, write_and_approve

PARCEL = "What is in the parcel"


def thread_named(session, story_id: int, title: str):
    return next((t for t in threads(session, story_id) if t.title == title), None)


def no_memory(**changes) -> MemoryUpdate:
    fields = dict(
        summary="s", hook="h", characters_present=[], new_characters=[], character_changes=[],
        new_facts=[], threads_opened=[], threads_resolved=[], resolved_thread_ids=[],
    )
    return MemoryUpdate(**{**fields, **changes})


def test_forgetting_an_episode_keeps_a_thread_a_later_episode_resolved(fake_model):
    story_id = new_story()
    fake_model.opens = {5: [PARCEL]}
    fake_model.resolves = {6: [PARCEL]}
    write_and_approve(story_id, 8)

    with session_scope() as session:
        forget_episode(session, story_id, 5)  # what an edit of episode 5 does first

    with session_scope() as session:
        parcel = thread_named(session, story_id, PARCEL)
        assert parcel is not None, "episode 6's payoff was lost"
        assert (parcel.status, parcel.opened_episode, parcel.resolved_episode) == ("resolved", 5, 6)


def test_re_extracting_an_episode_only_sees_threads_already_open_by_then(fake_model):
    story_id = new_story()
    fake_model.opens = {8: ["Who sent the letter"]}
    write_and_approve(story_id, 8)

    extract_memory(story_id, 5, "Episode five, rewritten.")

    assert "Who sent the letter" not in fake_model.prompts_for("MemoryUpdate")[-1]


def test_an_episode_cannot_resolve_a_thread_that_opens_later(fake_model):
    story_id = new_story()
    fake_model.opens = {8: ["Who sent the letter"]}
    write_and_approve(story_id, 8)

    with session_scope() as session:
        record_threads(session, story_id, 5, no_memory(threads_resolved=["Who sent the letter"]))

    with session_scope() as session:
        letter = thread_named(session, story_id, "Who sent the letter")
        assert (letter.status, letter.resolved_episode) == ("open", 0)


def test_facts_from_the_last_three_episodes_always_reach_the_writer(fake_model):
    story_id = new_story()
    # Lots of facts about an object nobody's name matches: the newest-ten rule alone drops episode 6's.
    fake_model.extra_facts = {
        n: [NewFact(subject="the locker", statement=f"locker detail {n}-{k}") for k in range(5)] for n in (6, 7, 8)
    }
    write_and_approve(story_id, 8)

    with session_scope() as session:
        canon = build_episode_context(session, story_id, 9).sections["Canon facts to respect"]

    for n in (6, 7, 8):
        for k in range(5):
            assert f"locker detail {n}-{k}" in canon


def test_the_recent_fact_window_survives_the_cap(fake_model, monkeypatch):
    monkeypatch.setattr(config, "MAX_FACTS_IN_CONTEXT", 4)
    story_id = new_story()
    fake_model.extra_facts = {3: [NewFact(subject="the locker", statement="locker 117 holds the parcel")]}
    write_and_approve(story_id, 3)

    with session_scope() as session:
        canon = build_episode_context(session, story_id, 4).sections["Canon facts to respect"]

    assert "locker 117 holds the parcel" in canon
    assert canon.count("\n") + 1 <= 4


def test_the_recap_is_never_empty_after_episode_one(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 1)

    with session_scope() as session:
        assert get_story(session, story_id).story_so_far_through == 1
        recap = build_episode_context(session, story_id, 2).sections["Story so far"]
    assert "beginning of the story" not in recap


def test_the_next_episode_sees_the_previous_opening_line(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 1)
    with session_scope() as session:
        episode = get_episode(session, story_id, 1)
        episode.text = "ORDER #4471 - 17 Kessler Ave, Apt 3B - brass key stamped 4F\n\n" + episode.text

    with session_scope() as session:
        handoff = build_episode_context(session, story_id, 2).sections["How the previous episode ended"]

    assert handoff.startswith("Opening line: ORDER #4471 - 17 Kessler Ave, Apt 3B - brass key stamped 4F")
    assert "ends at a door." in handoff


def test_the_extractor_is_asked_for_concrete_specifics():
    prompt = prompts.extractor_prompt(5, "text", "(none)", "(none)")
    for words in ("addresses", "numbers", "header line"):
        assert words in prompt
