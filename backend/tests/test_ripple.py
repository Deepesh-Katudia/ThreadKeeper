"""Ripple review: editing an approved episode, checking the later ones, and the three human gates.

The story: episode 5 says the parcel is in locker 214, and episode 6 repeats it. The editor
changes episode 5 to locker 117. Episodes 7 and 8 never saw the locker fact, so they must be
cleared without a model call.
"""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from story import config, pipeline, ripple
from story.db import session_scope
from story.models import EpisodeVersion
from story.queries import facts, facts_including_retracted, get_episode, get_story, threads, versions_of
from story.schemas import NewFact
from tests.ripple_helpers import close, edit_and_confirm
from tests.test_pipeline import new_story, write_and_approve
from tests.test_versions import canon

OLD_LINE = "The parcel was still in locker 214."
EDIT = "Episode five, rewritten: the parcel goes into locker 117."


def locker_story(fake_model, monkeypatch) -> int:
    """Eight approved episodes; only episode 6 (and the edited 5) know about the locker."""
    # Keep the window narrow and give episode 6 plenty of facts, so episodes 7-8's writers were
    # never shown the locker fact: that's what lets them be cleared for free.
    monkeypatch.setattr(config, "RECENT_FACT_EPISODES", 1)
    fake_model.extra_facts = {
        5: [NewFact(subject="the locker", statement="locker 214 holds the parcel")],
        6: [NewFact(subject="the stairwell", statement=f"stair detail {k}") for k in range(10)],
    }
    fake_model.draft_extra = {6: OLD_LINE}
    story_id = new_story()
    write_and_approve(story_id, 8)
    fake_model.diffs = {5: lambda prompt: {
        "retract_fact_ids": [fact_id(prompt, "the locker: locker 214 holds the parcel")],
        "new_facts": [NewFact(subject="the locker", statement="locker 117 holds the parcel")],
    }}
    fake_model.checks = {6: ("minor", [(OLD_LINE, "the parcel is in locker 117 now")])}
    fake_model.patches = {6: [(OLD_LINE, "The parcel was still in locker 117.")]}
    return story_id


def fact_id(prompt: str, label: str) -> int:
    return int(re.search(rf"\[(\d+)\] {re.escape(label)}", prompt).group(1))


def ripple_state(ripple_id: int) -> tuple[str, dict]:
    with session_scope() as session:
        found = session.get(ripple.Ripple, ripple_id)
        return found.status, {i.episode_number: i for i in ripple.items_of(session, ripple_id)}


def test_an_edit_changes_nothing_until_the_human_confirms_the_memory(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    before = canon(story_id)

    ripple_id = pipeline.edit_episode(story_id, 5, EDIT)

    status, _ = ripple_state(ripple_id)
    assert status == "confirm_memory"
    assert canon(story_id) == before
    with session_scope() as session:
        assert get_episode(session, story_id, 5).text != EDIT
        found = session.get(ripple.Ripple, ripple_id)
        assert [r["statement"] for r in found.memory_diff["change"]["retracted"]] == ["locker 214 holds the parcel"]


def test_confirming_checks_only_suspicious_episodes(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    ripple_id = edit_and_confirm(story_id, 5, EDIT)

    status, items = ripple_state(ripple_id)
    assert status == "reviewing"
    assert items[6].check_status == "minor"
    assert items[6].proposal["kind"] == "patch" and "locker 117" in items[6].proposal["text"]
    assert (items[7].check_status, items[8].check_status) == ("unaffected", "unaffected")
    checked = fake_model.prompts_for("ContinuityCheck")
    assert len(checked) == 1 and "Episode 6 text:" in checked[0]  # no model call for 7 or 8
    with session_scope() as session:
        statements = [f.statement for f in facts(session, story_id)]
        assert "locker 117 holds the parcel" in statements and "locker 214 holds the parcel" not in statements
        assert get_episode(session, story_id, 5).text == EDIT
        assert get_episode(session, story_id, 6).continuity["check_status"] == "minor"


def test_writing_and_other_edits_wait_for_the_ripple(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    ripple_id = edit_and_confirm(story_id, 5, EDIT)

    with pytest.raises(pipeline.NotAllowed, match="Finish the ripple review for episode 5"):
        pipeline.next_episode_to_write(story_id)
    with pytest.raises(pipeline.NotAllowed, match="Finish the ripple review for episode 5"):
        pipeline.edit_episode(story_id, 3, "Another edit.")

    close(story_id, ripple_id)
    assert pipeline.next_episode_to_write(story_id) == 9


def test_decisions_are_made_in_order_and_accepting_applies_the_fix(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    with session_scope() as session:  # give episode 8 a line that mentions the old locker
        get_episode(session, story_id, 8).text += " Ravi still thought of locker 214."
    fake_model.checks[8] = ("major", [("Ravi still thought of locker 214.", "it is locker 117 now")])
    ripple_id = edit_and_confirm(story_id, 5, EDIT)

    with pytest.raises(pipeline.NotAllowed, match="Decide episode 6 first"):
        ripple.decide_item(story_id, ripple_id, 8, "keep")

    ripple.decide_item(story_id, ripple_id, 6, "accept")
    ripple.decide_item(story_id, ripple_id, 8, "keep", note="Ravi misremembers; that's fine.")

    with session_scope() as session:
        six, eight = get_episode(session, story_id, 6), get_episode(session, story_id, 8)
        assert six.current_version == 2 and "locker 117" in six.text and OLD_LINE not in six.text
        assert [v.source for v in versions_of(session, story_id, 6)] == ["written", "ripple_patch"]
        assert eight.text.endswith("Ravi still thought of locker 214.")  # kept as is
        assert eight.continuity["decision"] == "keep"
    assert any("rewrote episode 6" in p for p in fake_model.prompts_for("MemoryDiff"))  # ep 6's memory followed


def test_a_fix_that_changes_canon_rechecks_later_episodes(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    ripple_id = edit_and_confirm(story_id, 5, EDIT)
    _, items = ripple_state(ripple_id)
    assert items[8].check_status == "unaffected"
    # Accepting episode 6's patch also retracts a stairwell fact that episode 8's writer was shown.
    fake_model.diffs[6] = lambda prompt: {"retract_fact_ids": [fact_id(prompt, "the stairwell: stair detail 9")]}
    fake_model.checks[8] = ("minor", [("Episode 8 ends at a door.", "the stairwell changed")])

    ripple.decide_item(story_id, ripple_id, 6, "accept")

    _, items = ripple_state(ripple_id)
    assert items[8].check_status == "recheck"
    assert items[8].decision is None


def test_new_beats_are_proposed_and_only_applied_after_approval(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    ripple_id = edit_and_confirm(story_id, 5, EDIT)

    ripple.decide_item(story_id, ripple_id, 6, "accept")

    status, _ = ripple_state(ripple_id)
    assert status == "replan_review"
    with session_scope() as session:
        assert get_episode(session, story_id, 9).beat == "beat 9"
        found = session.get(ripple.Ripple, ripple_id)
        assert found.replan["changes"][0] == {"episode": 9, "before": "beat 9", "after": "replanned beat 9"}
    assert "Editor changed episode 5" in fake_model.prompts_for("Replan")[-1]

    ripple.approve_replan(story_id, ripple_id, [9])

    status, _ = ripple_state(ripple_id)
    assert status == "closed"
    with session_scope() as session:
        assert get_episode(session, story_id, 9).beat == "replanned beat 9"
        assert get_episode(session, story_id, 10).beat == "beat 10"  # not selected
    assert pipeline.next_episode_to_write(story_id) == 9


def test_cancelling_before_confirming_leaves_everything_as_it_was(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    pipeline.write_episode(story_id, 9)  # a draft waiting for review
    before = canon(story_id)

    ripple_id = pipeline.edit_episode(story_id, 5, EDIT)
    with session_scope() as session:
        assert get_episode(session, story_id, 9).status == "stale"
    ripple.cancel_ripple(story_id, ripple_id)

    assert canon(story_id) == before
    with session_scope() as session:
        assert [v.version for v in versions_of(session, story_id, 5)] == [1]
        assert get_episode(session, story_id, 9).status == "in_review"
    assert ripple_state(ripple_id)[0] == "cancelled"


def test_the_cost_cap_leaves_unchecked_episodes_pending(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    monkeypatch.setattr(config, "RIPPLE_COST_CAP_USD", 0.001)  # the memory diff alone costs more

    ripple_id = edit_and_confirm(story_id, 5, EDIT)

    _, items = ripple_state(ripple_id)
    assert items[6].check_status == "pending"
    assert fake_model.prompts_for("ContinuityCheck") == []
    with session_scope() as session:
        assert "cost cap" in session.get(ripple.Ripple, ripple_id).summary


def test_retcon_mode_flags_episodes_but_keeps_them(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    with session_scope() as session:
        get_story(session, story_id).history_mode = "retcon"

    ripple_id = edit_and_confirm(story_id, 5, EDIT)

    status, items = ripple_state(ripple_id)
    assert items[6].check_status == "minor" and items[6].decision == "keep"
    assert fake_model.prompts_for("Patch") == []
    assert status == "replan_review"  # nothing waits for a decision; gate 3 still runs


def test_episodes_from_before_versions_and_context_ids_still_ripple(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    with session_scope() as session:  # how the live database looked before this feature
        session.execute(delete(EpisodeVersion))
        for number in range(1, 9):
            episode = get_episode(session, story_id, number)
            episode.current_version, episode.context_ids = None, None
        get_episode(session, story_id, 8).text += " Ravi still thought of locker 214."

    ripple_id = edit_and_confirm(story_id, 5, EDIT)

    _, items = ripple_state(ripple_id)
    assert items[6].check_status == "minor"  # the next episode is always checked
    assert any("locker 214" in r for r in items[8].signals["reasons"])  # found by text search
    assert items[7].check_status == "unaffected"
    with session_scope() as session:
        assert [v.version for v in versions_of(session, story_id, 5)] == [1, 2]


def test_a_thread_answered_by_a_later_episode_survives_an_edit(fake_model):
    story_id = new_story()
    fake_model.opens = {5: ["What is in the parcel"]}
    fake_model.resolves = {6: ["What is in the parcel"]}
    write_and_approve(story_id, 8)

    ripple_id = edit_and_confirm(story_id, 5, "Episode five without the parcel scene.")
    close(story_id, ripple_id)

    with session_scope() as session:
        parcel = [t for t in threads(session, story_id) if t.title == "What is in the parcel"]
        assert [(t.status, t.opened_episode, t.resolved_episode) for t in parcel] == [("resolved", 5, 6)]


def test_every_ripple_model_call_is_named_and_counted(fake_model, monkeypatch):
    story_id = locker_story(fake_model, monkeypatch)
    ripple_id = edit_and_confirm(story_id, 5, EDIT)
    close(story_id, ripple_id, decision="accept")

    with session_scope() as session:
        from story.models import LLMCall
        found = session.get(ripple.Ripple, ripple_id)
        steps = [c.step for c in session.query(LLMCall).filter(LLMCall.created_at >= found.created_at)]
        assert found.cost_usd > 0
    assert steps and all(step.startswith("ripple_") for step in steps)
    assert {"ripple_diff", "ripple_check", "ripple_patch", "ripple_replan"} <= set(steps)


def test_the_ripple_api_walks_through_all_three_gates(fake_model, monkeypatch):
    from main import app
    api = TestClient(app)
    story_id = locker_story(fake_model, monkeypatch)

    edited = api.put(f"/stories/{story_id}/episodes/5", json={"text": EDIT}).json()
    ripple_id = edited["ripple"]["id"]
    assert edited["ripple"]["status"] == "confirm_memory"
    overview = api.get(f"/stories/{story_id}").json()
    assert overview["open_ripple"]["id"] == ripple_id
    assert api.post(f"/stories/{story_id}/episodes/next", json={}).status_code == 409

    assert api.post(f"/stories/{story_id}/ripples/{ripple_id}/confirm-memory", json={}).status_code == 200
    assert api.get(f"/stories/{story_id}/ripples/{ripple_id}").json()["status"] == "reviewing"
    assert api.post(f"/stories/{story_id}/ripples/{ripple_id}/accept-minor").status_code == 200
    assert api.get(f"/stories/{story_id}/ripples/{ripple_id}").json()["status"] == "replan_review"
    closed = api.post(f"/stories/{story_id}/ripples/{ripple_id}/approve-replan", json={}).json()
    assert closed["status"] == "closed" and closed["counts"]["decided"] == 1

    episodes = api.get(f"/stories/{story_id}").json()["episodes"]
    assert episodes[5]["continuity"]["decision"] == "accept" and episodes[5]["current_version"] == 2
    versions = api.get(f"/stories/{story_id}/episodes/5/versions").json()
    assert [(v["version"], v["is_current"]) for v in versions] == [(1, False), (2, True)]
    restored = api.post(f"/stories/{story_id}/episodes/5/versions/1/restore").json()
    assert restored["is_restore"] and restored["status"] == "confirm_memory"
    assert len(api.get(f"/stories/{story_id}/ripples").json()) == 2
    memory = api.get(f"/stories/{story_id}/memory").json()
    assert any(not f["is_active"] and f["retracted_reason"] for f in memory["facts"])
    with session_scope() as session:
        assert any(f.is_active is False for f in facts_including_retracted(session, story_id))
