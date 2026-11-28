"""Local control service so Nova (a separate Python environment) can place voice-review calls.

    .venv/bin/python control.py            # starts a Cloudflare quick tunnel, the call page and this API
    .venv/bin/python control.py --no-tunnel  # use PUBLIC_TUNNEL_URL from .env instead

API (bound to 127.0.0.1 only):
    GET  /health            {"ok": true, "public_url": ..., "ntfy": true}
    POST /calls             {"status_summary": ..., "questions": ..., "preview_url": ""}  -> {"id": ..., "status": "ringing"}
    GET  /calls/{id}        {"id", "status": "ringing" | "done" | "failed", "result"}

A call blocks a worker thread until the owner hangs up or a timeout passes; calls are queued one at a time by the bridge.
"""
import argparse
import logging
import os
import re
import subprocess
import threading
import time
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException, Request

from voice_bridge import _BRIDGE

log = logging.getLogger("voice_bridge.control")
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
CONTROL_PORT = int(os.getenv("VOICE_BRIDGE_CONTROL_PORT", "7861"))


def start_tunnel(port, timeout=45):
    """Run a Cloudflare quick tunnel to the call page and return its public HTTPS URL (it changes on every start)."""
    process = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout
    for line in process.stderr:
        if match := TUNNEL_URL.search(line):
            # Keep draining cloudflared's log so its pipe never fills and blocks the tunnel.
            threading.Thread(target=lambda: [None for _ in process.stderr], daemon=True).start()
            return match.group(0), process
        if time.monotonic() > deadline:
            break
    process.terminate()
    raise RuntimeError("cloudflared did not report a tunnel URL; check your network or use --no-tunnel")


def create_app():
    app = FastAPI(title="voice_bridge control")
    jobs = {}

    @app.get("/health")
    def health():
        return {"ok": True, "public_url": _BRIDGE.public_url, "ntfy": bool(_BRIDGE.topic),
                "busy": _BRIDGE.call_lock.locked()}

    @app.post("/calls")
    async def start(request: Request):
        data = await request.json()
        summary = str(data.get("status_summary", "")).strip()[:1200]
        questions = str(data.get("questions", "")).strip()[:1200]
        if not summary or not questions:
            raise HTTPException(422, "status_summary and questions are required")
        key = uuid.uuid4().hex[:8]
        jobs[key] = {"id": key, "status": "ringing", "result": None, "created": time.time()}

        def run():
            try:
                jobs[key]["result"] = _BRIDGE.call(summary, questions, str(data.get("preview_url", "")).strip()[:500])
                jobs[key]["status"] = "done"
            except Exception as exc:  # noqa: BLE001 - report the failure to Nova instead of dying silently
                log.exception("Voice call failed")
                jobs[key].update(status="failed", result=f"{type(exc).__name__}: {exc}")

        threading.Thread(target=run, name=f"call-{key}", daemon=True).start()
        return jobs[key]

    @app.get("/calls/{key}")
    def status(key: str):
        if key not in jobs:
            raise HTTPException(404, "unknown call")
        return jobs[key]

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--no-tunnel", action="store_true", help="use PUBLIC_TUNNEL_URL instead of starting cloudflared")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    tunnel = None
    if not args.no_tunnel:
        _BRIDGE.public_url, tunnel = start_tunnel(_BRIDGE.port)
    log.info("Loading speech models and the call page (first start downloads them)...")
    _BRIDGE.ensure_server()
    log.info("Ready. Call page: %s · ntfy topic set: %s · control API: http://127.0.0.1:%s",
             _BRIDGE.public_url, bool(_BRIDGE.topic), CONTROL_PORT)
    try:
        uvicorn.run(create_app(), host="127.0.0.1", port=CONTROL_PORT, log_level="warning")
    finally:
        if tunnel:
            tunnel.terminate()


if __name__ == "__main__":
    main()
