import asyncio
import json
import time

import httpx
import pytest

from nova.app import create_app
from nova.config import BOLT, Settings
from nova.conversation import as_wav, local_intent
from nova.domain import Brief, MissionInput, NovaError, State
from nova.gateway import Capability, Gateway
from nova.research import PublicResearch, directory_links, inspect
from nova.runtime import Result, Runtime
from nova.store import Store


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, nvidia_api_key="test-only", database_path=tmp_path / "nova.db",
                    workspace_path=tmp_path / "projects", max_retries=1)


def brief(priority=5, objective="Plan a small storefront", **options):
    return MissionInput(title="Project brief", workflow="brief", objective=objective, priority=priority, **options)


async def until(predicate, timeout=5):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(.02)


@pytest.mark.parametrize("target", ["http://127.0.0.1/", "http://localhost/", "http://169.254.169.254/"])
async def test_public_research_blocks_internal_addresses(tmp_path, target):
    store = Store(tmp_path / "test.db")
    research = PublicResearch(store)
    try:
        with pytest.raises(NovaError, match="public"):
            await research.destination(target)
    finally:
        await research.close()
        store.db.close()


def test_website_findings_credit_existing_booking_and_check_labels():
    report = inspect("https://example.com/", """<html lang="en"><head><title>Studio</title>
      <meta name="viewport" content="width=device-width"></head><body>
      <main><h1>Studio</h1></main><section><a href="/workshops">Book now</a>
      <form><label for="email">Email</label><input id="email" required>
      <input id="name" placeholder="Your name"></form></section></body></html>""", 10)
    assert report["next_url"] == "https://example.com/workshops"
    assert report["unlabeled_fields"] == 1
    assert len(report["findings"]) == 1
    assert "1 of 2" in report["findings"][0]["observation"]


def test_directory_preserves_attribution_and_ignores_unrelated_links():
    source = "https://guide.example.com/art-studios/"
    candidates = directory_links(source, """<article>
      <a href="https://www.studio.example.com/">Studio A | Official website</a>
      <a href="https://studio.example.com/">Duplicate Studio</a>
      <a href="https://studio2.example.com/events">Deep link</a>
      <a href="https://www.instagram.com/">Instagram</a>
      <a href="javascript:alert(1)">Untrusted content</a>
      <a href="https://independent.example.org/">Studio B</a>
    </article>""")
    assert [item.name for item in candidates] == ["Studio A", "Studio B"]
    assert all(item.listed_by == source for item in candidates)


async def test_directory_checkpoints_schedule_only_extracted_candidates(settings):
    store = Store(settings.database_path)
    runtime = Runtime(settings, store, None, None)
    seen = []
    async def step(task_id, name, spec, checkpoints):
        seen.append(name)
        if name == "discover":
            return Result({"source": spec.directory_url, "candidates": [{"name": "Demo", "url": "https://example.com/"}]})
        return Result({"finished": name})
    runtime.step = step
    runtime.start()
    try:
        task, _ = runtime.submit(MissionInput(title="Directory review", directory_url="https://directory.example.com/"))
        await until(lambda: store.get(task["id"])["state"] == State.COMPLETE)
        assert seen == ["discover", "audit_1", "rank", "build", "verify", "proposal"]
    finally:
        await runtime.close()
        store.db.close()


def test_idempotency_schedule_and_emergency_stop(settings):
    store = Store(settings.database_path)
    try:
        first, created = store.submit(brief(run_at=time.time() + 3600))
        duplicate, is_new = store.submit(MissionInput.model_validate({**first["spec"], "title":"Rename"}))
        assert created and not is_new and first["id"] == duplicate["id"]
        child, _ = store.submit(brief(objective="Write a related memo", depends_on=first["id"]))
        assert store.claim(set()) is None
        store.stop(True)
        assert store.get(first["id"])["state"] == State.CANCELLED
        assert store.get(child["id"])["state"] == State.CANCELLED
        with pytest.raises(NovaError, match="stop"):
            store.submit(brief(objective="Another task"))
    finally:
        store.db.close()
    reopened = Store(settings.database_path)
    assert reopened.stopped()
    reopened.db.close()


async def test_restart_resumes_without_repeating_checkpoints(settings):
    store = Store(settings.database_path)
    spec = MissionInput(title="Website review", candidates=[{"name": "Example", "url": "https://example.com/"}])
    task, _ = store.submit(spec)
    store.claim(set())
    store.save(task["id"], 0, "audit_1", {"saved": True})
    store.db.close()

    store = Store(settings.database_path)
    runtime = Runtime(settings, store, None, None)
    visited = []

    async def step(task_id, name, spec, checkpoints):
        assert checkpoints["audit_1"] == {"saved": True}
        visited.append(name)
        return Result({"completed": name})

    runtime.step = step
    runtime.start()
    try:
        await until(lambda: store.get(task["id"])["state"] == State.COMPLETE)
        assert visited == ["rank", "build", "verify", "proposal"]
        assert store.get(task["id"])["cursor"] == 5
    finally:
        await runtime.close()
        store.db.close()


async def test_background_pause_resume_and_retry(settings):
    store = Store(settings.database_path)
    runtime = Runtime(settings, store, None, None)
    started = asyncio.Event()
    finish = asyncio.Event()
    calls = 0

    async def step(*args):
        nonlocal calls
        calls += 1
        started.set()
        if calls == 2:
            raise NovaError("transient", "Temporary failure", transient=True)
        await finish.wait()
        return Result({"done": "true"})

    runtime.step = step
    runtime.start()
    try:
        task, _ = runtime.submit(brief())
        await asyncio.wait_for(started.wait(), 1)
        assert "waiting for tool" in local_intent(runtime, "What are you doing?")
        assert "paused" in local_intent(runtime, "Pause " + task["id"])
        await until(lambda: task["id"] not in runtime.running)
        assert "queued" in local_intent(runtime, "Resume " + task["id"])
        await until(lambda: store.get(task["id"])["state"] == State.RETRY)
        assert store.get(task["id"])["cursor"] == 0
        finish.set()
        await until(lambda: store.get(task["id"])["state"] == State.COMPLETE)
        assert calls == 3
    finally:
        await runtime.close()
        store.db.close()


async def test_routes_budget_and_invalid_structured_output(settings):
    settings = settings.model_copy(update={"planner_model": "retired/model", "max_calls_hour": 1})
    store = Store(settings.database_path)

    def provider(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": BOLT}]})
        assert json.loads(request.content)["model"] == BOLT
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"action":"publish"}'}}],
                                        "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    gateway = Gateway(settings, store, httpx.MockTransport(provider))
    try:
        context = [{"role":"user", "content":"Prepare a brief"}]
        with pytest.raises(NovaError) as first:
            await gateway.chat(Capability.PLANNING, context, schema=Brief)
        assert first.value.code == "invalid_structure"
        with pytest.raises(NovaError) as second:
            await gateway.chat(Capability.PLANNING, context)
        assert second.value.code == "model_budget"
        assert store.usage()[0]["reported_tokens"] == 15
        assert store.usage()[0]["calls"] == 1
    finally:
        await gateway.close()
        store.db.close()


async def test_foreground_stream_runs_while_background_waits(settings):
    store = Store(settings.database_path)
    pending = asyncio.Event()
    release = asyncio.Event()

    async def provider(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": BOLT}]})
        payload = json.loads(request.content)
        if payload["stream"]:
            return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"I can help."}}]}\n\n'
                                            'data: {"usage":{"total_tokens":7}}\n\ndata: [DONE]\n\n')
        pending.set()
        await release.wait()
        return httpx.Response(200, json={"choices": [{"message": {"content": "Background answer"}}]})

    gateway = Gateway(settings, store, httpx.MockTransport(provider))
    messages = [{"role":"user", "content":"An objective"}]
    background = asyncio.create_task(gateway.chat(Capability.PLANNING, messages, lane="background"))
    try:
        await asyncio.wait_for(pending.wait(), 1)
        async with asyncio.timeout(1):
            assert "".join([chunk async for chunk in gateway.stream_chat(messages)]) == "I can help."
        assert not background.done()
        release.set()
        assert await background == "Background answer"
        assert {row["lane"] for row in store.usage()} == {"foreground", "background"}
    finally:
        release.set()
        await asyncio.gather(background, return_exceptions=True)
        await gateway.close()
        store.db.close()


def test_silent_capture_does_not_become_an_utterance():
    assert not as_wav(bytes(16000))
    loud = (4000).to_bytes(2, "little", signed=True) * 3500
    assert as_wav(loud).startswith(b"RIFF")


def test_owner_mutation_and_voice_origin_controls(settings):
    from fastapi.testclient import TestClient

    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.get("/health").status_code == 200
        assert client.post("/api/tasks", json=brief().model_dump()).status_code == 403
        assert client.post("/api/stop/enable", headers={"x-nova-owner":"1", "origin":"https://example.com"}).status_code == 403
        assert client.post("/api/payments/send", headers={"x-nova-owner":"1"}).status_code == 404
        with client.websocket_connect("ws://127.0.0.1/voice", headers={"origin": "http://127.0.0.1"}) as ws:
            ws.send_json({"type":"text", "text":"What are you doing?"})
            assert ws.receive_json()["type"] == "clear"
            assert ws.receive_json()["type"] == "processing"
            assert ws.receive_json()["text"] == "There are no missions yet."
            assert ws.receive_json()["type"] == "done"
        assert client.get("/api/state").json()["usage"] == []
