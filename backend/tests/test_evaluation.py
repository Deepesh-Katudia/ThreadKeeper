"""LangSmith evaluation: online feedback on traces, and the offline evaluators."""

import pytest
from fastapi.testclient import TestClient

from story import evaluation, pipeline
from tests.test_pipeline import new_story, write_and_approve


@pytest.fixture
def sent_feedback(monkeypatch):
    """Pretend we're inside a LangSmith trace and capture every piece of feedback."""
    sent = []
    monkeypatch.setattr(evaluation, "current_trace_run_id", lambda: "run-123")
    monkeypatch.setattr(evaluation, "log_feedback", lambda run_id, key, score=None, value=None, comment="": sent.append((run_id, key, score, value)))
    return sent


def keys(sent):
    return [key for _run, key, _score, _value in sent]


def test_critic_scores_are_logged_on_the_episode_trace(fake_model, sent_feedback):
    story_id = new_story()

    pipeline.write_episode(story_id, 1)

    assert {"critic_passed", "critic_hook", "word_count_ok", "revisions"} <= set(keys(sent_feedback))
    assert all(run_id == "run-123" for run_id, *_ in sent_feedback)


def test_human_decisions_are_logged_on_the_same_trace(fake_model, sent_feedback):
    story_id = new_story()
    pipeline.write_episode(story_id, 1)
    pipeline.reject_episode(story_id, 1, "More dialogue.")
    pipeline.write_episode(story_id, 1)
    pipeline.approve_episode(story_id, 1)
    sent_feedback.clear()

    pipeline.edit_episode(story_id, 1, "A human rewrite of episode one.")

    decisions = [(value, score) for _run, key, score, value in sent_feedback if key == "human_decision"]
    assert decisions == [("edited", 0.5)]


def test_rejections_carry_the_reason(fake_model, sent_feedback):
    story_id = new_story()
    pipeline.write_episode(story_id, 1)

    pipeline.reject_episode(story_id, 1, "Too much rain.")

    assert ("run-123", "human_decision", 0, "rejected") in sent_feedback


def test_feedback_is_skipped_quietly_when_langsmith_is_off(fake_model, monkeypatch):
    monkeypatch.setattr(evaluation, "langsmith_enabled", lambda: False)
    submitted = []
    monkeypatch.setattr(evaluation._sender, "submit", lambda *args: submitted.append(args))

    evaluation.log_feedback("run-1", "anything", score=1)

    assert submitted == []


def test_evaluators_score_an_episode(fake_model):
    story_id = new_story()
    write_and_approve(story_id, 3)

    snapshot = evaluation.episode_snapshot(story_id, 3)
    results = {r["key"]: r["score"] for r in (
        evaluation.word_count(snapshot), evaluation.repetition(snapshot), evaluation.hook(snapshot),
        evaluation.consistency(snapshot), evaluation.follows_directives(snapshot),
    )}

    # The fake model writes every summary from one template, so the repetition check rightly flags it.
    assert results == {"word_count": 1, "no_repetition": 0, "hook": 0.8, "consistency": 0.8, "follows_directives": None}
    assert snapshot["canon"] == ["Ravi Menon: fact from episode 1", "Ravi Menon: fact from episode 2"]


def test_averages_ignore_missing_scores():
    rows = [{"hook": 1.0, "follows_directives": None}, {"hook": 0.5, "follows_directives": 0.8}]

    averages = evaluation.average_scores(rows)

    assert averages["hook"] == 0.75
    assert averages["follows_directives"] == 0.8
    assert averages["consistency"] is None


def test_evaluations_endpoint_compares_critic_and_human(fake_model):
    from main import app
    api = TestClient(app)
    story_id = new_story()
    write_and_approve(story_id, 2)
    fake_model.critic_verdicts = ["revise"] * 3
    pipeline.write_episode(story_id, 3)
    pipeline.approve_episode(story_id, 3)  # the human overrules the critic

    body = api.get(f"/stories/{story_id}/evaluations").json()

    assert body["langsmith_enabled"] is False
    assert [r["agrees"] for r in body["critic_vs_human"]["rows"]] == [True, True, False]
    assert body["critic_vs_human"]["agreement"] == 0.667
    started = api.post(f"/stories/{story_id}/evaluations")
    assert started.status_code == 409
    assert "LangSmith isn't configured" in started.json()["detail"]
