import asyncio
import fcntl
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .conversation import Session
from .domain import Control, MissionInput, NovaError, StrictModel
from .gateway import FALLBACK, Gateway
from .research import PublicResearch
from .runtime import POTTERY_CANDIDATES, Runtime
from .store import Store

STATIC = Path(__file__).parent / "static"
ARTIFACTS = {"index.html", "style.css", "demo.js", "desktop.png", "mobile.png", "proposal.json"}
CONTENT_POLICY = ("default-src 'self'; style-src 'self'; script-src 'self'; media-src 'self' blob:; "
                  "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


class Decision(StrictModel):
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: bool


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
            research = research_factory(store)
            runtime = app.state.runtime = Runtime(settings, store, gateway, research)
            runtime.start()
            try:
                yield
            finally:
                await runtime.close()
                await gateway.close()
                await research.close()
                store.db.close()

    app = FastAPI(title="NOVA", version=settings.agent_version, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.draining = False
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    live_voice = asyncio.Semaphore(2)

    @app.middleware("http")
    async def local_owner(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            host = request.headers.get("host", "")
            origin = request.headers.get("origin")
            if request.headers.get("x-nova-owner") != "1" or (origin and origin != f"http://{host}"):
                return JSONResponse({"error": "origin", "message": "Owner mutations require a local NOVA request."}, 403)
        response = await call_next(request)
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
        status = 404 if exc.code == "task_missing" else 409
        return JSONResponse({"error": exc.code, "message": str(exc)}, status)

    @app.get("/")
    async def dashboard():
        return FileResponse(STATIC / "index.html")

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    @app.get("/static/{asset}")
    async def asset(asset: str):
        if asset not in {"dashboard.css", "dashboard.js", "mic.js"}:
            return JSONResponse({"message": "Asset not found."}, 404)
        return FileResponse(STATIC / asset)

    @app.get("/health")
    async def health():
        runtime = app.state.runtime
        return {"service": settings.agent_name, "version": settings.agent_version,
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
        voices = store.cached(f"nvidia:voices:{settings.tts_base_url}")
        last = store.db.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
        stats = {row["kind"]: row["count"] for row in store.db.execute(
            "SELECT kind, COUNT(*) AS count FROM events WHERE kind IN ('tool','cache','notification') GROUP BY kind"
        )}
        return {
            "agent": settings.agent_name, "version": settings.agent_version, "stopped": store.stopped(),
            "tasks": store.tasks(), "counts": counts, "leads": leads, "approvals": approvals, "usage": store.usage(),
            "catalogue_count": len(models) if models is not None else None,
            "routes": {item.value: next((model for model in (model_caps.configured(item), default)
                                        if models and model in models), None)
                       for item, default in FALLBACK.items()},
            "voice": {"enabled": settings.voice_enabled, "preferred": settings.tts_voice,
                      "asr_streaming": runtime.gateway.asr_streaming, "tts_streaming": runtime.gateway.tts_streaming,
                      "voices": voices or [],
                      "language": settings.tts_language},
            "spending_limit_inr": 0, "autonomous": settings.autonomous_mode,
            "recent_events": store.events(max(0, last - 24)), "stats": stats,
            "presets": {"hyderabad_studios": POTTERY_CANDIDATES},
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

    @app.post("/api/tasks")
    async def submit(spec: MissionInput):
        task, created = app.state.runtime.submit(spec)
        return JSONResponse({"task": task, "created": created}, 201 if created else 200)

    @app.get("/api/tasks/{task_id}")
    async def inspect(task_id: str):
        store = app.state.runtime.store
        task = store.view(store.get(task_id))
        events = list(store.db.execute("SELECT kind, data FROM events WHERE task_id=?", (task_id,)))
        checkpoints = store.checkpoints(task_id)
        return {
            "task": task, "checkpoints": checkpoints, "usage": store.usage(task_id),
            "audit_cache_hits": sum(item.get("cache_hit", False) for key, item in checkpoints.items() if key.startswith("audit_")),
            "tool_calls": sum(row["kind"] == "tool" for row in events),
            "execution_seconds": round(sum(json.loads(row["data"]).get("duration_seconds", 0)
                                           for row in events if row["kind"] == "attempt"), 3),
        }

    @app.post("/api/tasks/{task_id}/control")
    async def control(task_id: str, command: Control):
        return app.state.runtime.control(task_id, command.action)

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
        return {"approved": decision.approved}

    @app.get("/api/memory")
    async def memory(q: str = ""):
        return app.state.runtime.store.memory(q[:300])

    @app.delete("/api/memory/{note_id}")
    async def forget(note_id: int):
        store = app.state.runtime.store
        with store.db:
            removed = store.db.execute("DELETE FROM notes WHERE id=?", (note_id,)).rowcount
            if removed:
                store.event("memory", "Owner deleted a memory note")
        return {"removed": bool(removed)}

    @app.get("/projects/{task_id}/{file}")
    async def project(task_id: str, file: str):
        store = app.state.runtime.store
        row = store.get(task_id)
        folder = settings.workspace_path.resolve() / row["id"]
        asset_path = folder / file
        if (file not in ARTIFACTS or row["state"] != "completed" or folder.is_symlink()
                or asset_path.is_symlink() or not asset_path.is_file()):
            return JSONResponse({"message": "Preview file is unavailable."}, 404)
        return FileResponse(asset_path)

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
