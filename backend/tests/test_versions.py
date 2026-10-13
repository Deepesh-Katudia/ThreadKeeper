"""Versions, retraction, diff-based memory for edits, and an undo that makes no model call."""

import re

from sqlalchemy import delete

from story import pipeline
from story.db import session_scope
from story.models import EpisodeVersion, Fact
from story.queries import (
    characters, episode_facts, facts, facts_including_retracted, find_character, get_episode, threads, versions_of,
)
from story.schemas import CharacterChange, NewFact
from tests.ripple_helpers import edit_through_ripple
from tests.test_pipeline import new_story, write_and_approve

EXTRACTOR_SCHEMAS = ("MemoryUpdate", "MemoryDiff")


def canon(story_id: int) -> dict:
    """Everything an edit can change, in a form that can be compared."""
    with session_scope() as session:
        return {
            "facts": sorted((f.id, f.statement) for f in facts(session, story_id)),
            "characters": sorted(
                (c.name, c.status, c.status_changed_in, c.first_episode) for c in characters(session, story_id)
            ),
            "threads": sorted(
                (t.title, t.status, t.opened_episode, t.resolved_episode) for t in threads(session, story_id)
            ),
        }


def extractor_calls(fake_model) -> int:
    return sum(1 for name, _ in fake_model.prompts if name in EXTRACTOR_SCHEMAS)


def id_in(prompt: str, label: str) -> int:
    return int(re.search(rf"\[(\d+)\] {re.escape(label)}", prompt).group(1))


def test_approval_records_version_one_with_the_facts_it_left(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 2)

    with session_scope() as session:
        episode = get_episode(session, story_id, 2)
        [v1] = versions_of(session, story_id, 2)
        own = episode_facts(session, story_id, 2)
        assert episode.current_version == 1
        assert (v1.version, v1.source, v1.text) == (1, "written", episode.text)
        assert v1.memory["fact_ids"] == [f.id for f in own]
        assert all(f.source_version == 1 for f in own)


def test_the_writer_context_ids_and_prompt_size_are_recorded(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 2)
    pipeline.write_episode(story_id, 3)

    with session_scope() as session:
        episode = get_episode(session, story_id, 3)
        earlier = {f.id for f in facts(session, story_id)}
        assert set(episode.context_ids["facts"]) == earlier
        assert episode.context_ids["summaries"] == [1, 2]
        assert episode.critic_report["context_chars"] > 0


def test_an_edit_retracts_facts_instead_of_deleting_them(fake_model):
    story_id = new_story()
    fake_model.extra_facts = {2: [NewFact(subject="the locker", statement="locker 214")]}
    write_and_approve(story_id, 3)
    fake_model.diffs = {2: lambda prompt: {
        "retract_fact_ids": [id_in(prompt, "the locker: locker 214")],
        "new_facts": [NewFact(subject="the locker", statement="locker 117")],
    }}

    edit_through_ripple(story_id, 2, "Episode two, now with locker 117.")

    with session_scope() as session:
        everything = {f.statement: f for f in facts_including_retracted(session, story_id)}
        old, new = everything["locker 214"], everything["locker 117"]
        assert old.is_active is False and old.retracted_reason == "ep 2 v2 edit"
        assert new.source_version == 2
        assert "locker 214" not in [f.statement for f in facts(session, story_id)]
        assert "fact from episode 2" in [f.statement for f in facts(session, story_id)]  # kept: still true
        assert get_episode(session, story_id, 2).current_version == 2
    diff_temperatures = [t for (name, _), t in zip(fake_model.prompts, fake_model.temperatures) if name == "MemoryDiff"]
    assert diff_temperatures == [0]  # as repeatable as the provider allows


def test_the_diff_cannot_touch_other_episodes_or_break_time_order(fake_model):
    story_id = new_story()
    fake_model.opens = {4: ["Who rang the bell"]}
    write_and_approve(story_id, 4)
    with session_scope() as session:
        ep1_fact = episode_facts(session, story_id, 1)[0].id
        bell = next(t.id for t in threads(session, story_id) if t.title == "Who rang the bell")
    fake_model.diffs = {2: {"retract_fact_ids": [ep1_fact], "resolve_thread_ids": [bell]}}

    edit_through_ripple(story_id, 2, "Episode two again.")

    with session_scope() as session:
        assert ep1_fact in [f.id for f in facts(session, story_id)]
        thread = next(t for t in threads(session, story_id) if t.id == bell)
        assert (thread.status, thread.resolved_episode) == ("open", 0)


def test_restoring_the_original_text_restores_canon_exactly_without_a_model_call(fake_model):
    story_id = new_story()
    fake_model.opens = {3: ["Who rang the bell"]}
    fake_model.newcomers = {3: ["Woman In Green"]}
    fake_model.deaths = {3: "Mr Das"}
    fake_model.extra_facts = {3: [NewFact(subject="the locker", statement="locker 214")]}
    write_and_approve(story_id, 5)
    before = canon(story_id)
    with session_scope() as session:
        original = get_episode(session, story_id, 3).text
    fake_model.diffs = {3: lambda prompt: {
        "retract_fact_ids": [id_in(prompt, "the locker: locker 214")],
        "new_facts": [NewFact(subject="the locker", statement="locker 117")],
        "remove_character_ids": [id_in(prompt, "Woman In Green")],
        "remove_thread_ids": [id_in(prompt, "Who rang the bell")],
        "character_changes": [CharacterChange(name="Mr Das", new_status="alive", reason="lives")],
    }}

    edit_through_ripple(story_id, 3, "Episode three, rewritten by the editor.")

    edited = canon(story_id)
    assert edited != before
    assert ("Mr Das", "alive", 0, 0) in edited["characters"]
    assert not any(name == "Woman In Green" for name, *_ in edited["characters"])
    calls_before_undo = extractor_calls(fake_model)

    edit_through_ripple(story_id, 3, original)  # same text as version 1: a restore

    assert canon(story_id) == before
    assert extractor_calls(fake_model) == calls_before_undo
    with session_scope() as session:
        assert get_episode(session, story_id, 3).current_version == 1


def test_an_episode_approved_before_versions_existed_gets_version_one_when_edited(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 3)
    with session_scope() as session:  # make it look like the live database before this feature
        session.execute(delete(EpisodeVersion))
        for fact in session.query(Fact).all():
            fact.source_version, fact.is_active = None, None
        for number in (1, 2, 3):
            get_episode(session, story_id, number).current_version = None
    with session_scope() as session:
        assert len(facts(session, story_id)) == 3  # NULL counts as active
    fake_model.diffs = {2: lambda prompt: {"retract_fact_ids": [id_in(prompt, "Ravi Menon: fact from episode 2")]}}

    edit_through_ripple(story_id, 2, "Episode two, edited long after it was approved.")

    with session_scope() as session:
        v1, v2 = versions_of(session, story_id, 2)
        assert v1.note.startswith("Recorded from canon")
        assert (v2.version, v2.source) == (2, "human_edit")
        retracted = [f for f in facts_including_retracted(session, story_id) if f.is_active is False]
        assert [(f.source_episode, f.source_version) for f in retracted] == [(2, 1)]
        assert find_character(session, story_id, "Ravi Menon") is not None
