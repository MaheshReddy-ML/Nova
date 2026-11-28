from fastapi.testclient import TestClient

from nova.app import create_app
from nova.config import Settings
from nova.profile import Profile, Profiles, compact, detail


def sample():
    return Profile.model_validate({
        "name": "Asha Rao", "headline": "AI Researcher", "email": "asha@example.com", "phone": "+91 90000 00000",
        "status": "Final-year B.Tech; research intern.", "goals": ["Postgraduate research"],
        "agent_rules": ["Never suggest beginner projects."],
        "publications": [{"title": "TraceKit: Reproducible Evaluation", "year": "2026", "doi": "10.0/x"}],
        "projects": [{"name": "TraceKit", "summary": "Evaluation harness"}]})


def test_compact_profile_puts_rules_first_and_hides_contact_details():
    text = compact(sample())
    assert text.index("Never suggest beginner projects") < text.index("Publications")
    assert "asha@example.com" not in text and "90000" not in text
    assert "phone" not in detail(sample())


def test_profile_round_trip(tmp_path):
    store = Profiles(tmp_path / "profile.json")
    assert store.load().name == ""
    store.save(sample())
    assert store.load().publications[0].doi == "10.0/x"
    assert (tmp_path / "profile.json").stat().st_mode & 0o777 == 0o600


def test_profile_api(tmp_path):
    settings = Settings(_env_file=None, nvidia_api_key="test", database_path=tmp_path / "nova.db", workspace_path=tmp_path / "w")
    with TestClient(create_app(settings)) as client:
        headers = {"x-nova-owner": "1"}
        saved = client.put("/api/profile", headers=headers, json=sample().model_dump()).json()
        assert saved["name"] == "Asha Rao"
        assert client.get("/api/profile").json()["goals"] == ["Postgraduate research"]
        assert client.get("/api/state").json()["me"]["name"] == "Asha Rao"
        assert client.put("/api/profile", headers=headers, json={"name": "x", "unknown": 1}).status_code == 409


def test_follow_up_api_lists_due_and_upcoming(tmp_path):
    settings = Settings(_env_file=None, nvidia_api_key="test", database_path=tmp_path / "nova.db", workspace_path=tmp_path / "w")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/follow-ups").json() == {"due": [], "upcoming": []}
        from nova.store import Store
        from nova.toolkit import FollowUps

        FollowUps(Store(tmp_path / "nova.db")).schedule("Clay Studio", days=2, note="Share the concept")
        listed = client.get("/api/follow-ups").json()
        assert listed["due"] == [] and [row["business"] for row in listed["upcoming"]] == ["Clay Studio"]
