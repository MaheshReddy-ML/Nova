import asyncio
import fcntl
import hashlib
import io
import json
import math
import re
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import demo, exports
from .business import DraftEdit, DraftInput, EntryInput, FeedbackInput, LeadChange
from .config import Settings
from .conversation import Session
from .domain import Candidate, Control, MissionInput, NovaError, StrictModel
from .gateway import FALLBACK, Capability, Gateway
from .notifications import TelegramDelivery
from .research import PublicResearch
from .runtime import POTTERY_CANDIDATES, Runtime
from .scheduling import RepeatControl, RepeatInput
from .store import Store

STATIC = Path(__file__).parent / "static"
CONTENT_POLICY = ("default-src 'self'; style-src 'self'; script-src 'self'; media-src 'self' blob:; "
                  "object-src 'none'; frame-ancestors 'none'; frame-src 'self'; base-uri 'none'; form-action 'self'")


class Decision(StrictModel):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: bool


class SkillRevision(StrictModel):
    revision: str | None = Field(default=None, max_length=64)


class SemanticSearch(StrictModel):
    query: str = Field(min_length=2, max_length=300)


class Refinement(StrictModel):
    priority_index: int = Field(ge=0, le=2, strict=True)


class EmailRecipient(StrictModel):
    recipient: str = Field(min_length=5, max_length=254)


class OutboxEdit(StrictModel):
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=12, max_length=8000)
    recipient: str | None = Field(default=None, max_length=254)


class Rewrite(StrictModel):
    subject: str = Field(default="", max_length=160)
    body: str = Field(min_length=12, max_length=8000)
    instruction: Literal["shorter", "warmer", "specific"]


class OutboxCompose(OutboxEdit):
    recipient: str = Field(default="", max_length=254)
    business: str = Field(default="", max_length=140)


class EmailDelivery(EmailRecipient):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


def create_app(settings=None, *, transport=None, research_factory=PublicResearch):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        path = settings.database_path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.with_suffix(path.suffix + ".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("A NOVA service is already using this database.") from exc
            store = Store(path)
            gateway = Gateway(settings, store, transport)
            research = (PublicResearch(store, wikidata_contact=settings.wikidata_contact)
                        if research_factory is PublicResearch else research_factory(store))
            if hasattr(research, "brave_key"):
                research.brave_key = settings.brave_search_api_key.get_secret_value()
            runtime = app.state.runtime = Runtime(settings, store, gateway, research)
            app.state.telegram = TelegramDelivery(settings, store)
            runtime.start()
            try:
                yield
            finally:
                await runtime.close()
                await gateway.close()
                await research.close()
                store.db.close()

    app = FastAPI(title="NOVA", version=settings.release_version, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.draining = False
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    live_voice = asyncio.Semaphore(4)
    review_browser = asyncio.Semaphore(1)

    @app.middleware("http")
    async def local_owner(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            host = request.headers.get("host", "")
            origin = request.headers.get("origin")
            if request.headers.get("x-nova-owner") != "1" or (origin and origin != f"http://{host}"):
                return JSONResponse({"error": "origin", "message": "Owner mutations require a local NOVA request."}, 403)
        response = await call_next(request)
        if "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = CONTENT_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(_request, exc):
        return JSONResponse({"error": "input", "message": "; ".join(
            item.get("msg", "Invalid input.") for item in exc.errors()[:3]
        )}, 422)

    @app.exception_handler(NovaError)
    async def failure(_request, exc):
        status = 404 if exc.code.endswith("_missing") else 409
        return JSONResponse({"error": exc.code, "message": str(exc)}, status)

    @app.get("/")
    async def dashboard():
        return FileResponse(STATIC / "index.html")

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    @app.get("/static/brand/{asset}")
    async def brand_asset(asset: str):
        if asset not in {"mark.svg", "mark-128.png", "lockup-light.png", "lockup-dark.png", "manrope-800.woff2"}:
            return JSONResponse({"message": "Asset not found."}, 404)
        return FileResponse(STATIC / "brand" / asset)

    @app.get("/static/{asset}")
    async def asset(asset: str):
        if asset not in {"dashboard.css", "dashboard.js", "mic.js"}:
            return JSONResponse({"message": "Asset not found."}, 404)
        return FileResponse(STATIC / asset)

    @app.get("/health")
    async def health():
        runtime = app.state.runtime
        return {"service": settings.agent_name, "version": settings.release_version,
                "stopped": runtime.store.stopped(), "workers": settings.workers, "running": len(runtime.running)}

    @app.get("/api/state")
    async def state():
        runtime = app.state.runtime
        store = runtime.store
        leads = [{**dict(row), "evidence": json.loads(row["evidence"])} for row in store.db.execute(
            "SELECT * FROM leads ORDER BY score DESC LIMIT 50"
        )]
        approvals = [{**dict(row), "payload": json.loads(row["payload"])} for row in store.db.execute(
            "SELECT * FROM approvals ORDER BY rowid DESC LIMIT 50"
        )]
        counts = {row["state"]: row["count"] for row in store.db.execute(
            "SELECT state, COUNT(*) AS count FROM tasks GROUP BY state"
        )}
        model_caps = runtime.gateway
        models = store.cached("nvidia:catalogue")
        voices = store.cached(runtime.gateway.voices_key())
        last = store.db.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
        stats = {row["kind"]: row["count"] for row in store.db.execute(
            "SELECT kind, COUNT(*) AS count FROM events WHERE kind IN ('tool','cache','notification') GROUP BY kind"
        )}
        return {
            "agent": settings.agent_name, "version": settings.release_version, "stopped": store.stopped(),
            "tasks": store.tasks(), "counts": counts, "leads": leads, "approvals": approvals, "usage": store.usage(),
            "catalogue_count": len(models) if models is not None else None,
            "routes": {item.value: model_caps.resolve(item, models) for item in FALLBACK},
            "voice": {"enabled": settings.voice_enabled, "provider": runtime.gateway.speech_provider,
                      "preferred": settings.deepgram_voice if runtime.gateway.deepgram_active else settings.tts_voice,
                      "asr_streaming": runtime.gateway.asr_streaming, "tts_streaming": runtime.gateway.tts_streaming,
                      "voices": voices or [],
                      "language": settings.tts_language},
            "spending_limit_inr": 0, "autonomous": settings.autonomous_mode,
            "recent_events": store.events(max(0, last - 24)), "stats": stats,
            "presets": {"hyderabad_studios": POTTERY_CANDIDATES},
            "email_configured": runtime.outreach.configured(),
            "email": {"configured": runtime.outreach.configured(), "sender": settings.smtp_from or None,
                      "owner": settings.owner_emails[0] if settings.owner_emails else None,
                      "sent_last_hour": runtime.outbox.sent_last_hour(), "hourly_limit": settings.max_emails_hour},
            "outbox": runtime.outbox.list(30),
            "agent": {"model": settings.agent_model, "max_steps": settings.agent_max_steps,
                      "calls_hour_limit": settings.max_calls_hour,
                      "calls_last_hour": store.db.execute("SELECT COUNT(*) FROM usage WHERE started>? AND lane!='speech'",
                                                          (time.time() - 3600,)).fetchone()[0],
                      "tokens_today": store.db.execute("SELECT COALESCE(SUM(COALESCE(total,reserved)),0) FROM usage "
                                                       "WHERE started>? AND lane!='speech'", (time.time() - 86400,)).fetchone()[0],
                      "daily_token_limit": settings.max_daily_tokens},
            "owner": settings.owner_name or None,
            "profile_complete": bool(settings.business_name and settings.business_about),
            "me": (lambda p: {"name": p.name, "headline": p.headline, "status": p.status} if p.name else None)(
                runtime.profiles.load()),
        }

    @app.post("/api/providers")
    async def providers():
        provider = app.state.runtime.gateway
        results = {"catalogue": None, "voices": None, "errors": {}}
        for name, check in (("catalogue", provider.catalogue), ("voices", provider.voices)):
            try:
                data = await check(refresh=True)
                results[name] = len(data)
            except NovaError as exc:
                results["errors"][name] = str(exc)
        return results

    @app.get("/api/agent/calls")
    async def agent_calls(turn: str | None = None, limit: int = 60):
        from . import provenance

        db = app.state.runtime.store.db
        provenance.ensure(db)
        query = "SELECT * FROM tool_calls " + ("WHERE turn=? " if turn else "") + "ORDER BY id DESC LIMIT ?"
        rows = db.execute(query, ((turn, min(limit, 200)) if turn else (min(limit, 200),))).fetchall()
        return {"calls": [{**dict(row), "args": json.loads(row["args"]), "fetches": json.loads(row["fetches"])} for row in rows]}

    @app.get("/api/models/bench")
    async def model_bench():
        path = Path("output/model-bench/results.json")
        results = json.loads(path.read_text()) if path.is_file() else {}
        return {"results": results, "routing": {"agent": settings.agent_model, "small_talk": settings.fast_model,
                                                "site": settings.site_model, "vision": settings.vision_model}}

    @app.post("/api/research/search")
    async def research_search(data: SemanticSearch):
        return await app.state.runtime.research.search(data.query, interactive=True)

    @app.post("/api/tasks")
    async def submit(spec: MissionInput):
        task, created = app.state.runtime.submit(spec)
        return JSONResponse({"task": task, "created": created}, 201 if created else 200)

    @app.get("/api/tasks/{task_id}")
    async def inspect(task_id: str):
        runtime = app.state.runtime
        store = runtime.store
        task = store.view(store.get(task_id))
        events = [{**dict(row), "data": json.loads(row["data"])} for row in store.db.execute(
            "SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,)
        )]
        checkpoints = store.checkpoints(task_id)
        spec = MissionInput.model_validate(task["spec"])
        stages = runtime.plan(spec, checkpoints)
        stage_status = task["state"] if task["state"] in {"paused", "cancelled", "failed"} else (
            "pending" if task["state"] in {"queued", "retry_scheduled"} else "running"
        )
        return {
            "task": task, "checkpoints": checkpoints, "usage": store.usage(task_id),
            "events": events[-150:], "skill_activations": runtime.skills.observed(task_id),
            "workflow_stages": [
                {"id": step, "name": step.replace("_", " "), "position": index + 1,
                 "state": "completed" if step in checkpoints else (stage_status if index == task["cursor"] else "pending")}
                for index, step in enumerate(stages)
            ],
            "revisions": demo.revision_history(settings.workspace_path, task_id) if task["state"] == "completed" else [],
            "audit_cache_hits": sum(item.get("cache_hit", False) for key, item in checkpoints.items() if key.startswith("audit_")),
            "tool_calls": sum(row["kind"] == "tool" for row in events),
            "execution_seconds": round(sum(row["data"].get("duration_seconds", 0)
                                           for row in events if row["kind"] == "attempt"), 3),
        }

    @app.get("/api/skills")
    async def skills(q: str = ""):
        return {"skills": app.state.runtime.skills.list(q[:200])}

    @app.get("/api/skills/{skill_id}")
    async def skill(skill_id: str):
        return app.state.runtime.skills.inspect(skill_id)

    @app.get("/api/skills/{skill_id}/reference")
    async def skill_reference(skill_id: str, path: str, heading: str | None = None):
        return app.state.runtime.skills.reference(skill_id, path[:200], heading[:100] if heading else None)

    @app.post("/api/skills/{skill_id}/{action}")
    async def change_skill(skill_id: str, action: str, selection: SkillRevision | None = None):
        runtime = app.state.runtime
        if action == "evaluate":
            return runtime.skills.evaluate(skill_id)
        result = runtime.skills.mutate(skill_id, action, selection.revision if selection else None)
        runtime.store.log("skill", "Owner updated a skill", skill_id=skill_id, action=action)
        return result

    @app.get("/api/schedules")
    async def schedules():
        return {"schedules": app.state.runtime.schedules.list()}

    @app.post("/api/schedules")
    async def create_schedule(data: RepeatInput):
        runtime = app.state.runtime
        item = runtime.schedules.create(data)
        runtime.wake.set()
        return item

    @app.post("/api/schedules/{schedule_id}")
    async def change_schedule(schedule_id: str, data: RepeatControl):
        runtime = app.state.runtime
        item = runtime.schedules.change(schedule_id, data.enabled)
        runtime.wake.set()
        return item

    @app.get("/api/profile")
    async def get_profile():
        return app.state.runtime.profiles.load().model_dump()

    @app.put("/api/profile")
    async def put_profile(request: Request):
        from .profile import Profile

        try:
            profile = Profile.model_validate(await request.json())
        except ValueError as exc:
            raise NovaError("profile_input", "The profile has an invalid field.") from exc
        saved = app.state.runtime.profiles.save(profile)
        app.state.runtime.store.log("memory", "Owner updated their profile")
        return saved.model_dump()

    @app.get("/api/outbox")
    async def outbox():
        return {"messages": app.state.runtime.outbox.list(100)}

    @app.post("/api/outbox")
    async def compose(data: OutboxCompose):
        return app.state.runtime.outbox.draft(data.recipient, data.subject, data.body, business=data.business)

    @app.put("/api/outbox/{message_id}")
    async def edit_outbox(message_id: str, data: OutboxEdit):
        return app.state.runtime.outbox.edit(message_id, data.subject, data.body, data.recipient)

    @app.post("/api/outbox/rewrite")
    async def rewrite_email(data: Rewrite):
        asks = {"shorter": "Cut it to about 60% of the length. Keep the greeting, the key point, the call to action and the signature.",
                "warmer": "Make the tone warmer and more personal without adding hype or new claims.",
                "specific": "Make it more concrete: sharpen the observation and the benefit using only facts already in the email."}
        message = await app.state.runtime.gateway.agent_chat([
            {"role": "system", "content": "You edit outreach emails. Never add facts, numbers, names or links that are not "
             "already in the email. Keep the signature block exactly. Reply in exactly this format:\nSubject: <subject>\n\n<body>"},
            {"role": "user", "content": f"{asks[data.instruction]}\n\nSubject: {data.subject}\n\n{data.body}"}], [], max_output=900)
        text = message["content"].strip()
        match = re.match(r"(?is)\s*subject:\s*(.+?)\n\s*\n(.+)", text)
        if not match:
            raise NovaError("rewrite_format", "The rewrite came back in an unexpected format. Try again.")
        return {"subject": match.group(1).strip()[:160], "body": match.group(2).strip()[:8000]}

    @app.get("/api/email/render")
    async def render_email(subject: str = "", body: str = ""):
        """Live compose preview using the real email template (sandboxed, no scripts)."""
        from .outreach import render_email_html

        return HTMLResponse(render_email_html(subject[:160] or "(no subject)", body[:8000] or " ", settings),
                            headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"})

    @app.get("/api/outbox/{message_id}/preview")
    async def preview_outbox(message_id: str):
        from .outreach import render_email_html

        message = app.state.runtime.outbox.get(message_id)
        return HTMLResponse(render_email_html(message["subject"], message["body"], settings),
                            headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"})

    @app.post("/api/outbox/{message_id}/send")
    async def send_outbox(message_id: str):
        return await app.state.runtime.outbox.send(message_id)

    @app.post("/api/outbox/{message_id}/discard")
    async def discard_outbox(message_id: str):
        return app.state.runtime.outbox.discard(message_id)

    @app.post("/api/drafts/{draft_id}/outbox")
    async def draft_to_outbox(draft_id: str, data: EmailRecipient):
        """Move a mission draft into the outbox so it can be sent from there or by voice."""
        runtime = app.state.runtime
        draft = runtime.business.draft(draft_id)
        return runtime.outbox.draft(data.recipient, draft["subject"], draft["body"], business=draft["business"],
                                    source=draft["facts"].get("source", ""), task_id=draft["task_id"])

    @app.get("/api/drafts")
    async def drafts(task_id: str | None = None):
        return {"drafts": app.state.runtime.business.list(task_id)}

    @app.post("/api/drafts")
    async def create_draft(data: DraftInput):
        runtime = app.state.runtime
        draft = runtime.business.create(data.task_id, data.kind)
        stage = f"draft_{data.kind}"
        guides = runtime.skills.resolve("email", "draft", data.kind)
        if guides and not any(item.get("stage") == stage for item in runtime.skills.observed(data.task_id)):
            runtime.skills.record(data.task_id, stage, guides)
            runtime.skills.finish(data.task_id, stage, "passed")
        return draft

    @app.put("/api/drafts/{draft_id}")
    async def edit_draft(draft_id: str, data: DraftEdit):
        return app.state.runtime.business.edit(draft_id, data)

    @app.post("/api/drafts/{draft_id}/review")
    async def review_draft(draft_id: str, data: Decision):
        return app.state.runtime.business.review(draft_id, data.digest, data.approved)

    @app.get("/api/drafts/{draft_id}/channels")
    async def draft_channels(draft_id: str):
        runtime = app.state.runtime
        draft = runtime.business.draft(draft_id)
        channels = runtime.outreach.channels(draft["task_id"])
        return {**channels, "configured": runtime.outreach.configured()}

    @app.post("/api/drafts/{draft_id}/channels")
    async def refresh_channels(draft_id: str):
        runtime = app.state.runtime
        if runtime.store.stopped():
            raise NovaError("stopped", "Emergency stop is active.")
        draft = runtime.business.draft(draft_id)
        channels = runtime.outreach.channels(draft["task_id"])
        if channels["source"]:
            record = await runtime.research.audit(Candidate(name=draft["business"], url=channels["source"]))
            channels = {"source": record["url"], "emails": record.get("public_emails", []),
                        "contact_page": record.get("contact_page")}
        return {**channels, "configured": runtime.outreach.configured()}

    @app.post("/api/drafts/{draft_id}/email/preview")
    async def email_preview(draft_id: str, data: EmailRecipient):
        return app.state.runtime.outreach.preview(draft_id, data.recipient)

    @app.post("/api/drafts/{draft_id}/email/deliver")
    async def deliver_email(draft_id: str, data: EmailDelivery):
        return await app.state.runtime.outreach.send(draft_id, data.recipient, data.digest)

    @app.get("/api/drafts/{draft_id}/export/{format_name}")
    async def draft_export(draft_id: str, format_name: str):
        if format_name not in {"txt", "html"}:
            raise NovaError("export_missing", "Choose a plain-text or HTML email export.")
        business = app.state.runtime.business
        draft = business.draft(draft_id)
        from .outreach import render_email_html

        content = (render_email_html(draft["subject"], draft["body"], settings) if format_name == "html"
                   else business.email_export(draft, format_name))
        return Response(content, media_type="text/html" if format_name == "html" else "text/plain",
                        headers={"Content-Disposition": f"attachment; filename=nova-email.{format_name}",
                                 "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})

    @app.get("/api/tasks/{task_id}/export/{format_name}")
    async def export_task(task_id: str, format_name: str, kind: str = "proposal"):
        if format_name not in exports.MEDIA or kind not in exports.DOC_SECTIONS:
            raise NovaError("export_missing", "That document format or report type is unavailable.")
        proposal = app.state.runtime.business.proposal_for(task_id)
        if format_name == "docx":
            content = await asyncio.to_thread(exports.document, proposal, kind)
        else:
            content = await asyncio.to_thread(exports.workbook if format_name == "xlsx" else exports.deck, proposal)
        return Response(content, media_type=exports.MEDIA[format_name],
                        headers={"Content-Disposition": f"attachment; filename=nova-{kind}.{format_name}"})

    @app.post("/api/leads/{task_id}/stage")
    async def lead_stage(task_id: str, data: LeadChange):
        return app.state.runtime.business.change_lead(task_id, data)

    @app.get("/api/finance")
    async def finance():
        return app.state.runtime.business.ledger()

    @app.post("/api/finance")
    async def record_finance(data: EntryInput):
        return app.state.runtime.business.add_entry(data)

    @app.post("/api/tasks/{task_id}/feedback")
    async def feedback(task_id: str, data: FeedbackInput):
        return app.state.runtime.business.feedback(task_id, data)

    @app.get("/api/learning")
    async def learning():
        db = app.state.runtime.store.db
        return {"feedback": [dict(row) for row in db.execute(
            "SELECT f.*,t.title FROM outcome_feedback f JOIN tasks t ON t.id=f.task_id ORDER BY f.updated DESC LIMIT 50"
        )], "outcomes": [dict(row) for row in db.execute(
            "SELECT json_extract(spec,'$.workflow') workflow,state,COUNT(*) AS count FROM tasks GROUP BY workflow,state"
        )]}

    @app.get("/api/notifications/{event_id}/telegram")
    async def telegram_preview(event_id: int):
        return app.state.telegram.preview(event_id)

    @app.post("/api/notifications/{event_id}/telegram")
    async def telegram_delivery(event_id: int, data: Decision):
        if not data.approved:
            raise NovaError("approval_required", "Owner approval is required for this Telegram message.")
        return await app.state.telegram.deliver(event_id, data.digest)

    @app.post("/api/tasks/{task_id}/control")
    async def control(task_id: str, command: Control):
        return app.state.runtime.control(task_id, command.action)

    @app.post("/api/tasks/{task_id}/retry")
    async def retry(task_id: str):
        """Queue a fresh copy of a failed or cancelled mission with the same inputs."""
        store = app.state.runtime.store
        row = store.db.execute("SELECT spec, state FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise NovaError("task_missing", "That mission does not exist.")
        if row["state"] not in {"failed", "cancelled"}:
            raise NovaError("task_state", "Only failed or cancelled missions can be retried.")
        spec = {key: value for key, value in json.loads(row["spec"]).items() if key not in {"run_at", "depends_on"}}
        task, created = store.submit(MissionInput.model_validate(spec))
        store.event("task", "Owner retried a mission", task["id"], retried_from=task_id)
        return {"task": task, "created": created}

    @app.post("/api/stop/{action}")
    async def stop(action: str):
        if action not in {"enable", "reset"}:
            return JSONResponse({"message": "Unknown emergency stop action."}, 404)
        app.state.runtime.stop(action == "enable")
        return {"stopped": action == "enable"}

    @app.post("/api/approvals/{task_id}")
    async def approval(task_id: str, decision: Decision):
        store = app.state.runtime.store
        with store.db:
            cursor = store.db.execute(
                "UPDATE approvals SET state=? WHERE task_id=? AND digest=? AND state='pending'",
                ("approved" if decision.approved else "rejected", task_id, decision.digest),
            )
            if cursor.rowcount != 1:
                raise NovaError("review_changed", "The approval is no longer pending for these action parameters.")
            store.event("approval", "Owner recorded proposal review", task_id, approved=decision.approved)
            if decision.approved:
                store.db.execute("UPDATE leads SET stage='proposal_reviewed' WHERE task_id=? AND stage='awaiting_approval'", (task_id,))
        return {"approved": decision.approved}

    @app.get("/api/memory")
    async def memory(q: str = ""):
        return app.state.runtime.store.memory(q[:300])

    @app.post("/api/memory/semantic")
    async def semantic_memory(data: SemanticSearch):
        runtime = app.state.runtime
        public_notes = [item for item in runtime.store.memory("") if
                        item["category"] == "business" and item["source"].startswith("mission:")][:6]
        if not public_notes:
            return {"results": [], "model_calls": 0}
        passages = [f"{item['headline']} {item['body']}"[:350] for item in public_notes]
        [query] = await runtime.gateway.embeddings([data.query], mode="query")
        vectors = await runtime.gateway.embeddings(passages, mode="passage")
        def score(vector):
            norms = math.hypot(*query) * math.hypot(*vector)
            return sum(a * b for a, b in zip(query, vector, strict=True)) / norms if norms and len(query) == len(vector) else 0
        results = sorted(({**item, "relevance": round(score(vector), 5)}
                          for item, vector in zip(public_notes, vectors, strict=True)),
                         key=lambda item: -item["relevance"])
        return {"results": results}

    @app.delete("/api/memory/{note_id}")
    async def forget(note_id: int):
        store = app.state.runtime.store
        with store.db:
            removed = store.db.execute("DELETE FROM notes WHERE id=?", (note_id,)).rowcount
            if removed:
                store.event("memory", "Owner deleted a memory note")
        return {"removed": bool(removed)}

    def project_file(task_id, file, revision=None):
        store = app.state.runtime.store
        row = store.get(task_id)
        folder = settings.workspace_path.resolve() / row["id"]
        if folder.is_symlink():
            raise NovaError("preview_missing", "Preview file is unavailable.")
        if revision is not None:
            if not demo.REVISION_PATTERN.fullmatch(revision) or (folder / "revisions").is_symlink():
                raise NovaError("preview_missing", "Preview revision is unavailable.")
            folder = folder / "revisions" / revision
        asset_path = folder / file
        if ((file not in demo.ARTIFACTS and not demo.SITE_ASSET.fullmatch(file)) or row["state"] != "completed" or folder.is_symlink()
                or asset_path.is_symlink() or not asset_path.is_file()):
            raise NovaError("preview_missing", "Preview file is unavailable.")
        return FileResponse(asset_path)

    def serve_project(request, task_id, file, revision=None):
        response = project_file(task_id, file, revision)
        if file != "index.html":
            return response
        host = request.headers.get("host", "")
        if not re.fullmatch(r"(?:127\.0\.0\.1|localhost|testserver)(?::[0-9]{1,5})?", host):
            raise NovaError("preview_origin", "The preview requires a local origin.")
        root = f"http://{host}/projects/{task_id}"
        if revision:
            root += f"/revisions/{revision}"
        html, policy = demo.sandbox_preview(Path(response.path).read_text(encoding="utf-8"), root)
        return HTMLResponse(html, headers={"Content-Security-Policy": policy})

    @app.get("/api/documents")
    async def documents():
        from .toolkit import list_documents

        return {"documents": list_documents(settings.workspace_path)}

    @app.get("/api/follow-ups")
    async def follow_ups():
        reminders = app.state.runtime.follow_ups
        return {"due": reminders.due(), "upcoming": reminders.upcoming(20)}

    @app.post("/api/follow-ups/{key}/done")
    async def follow_up_done(key: str):
        return app.state.runtime.follow_ups.complete(key)

    @app.get("/documents/{name}")
    async def document(name: str):
        from .toolkit import document_path

        path = document_path(settings.workspace_path, name)
        media = "text/markdown; charset=utf-8" if name.endswith(".md") else \
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(path, media_type=media, filename=name,
                            content_disposition_type="inline" if name.endswith(".md") else "attachment")

    @app.get("/projects/{task_id}/{file}")
    async def project(request: Request, task_id: str, file: str):
        return serve_project(request, task_id, file)

    @app.get("/projects/{task_id}/revisions/{revision}/{file}")
    async def project_revision(request: Request, task_id: str, revision: str, file: str):
        return serve_project(request, task_id, file, revision)

    @app.post("/api/tasks/{task_id}/revisions")
    async def refine_preview(task_id: str, data: Refinement):
        runtime = app.state.runtime
        runtime.business.proposal_for(task_id)
        lead = runtime.store.checkpoints(task_id)["rank"]["selected"]
        if data.priority_index >= len(lead["findings"]):
            raise NovaError("design_choice", "Choose one of the verified audit findings.")
        if runtime.store.stopped():
            raise NovaError("stopped", "Emergency stop is active.")
        workspace = settings.workspace_path
        candidate = runtime.prioritize(lead, data.priority_index)
        guides = runtime.skills.resolve("website", "build", lead["name"])
        async with review_browser:
            with tempfile.TemporaryDirectory(prefix=".nova-revision-", dir=workspace) as scratch:
                root = Path(scratch)
                revision = demo.create_demo(root, task_id, candidate, skill_ids=tuple(item.skill_id for item in guides))
                key = revision["revision"]
                folder = demo.project_dir(workspace, task_id, create=False)
                destination = demo.revision_dir(folder, key)
                if (destination / "verification.json").is_file():
                    return {"revision": key, "created": False}
                await demo.verify(root, task_id, candidate)
                if runtime.store.stopped():
                    raise NovaError("stopped", "Emergency stop interrupted preview refinement.")
                staged = demo.revision_dir(demo.project_dir(root, task_id, create=False), key)
                destination.parent.mkdir(mode=0o700, exist_ok=True)
                staged.replace(destination)
        runtime.store.log("design", "Verified an alternate website revision", task_id, revision=key,
                          evidence_index=data.priority_index)
        return {"revision": key, "created": True}

    @app.post("/api/tasks/{task_id}/visual-review")
    async def visual_review(task_id: str):
        runtime = app.state.runtime
        runtime.business.proposal_for(task_id)
        screenshot = project_file(task_id, "desktop.png").path

        def crop():
            from PIL import Image

            with Image.open(screenshot) as image:
                if image.width * image.height > 20_000_000:
                    raise NovaError("input_budget", "The preview is too large to review.")
                region = image.crop((0, 0, image.width, min(image.height, 1000))).convert("RGB")
                region.thumbnail((768, 768))
                output = io.BytesIO()
                region.save(output, format="PNG", optimize=True)
                return output.getvalue()

        image = await asyncio.to_thread(crop)
        digest = hashlib.sha256(image).hexdigest()
        key = f"vision:{task_id}:{runtime.gateway.configured(Capability.VISION)}:{digest}"
        if (existing := runtime.store.cached(key)) is not None:
            return {**existing, "cache_hit": True}
        result = await runtime.gateway.visual_review(image, "Review a private website concept based on observed public HTML.",
                                                    task_id=task_id)
        runtime.store.cache(key, result, 7 * 24 * 3600)
        runtime.store.log("design", "NVIDIA recorded a visual critique", task_id, model=result["model"])
        return {**result, "cache_hit": False}

    @app.get("/api/events")
    async def event_feed(request: Request, after: int = 0):
        runtime = app.state.runtime
        last_header = request.headers.get("last-event-id")
        offset = min(2 ** 63 - 1, max(0, after))
        if last_header and last_header.isdecimal() and len(last_header) < 18:
            offset = max(offset, int(last_header))

        async def stream():
            nonlocal offset
            while not app.state.draining:
                runtime.activity.clear()
                events = runtime.store.events(offset)
                if events:
                    for event in events:
                        offset = event["id"]
                        yield f"id: {offset}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    continue
                try:
                    await asyncio.wait_for(runtime.activity.wait(), 15)
                except TimeoutError:
                    yield ": keepalive\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no"})

    @app.websocket("/voice")
    async def voice(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        host = websocket.headers.get("host", "")
        if origin != f"http://{host}" or live_voice.locked():
            await websocket.close(code=1008)
            return
        async with live_voice:
            await Session(websocket, app.state.runtime).handle()

    return app
