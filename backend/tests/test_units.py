"""Small pure functions."""

from story import config
from story.critic import rule_problems, similar_earlier_episodes
from story.models import Character
from story.planner import tidy_act_ranges
from story.schemas import Draft, PlannedAct


def act(number, first, last):
    return PlannedAct(number=number, title="t", goal="g", turning_point="p", first_episode=first, last_episode=last)


def test_act_ranges_are_made_contiguous():
    messy = [act(2, 30, 50), act(1, 1, 25), act(3, 60, 90)]

    tidy = tidy_act_ranges(messy, 100)

    assert [(a.first_episode, a.last_episode) for a in tidy] == [(1, 25), (26, 50), (51, 100)]
    assert [a.number for a in tidy] == [1, 2, 3]
    assert messy[0].first_episode == 30  # the original isn't changed


def test_short_episodes_are_flagged():
    problems = rule_problems(Draft(title="x", text="too short"), [])
    assert [p.kind for p in problems] == ["length"]


def test_dead_characters_named_in_a_draft_are_flagged_for_checking():
    dead = Character(name="Mr Das", status="dead", status_changed_in=4)
    text = " ".join(["word"] * config.MIN_WORDS) + " Mr Das waved."

    problems = rule_problems(Draft(title="x", text=text), [dead])

    assert [p.kind for p in problems] == ["check"]


def test_new_model_columns_are_added_to_an_older_database(tmp_path):
    from sqlalchemy import inspect, text

    from story import db

    url = f"sqlite:///{tmp_path / 'old.db'}"
    old_engine = db.make_engine(url)
    with old_engine.begin() as connection:  # a directives table from before beat_changes existed
        connection.execute(text("CREATE TABLE directives (id INTEGER PRIMARY KEY, story_id INTEGER, text TEXT)"))

    db.use_database(url)

    columns = {c["name"] for c in inspect(db.engine).get_columns("directives")}
    assert {"beat_changes", "replan_summary", "is_active"} <= columns


def test_openrouter_models_fall_back_to_their_direct_anthropic_twin():
    from story.llm import direct_anthropic_model

    assert direct_anthropic_model("anthropic/claude-sonnet-5.5") == "claude-sonnet-5-5"
    assert direct_anthropic_model("anthropic/claude-haiku-4.5") == "claude-haiku-4-5"
    assert direct_anthropic_model("google/gemini-2.5-flash") == config.DIRECT_FALLBACK_MODEL


def test_near_duplicate_summaries_are_detected():
    earlier = {
        3: "Ravi delivers a parcel to flat 9B and finds the door sealed with wax.",
        4: "Asha confronts the landlord about missing rent books.",
    }
    summary = "Ravi delivers a parcel to flat 9B and finds the door sealed with red wax."

    assert similar_earlier_episodes(summary, earlier) == [3]
