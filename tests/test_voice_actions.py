import asyncio
import json

import pytest

from nova.commands import Commands, planned_command
from nova.config import Settings
from nova.domain import MissionInput, NovaError
from nova.research import inspect
from nova.runtime import Runtime
from nova.store import Store


@pytest.fixture
def runtime(tmp_path):
    settings = Settings(_env_file=None, database_path=tmp_path / "nova.db", workspace_path=tmp_path / "work")
    store = Store(settings.database_path)
    yield Runtime(settings, store, None, None)
    store.db.close()


def save_research(runtime):
    store = runtime.store
    item, _ = runtime.submit(MissionInput(title="Elm Studio website research", workflow="research",
                                           candidates=[{"name":"Elm Studio","url":"https://example.org/"}]))
    evidence = {"name":"Elm Studio","url":"https://example.org/","score":15,
                "findings":[{"observation":"A heading was missing."}], "public_emails":["sales@example.org"]}
    with store.db:
        store.db.execute("INSERT INTO checkpoints VALUES(?,?,?,?)", (item["id"], 0, "audit_1",
            '{"name":"Elm Studio","url":"https://example.org/","public_emails":["sales@example.org"]}'))
        store.db.execute("INSERT INTO checkpoints VALUES(?,?,?,?)", (item["id"], 1, "report", json.dumps({"sources":[evidence]})))
        store.db.execute("UPDATE tasks SET state='completed',cursor=2 WHERE id=?", (item["id"],))
    return item["id"]


async def test_natural_review_starts_an_actual_research_workflow(runtime):
    result = await Commands(runtime).run("Could you check example.org for me?", None)
    task = runtime.store.view(runtime.store.get(result.task_id))
    assert task["spec"]["workflow"] == "research"
    assert task["spec"]["candidates"][0]["url"] == "https://example.org"
    assert runtime.plan(MissionInput.model_validate(task["spec"]), {}) == ["audit_1", "report"]


async def test_references_reuse_project_and_contact_is_draft_only(runtime):
    key = save_research(runtime)
    agent = Commands(runtime)
    summary = await agent.run("What did you find about the website?", key)
    assert "A heading was missing." in summary.text
    result = await agent.run("Contact them", key)
    assert result.draft_id and result.task_id == key
    assert runtime.business.draft(result.draft_id)["status"] == "pending"
    assert runtime.outreach.channels(key)["emails"] == ["sales@example.org"]
    assert runtime.store.db.execute("SELECT COUNT(*) FROM email_delivery").fetchone()[0] == 0
    with pytest.raises(NovaError):
        await agent.run("Contact unrelated business", key)


async def test_spoken_business_name_matches_known_site_over_failed_lookup(runtime):
    store = runtime.store
    failed, _ = runtime.submit(MissionInput(title="Business research the Clay Sutra site", workflow="research",
                                             business_search="the Clay Sutra site"))
    with store.db:
        store.db.execute("UPDATE tasks SET state='failed' WHERE id=?", (failed["id"],))
    known, _ = runtime.submit(MissionInput(title="Saved pottery studio project", candidates=[
        {"name":"Claysutra Pottery Studio", "url":"https://www.claysutra.com/"},
        {"name":"Other Studio", "url":"https://example.org/"},
    ]))
    with store.db:
        store.db.execute("UPDATE tasks SET state='completed' WHERE id=?", (known["id"],))
    command = await Commands(runtime).run("Review the Clay Sutra website.", None)
    spec = store.view(store.get(command.task_id))["spec"]
    assert spec["business_search"] is None
    assert [item["url"] for item in spec["candidates"]] == ["https://www.claysutra.com/"]


async def test_contact_during_research_is_persisted_and_prepared_after_report(runtime):
    spec = MissionInput(title="Elm Studio website research", workflow="research",
                        candidates=[{"name":"Elm Studio", "url":"https://example.org/"}])
    task, _ = runtime.submit(spec)
    result = await Commands(runtime).run("Contact them", task["id"])
    assert result.draft_id is None and runtime.outreach.contact_requested(task["id"])
    evidence = {"name":"Elm Studio", "url":"https://example.org/", "score":8,
                "findings":[{"observation":"No label."}]}
    report = await runtime.step(task["id"], "report", spec, {"audit_1": evidence})
    with runtime.store.db:
        report.commit(runtime.store.db)
    assert runtime.business.list(task["id"])[0]["status"] == "pending"


async def test_email_confirmation_checks_revision_and_deduplicates_concurrent_sends(runtime, monkeypatch):
    draft = runtime.business.contact_draft(save_research(runtime))
    sender = runtime.outreach
    sent = []
    monkeypatch.setattr(sender, "configured", lambda: True)
    monkeypatch.setattr(sender, "deliver_message", lambda preview: sent.append(preview))
    preview = sender.preview(draft["id"], "sales@example.org")
    with pytest.raises(NovaError, match="changed"):
        await sender.send(draft["id"], "somebody@example.org", preview["digest"])
    results = await asyncio.gather(*[sender.send(draft["id"], preview["recipient"], preview["digest"]) for _ in range(2)],
                                   return_exceptions=True)
    assert results[0] == {"state":"accepted"} and isinstance(results[1], NovaError)
    assert len(sent) == 1


async def test_model_router_does_not_accept_invented_targets(runtime):
    from nova.commands import Command

    async def fabricated(*args, **kwargs):
        return Command(action="audit", target="some-invented.example.org")
    runtime.gateway = type("Fake", (), {"chat": staticmethod(fabricated)})()
    with pytest.raises(NovaError, match="exact"):
        await Commands(runtime).run("Please carefully review the published business page", None)


def test_contact_discovery_only_returns_public_mailto():
    audit = inspect("https://example.org", """
      <html lang="en"><head><title>Elm</title></head><body>
      <a href="/booking">Book</a><a href="/contact">Contact</a>
      <a href="mailto:sales@example.org?subject=Hi">Sales</a>
      <a href="mailto:bad%0A@example.org">Bad value</a>
      </body></html>
    """, 1)
    assert audit["contact_page"] == "https://example.org/contact"
    assert audit["public_emails"] == ["sales@example.org"]
    assert planned_command("Should we review example.org?") == "review example.org"


def test_microphone_turn_executes_the_same_router(tmp_path):
    from fastapi.testclient import TestClient
    from nova.app import create_app

    settings = Settings(_env_file=None, speech_streaming=False, database_path=tmp_path / "voice.db",
                        workspace_path=tmp_path / "work")
    app = create_app(settings)

    async def recognize(audio):
        assert audio.startswith(b"RIFF")
        return "Research ceramic glaze"

    async def sound(text, voice):
        yield "pcm", bytes(120)

    async def sources(subject):
        return {"provider":"Fixture", "sources":[{"name":subject, "url":"https://example.org", "extract":"Fixture."}]}

    with TestClient(app, base_url="http://127.0.0.1") as client:
        runtime = app.state.runtime
        runtime.gateway.transcribe = recognize
        runtime.gateway.stream_speech = sound
        runtime.research.topic = sources
        with client.websocket_connect("ws://127.0.0.1/voice", headers={"origin":"http://127.0.0.1"}) as ws:
            ws.send_json({"type":"voice", "enabled":True})
            ws.send_json({"type":"audio_start"})
            ws.send_bytes((9000).to_bytes(2, "little", signed=True) * 1800)
            ws.send_bytes((9000).to_bytes(2, "little", signed=True) * 1800)
            ws.send_json({"type":"audio_end"})
            kinds, task_id = [], None
            while "done" not in kinds:
                item = ws.receive_json()
                kinds.append(item["type"])
                if item["type"] == "action":
                    task_id = item["task_id"]
            assert "transcript" in kinds and "pcm" in kinds and task_id
        assert client.get("/api/tasks/" + task_id).json()["task"]["spec"]["workflow"] == "topic"
