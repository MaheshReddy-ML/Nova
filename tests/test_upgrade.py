import io
import sqlite3
import time

import httpx
import pytest
from pydantic import ValidationError

from nova.app import create_app
from nova.business import Business, DraftEdit, EntryInput
from nova.config import EMBED, OMNI, Settings
from nova.conversation import mode_for_text, phrase_boundary
from nova.domain import MissionInput, NovaError, State
from nova.gateway import Gateway
from nova.notifications import TelegramDelivery
from nova.scheduling import RepeatInput, Schedules
from nova.store import Store, encoded


@pytest.fixture
def setup(tmp_path):
    settings = Settings(_env_file=None, nvidia_api_key="unit-key", database_path=tmp_path / "state.db",
                        workspace_path=tmp_path / "workspace")
    store = Store(settings.database_path)
    yield settings, store
    store.db.close()


@pytest.fixture
def proposal():
    return {
        "business": "Sample Studio", "source": "https://example.com/",
        "observations": ["One of two form fields had no associated label."],
        "scope": ["Add persistent labels to the form."], "demonstrated": ["Working form interaction"],
        "verification": ["desktop", "mobile", "tablet"], "effort_hours": 8, "proposed_price_inr": 9600,
        "rate_basis": "Planning assumption of INR 1,200 per hour.", "limitations": ["Confirm scope before quoting."],
    }


def completed(store, proposal):
    key = store.submit(MissionInput(title="Legacy project", candidates=[{"name": "Sample Studio", "url": "https://example.com/"}]))[0]["id"]
    with store.db:
        store.db.execute("INSERT INTO checkpoints VALUES(?,?,?,?)", (key, 0, "proposal", encoded({"draft": proposal})))
        store.db.execute("UPDATE tasks SET state='completed',cursor=1 WHERE id=?", (key,))
    return key


def test_database_upgrade_keeps_old_proposal_and_review_history(setup, proposal):
    settings, store = setup
    key = completed(store, proposal)
    with store.db:
        store.db.execute("INSERT INTO approvals VALUES(?,?,?,?,?)", (key, "outreach_review", "{}", "old", "pending"))

    with sqlite3.connect(settings.database_path) as reader:
        assert reader.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='business_drafts'").fetchone()[0] == 0
    business = Business(store)
    Schedules(store)
    assert business.proposal_for(key) == proposal
    assert store.db.execute("SELECT digest FROM approvals WHERE task_id=?", (key,)).fetchone()[0] == "old"
    assert store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert store.db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_draft_is_grounded_and_edit_invalidates_approval(setup, proposal):
    _, store = setup
    key = completed(store, proposal)
    business = Business(store)
    draft = business.create(key, "introduction")
    assert proposal["observations"][0] in draft["body"]
    assert "NOVA\nAI business assistant" in draft["body"]
    assert business.create(key, "introduction")["id"] == draft["id"]
    assert business.review(draft["id"], draft["digest"], True)["status"] == "approved"
    changed = business.edit(draft["id"], DraftEdit(subject="Revised note", body="Local owner comment only.", digest=draft["digest"]))
    assert changed["status"] == "pending" and changed["origin"] == "owner_edited"
    with pytest.raises(NovaError, match="latest"):
        business.review(draft["id"], draft["digest"], True)
    assert "<script>" not in Business.email_export({**draft, "body": "<script>bad</script>"}, "html")


def test_finance_calculates_actuals_and_deduplicates(setup, proposal):
    _, store = setup
    task = completed(store, proposal)
    business = Business(store)
    with pytest.raises(NovaError, match="no recorded invoice"):
        business.create(task, "reminder")
    invoice = EntryInput(task_id=task, kind="invoice", reference="A12", amount_paise=550000, occurred_on="2026-11-01")
    payment = EntryInput(task_id=task, kind="payment", reference="P12", invoice_reference="A12", amount_paise=200000, occurred_on="2026-11-02")
    business.add_entry(invoice)
    assert business.add_entry(payment) == business.add_entry(payment)
    assert business.ledger()["outstanding_paise"] == 350000
    assert "INR 3,500.00" in business.create(task, "reminder")["body"]
    with pytest.raises(NovaError, match="outstanding"):
        business.add_entry(payment.model_copy(update={"amount_paise": 400000, "reference": "P13"}))


def test_repeating_schedules_survive_restart_without_overlapping_or_replaying(setup):
    _, store = setup
    schedules = Schedules(store)
    now = time.time()
    mission = MissionInput(title="Repeat report", workflow="brief", objective="Review the current verified status.")
    record = schedules.create(RepeatInput(mission=mission, every_hours=24, first_at=now - 3 * 86400))
    schedules.materialize(now)
    assert len(store.tasks()) == 1
    schedules.materialize(now + 86401)
    assert len(store.tasks()) == 1
    first_task = schedules.get(record["id"])["latest_task"]
    with store.db:
        store.transition(first_task, State.COMPLETE, "verified")
    schedules = Schedules(store)
    schedules.materialize(now + 2 * 86400 + 1)
    assert len(store.tasks()) == 2
    schedules.change(record["id"], False)
    schedules.materialize(now + 4 * 86400)
    assert len(store.tasks()) == 2


async def test_only_verified_telegram_digest_can_submit_once(setup):
    settings, store = setup
    token = "123456:" + "A" * 25
    settings = settings.model_copy(update={"telegram_bot_token": type(settings.telegram_bot_token)(token),
                                           "telegram_owner_chat_id": "123456789"})
    requests = []
    def send(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})
    delivery = TelegramDelivery(settings, store, httpx.MockTransport(send))
    with store.db:
        event_id = store.event("notification", "Mission is complete.")
    preview = delivery.preview(event_id)
    with pytest.raises(NovaError):
        await delivery.deliver(event_id, "0" * 64)
    assert await delivery.deliver(event_id, preview["digest"]) == {"status": "sent"}
    with pytest.raises(NovaError, match="already exists"):
        await delivery.deliver(event_id, preview["digest"])
    assert len(requests) == 1 and requests[0].url.host == "api.telegram.org"
    assert token not in str(preview)


async def test_multimodal_routes_and_embedding_cache(setup):
    settings, store = setup
    seen = []
    def reply(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": EMBED}, {"id": OMNI}]})
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [.9, .1]}], "usage": {"total_tokens": 3}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Give the primary action more space."}}],
                                        "usage": {"total_tokens": 13}})
    gateway = Gateway(settings, store, httpx.MockTransport(reply))
    try:
        assert await gateway.embeddings(["public fixture"], mode="query") == [[.9, .1]]
        assert await gateway.embeddings(["public fixture"], mode="query") == [[.9, .1]]
        assert seen.count("/v1/embeddings") == 1
        assert (await gateway.visual_review(b"\x89PNG\r\n\x1a\n" + b"fixture", "public QA"))["model"] == OMNI
        assert len(store.usage()) == 2
    finally:
        await gateway.close()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, nvidia_base_url="https://example.com/v1")


def test_exports_are_readable_and_keep_formula_binary_safe(proposal):
    from docx import Document
    from openpyxl import load_workbook
    from pptx import Presentation

    from nova.exports import deck, document, workbook

    doc = Document(io.BytesIO(document(proposal, "proposal")))
    assert "Website Improvement Proposal" == doc.paragraphs[0].text
    estimate = workbook({**proposal, "business": "=2+2"})
    book = load_workbook(io.BytesIO(estimate))
    assert book.active["B5"].value == "=B3*B4"
    assert book.active["B1"].data_type == "s"
    assert load_workbook(io.BytesIO(estimate), data_only=True).active["B5"].value == 9600
    assert len(Presentation(io.BytesIO(deck(proposal))).slides) == 5


def test_voice_modes_and_bounded_phrase_rules():
    assert mode_for_text("Please explain the API error", "auto") == "technical"
    assert mode_for_text("Primary plan", "presentation") == "presentation"
    assert phrase_boundary("The plan we discussed with Dr. Nguyen looks useful. The next detail") == 52
    assert phrase_boundary("Hello") == 0


def test_preview_is_opaque_and_drafts_have_no_send_api(setup, proposal):
    from fastapi.testclient import TestClient

    settings, store = setup
    task = completed(store, proposal)
    folder = settings.workspace_path / task
    folder.mkdir(parents=True)
    (folder / "index.html").write_text("<html><body>Fixture</body></html>")
    (folder / "secret.txt").write_text("must not be served")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.get("/health").json()["version"] == "2.0.0"
        preview = client.get(f"/projects/{task}/index.html")
        policy = preview.headers["Content-Security-Policy"]
        assert "sandbox allow-scripts" in policy and "allow-same-origin" not in policy and "connect-src 'none'" in policy
        assert client.get(f"/projects/{task}/secret.txt").status_code == 404
        assert client.post("/api/drafts", json={"task_id":task}).status_code == 403
        headers = {"x-nova-owner": "1"}
        draft = client.post("/api/drafts", json={"task_id":task}, headers=headers).json()
        assert draft["status"] == "pending"
        assert client.post(f"/api/drafts/{draft['id']}/send", headers=headers).status_code == 404
        assert client.get(f"/api/drafts/{draft['id']}/export/txt").status_code == 200
