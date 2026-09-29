"""The HTTP API, driven the way the frontend drives it."""

from fastapi.testclient import TestClient

from story import config


def client():
    from main import app
    return TestClient(app)


def test_full_review_flow_over_http(fake_model):
    api = client()

    created = api.post("/stories", json={"premise": "A rider's deliveries all go to the dead.", "total_episodes": 16})
    assert created.status_code == 200
    story_id = created.json()["story_id"]

    overview = api.get(f"/stories/{story_id}").json()
    assert overview["story"]["status"] == "arc_review"
    assert len(overview["episodes"]) == 16

    assert api.put(f"/stories/{story_id}/arc", json={"beats": [{"number": 1, "beat": "Ravi's first odd drop."}]}).status_code == 200
    assert api.post(f"/stories/{story_id}/episodes/next", json={}).status_code == 409  # arc not approved
    assert api.post(f"/stories/{story_id}/arc/approve").status_code == 200

    assert api.post(f"/stories/{story_id}/episodes/next", json={"count": 1}).status_code == 200
    episode = api.get(f"/stories/{story_id}/episodes/1").json()
    assert episode["status"] == "in_review"
    assert "Ravi's first odd drop." in "".join(fake_model.prompts_for("Draft"))

    assert api.post(f"/stories/{story_id}/episodes/1/approve").status_code == 200
    assert api.post(f"/stories/{story_id}/feedback", json={"text": "Slow down the romance."}).status_code == 200

    memory = api.get(f"/stories/{story_id}/memory").json()
    assert memory["directives"][0]["text"] == "Slow down the romance."
    assert memory["facts"]

    costs = api.get(f"/stories/{story_id}/costs").json()
    assert costs["projection"]["based_on_episodes"] == 1
    assert costs["projection"]["estimated_total_cost_usd"] > 0


def test_access_key_is_required_when_configured(fake_model, monkeypatch):
    monkeypatch.setattr(config, "ACCESS_KEY", "secret")
    api = client()

    assert api.get("/stories").status_code == 401
    assert api.get("/stories", headers={"X-Access-Key": "secret"}).status_code == 200
    assert api.get("/health").status_code == 200


def test_validation_errors_come_back_as_plain_sentences(fake_model):
    api = client()

    too_few = api.post("/stories", json={"premise": "A rider's deliveries all go to the dead.", "total_episodes": 1})
    too_short = api.post("/stories", json={"premise": "short", "total_episodes": 20})
    missing = api.post("/stories", json={})

    assert too_few.status_code == 422
    assert too_few.json()["detail"] == "Number of episodes must be at least 10."
    assert too_short.json()["detail"] == "The premise is too short: use at least 10 characters."
    assert missing.json()["detail"] == "The premise is required."


def test_missing_things_return_404(fake_model):
    assert client().get("/stories/999").status_code == 404
