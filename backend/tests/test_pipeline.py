"""End-to-end behaviour of the story loop, using the fake model."""

import pytest

from story import config, pipeline
from story.context import build_episode_context
from story.db import session_scope
from story.models import Story
from story.planner import plan_arc
from story.queries import acts, all_episodes, characters, facts, find_character, get_episode, get_story

TOTAL = 16


def new_story(approve_arc: bool = True) -> int:
    with session_scope() as session:
        story = Story(premise="A delivery rider's route is all dead people.", total_episodes=TOTAL)
        session.add(story)
        session.flush()
        story_id = story.id
    plan_arc(story_id)
    if approve_arc:
        with session_scope() as session:
            get_story(session, story_id).status = "writing"
    return story_id


def write_and_approve(story_id: int, how_many: int) -> None:
    for _ in range(how_many):
        number = pipeline.next_episode_to_write(story_id)
        pipeline.write_episode(story_id, number)
        pipeline.approve_episode(story_id, number)


def test_planning_creates_every_episode_and_waits_for_review(fake_model):
    story_id = new_story(approve_arc=False)

    with session_scope() as session:
        story = get_story(session, story_id)
        episodes = all_episodes(session, story_id)
        act_list = acts(session, story_id)
        assert story.status == "arc_review"
        assert [e.number for e in episodes] == list(range(1, TOTAL + 1))
        assert act_list[0].first_episode == 1 and act_list[-1].last_episode == TOTAL
        assert all(e.beat.startswith("beat") for e in episodes)


def test_writing_is_blocked_until_the_arc_is_approved(fake_model):
    story_id = new_story(approve_arc=False)
    with pytest.raises(pipeline.NotAllowed):
        pipeline.next_episode_to_write(story_id)


def test_an_episode_waits_for_review_then_memory_is_committed_on_approval(fake_model):
    story_id = new_story()

    pipeline.write_episode(story_id, 1)
    with session_scope() as session:
        episode = get_episode(session, story_id, 1)
        assert episode.status == "in_review"
        assert episode.critic_report["passed"] is True
        assert facts(session, story_id) == []  # nothing is canon until a human approves

    with pytest.raises(pipeline.NotAllowed):
        pipeline.next_episode_to_write(story_id)  # can't run ahead of the reviewer

    pipeline.approve_episode(story_id, 1)
    with session_scope() as session:
        assert get_episode(session, story_id, 1).status == "approved"
        assert [f.source_episode for f in facts(session, story_id)] == [1]


def test_resume_picks_up_at_the_first_unapproved_episode(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 3)
    # "Stopping" is just not calling anything; state lives in the database.
    assert pipeline.next_episode_to_write(story_id) == 4


def test_critic_objections_trigger_revisions_but_only_up_to_the_limit(fake_model):
    story_id = new_story()
    fake_model.critic_verdicts = ["revise"] * 10

    pipeline.write_episode(story_id, 1)

    with session_scope() as session:
        episode = get_episode(session, story_id, 1)
        assert episode.revision_count == config.MAX_REVISIONS
        assert episode.critic_report["passed"] is False
        assert episode.status == "in_review"  # a human decides what to do with it
    assert len(fake_model.prompts_for("CriticReport")) == config.MAX_REVISIONS + 1


def test_cost_cap_stops_revisions_early(fake_model, monkeypatch):
    monkeypatch.setattr(config, "EPISODE_COST_CAP_USD", 0.0001)
    story_id = new_story()
    fake_model.critic_verdicts = ["revise"] * 10

    pipeline.write_episode(story_id, 1)

    with session_scope() as session:
        report = get_episode(session, story_id, 1).critic_report
    assert report["attempts"][-1] == {"stage": "stopped", "reason": "cost cap reached"}


def test_feedback_becomes_a_standing_instruction_and_replans_upcoming_beats(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 2)

    pipeline.give_feedback(story_id, "Kill off Mr Das soon.")

    with session_scope() as session:
        assert get_episode(session, story_id, 2).beat == "beat 2"  # history untouched
        assert get_episode(session, story_id, 3).beat == "replanned beat 3"
        context = build_episode_context(session, story_id, 3)
    assert "Kill off Mr Das soon." in context.sections["Standing instructions from the editor"]

    write_and_approve(story_id, 1)
    last_draft_prompt = fake_model.prompts_for("Draft")[-1]
    assert "Kill off Mr Das soon." in last_draft_prompt
    assert "replanned beat 3" in last_draft_prompt


def test_rejecting_with_a_note_puts_the_note_in_the_next_draft(fake_model):
    story_id = new_story()
    pipeline.write_episode(story_id, 1)

    pipeline.reject_episode(story_id, 1, "Less rain, more dialogue.")
    pipeline.write_episode(story_id, 1)

    assert "Less rain, more dialogue." in fake_model.prompts_for("Draft")[-1]


def test_character_deaths_are_remembered_and_shown_to_the_writer(fake_model):
    story_id = new_story()
    fake_model.deaths = {2: "Mr Das"}
    write_and_approve(story_id, 3)

    with session_scope() as session:
        das = find_character(session, story_id, "Mr Das")
        assert (das.status, das.status_changed_in) == ("dead", 2)
        context = build_episode_context(session, story_id, 4)
    assert "Mr Das (dead since ep 2)" in context.sections["Characters in play"]


def test_editing_an_approved_episode_rewrites_its_memory(fake_model):
    story_id = new_story()
    fake_model.deaths = {2: "Mr Das"}
    write_and_approve(story_id, 3)
    fake_model.deaths = {}  # in the human's rewrite, Mr Das survives

    pipeline.edit_episode(story_id, 2, "A rewritten episode two. Mr Das lives.")

    with session_scope() as session:
        das = find_character(session, story_id, "Mr Das")
        assert das.status == "alive"
        assert sorted(f.source_episode for f in facts(session, story_id)) == [1, 2, 3]
        assert get_episode(session, story_id, 2).was_edited_by_human


def test_editing_history_marks_later_unapproved_drafts_stale(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 2)
    pipeline.write_episode(story_id, 3)  # waiting for review

    pipeline.edit_episode(story_id, 1, "New version of episode one.")

    with session_scope() as session:
        assert get_episode(session, story_id, 3).status == "stale"
    assert pipeline.next_episode_to_write(story_id) == 3


def test_context_stays_bounded_as_the_story_grows(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 12)

    with session_scope() as session:
        early = build_episode_context(session, story_id, 3)
        late = build_episode_context(session, story_id, 13)
        recent = late.sections["Recent episodes"]

    assert recent.count("Ep ") == config.RECENT_SUMMARIES
    assert len(late.text) < len(early.text) * 3


def test_story_so_far_is_refreshed_every_ten_episodes(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 10)
    with session_scope() as session:
        story = get_story(session, story_id)
        assert story.story_so_far_through == 10
        assert story.story_so_far


def test_a_failed_model_call_marks_the_episode_failed_with_the_reason(fake_model, monkeypatch):
    story_id = new_story()

    def broken(*args):
        raise RuntimeError("provider is down")

    monkeypatch.setattr("story.llm._call_anthropic", broken)
    monkeypatch.setattr("story.llm._call_openrouter", broken)
    pipeline.write_episode(story_id, 1)

    with session_scope() as session:
        episode = get_episode(session, story_id, 1)
        assert episode.status == "failed"
        assert "provider is down" in episode.error
    assert pipeline.next_episode_to_write(story_id) == 1  # can simply be retried


def test_interrupted_work_is_recovered_after_a_restart(fake_model):
    story_id = new_story()
    with session_scope() as session:
        get_episode(session, story_id, 1).status = "drafting"

    pipeline.recover_interrupted_work()

    with session_scope() as session:
        assert get_episode(session, story_id, 1).status == "failed"


def test_auto_approve_batch_stops_when_the_critic_objects(fake_model):
    story_id = new_story()
    fake_model.critic_verdicts = ["pass", "pass", "revise", "revise", "revise"]

    message = pipeline.write_batch(story_id, count=5, auto_approve=True)

    assert "episode 3" in message
    with session_scope() as session:
        statuses = [e.status for e in all_episodes(session, story_id)[:3]]
    assert statuses == ["approved", "approved", "in_review"]


def test_every_model_call_is_logged_with_cost(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 1)
    from story.llm import episode_cost
    assert episode_cost(story_id, 1) > 0
    with session_scope() as session:
        assert characters(session, story_id)
