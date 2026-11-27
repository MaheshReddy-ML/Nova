import argparse
import asyncio
import io
import json
import logging
import tempfile
import time
import wave
from pathlib import Path

import httpx
import uvicorn

from .app import create_app
from .config import Settings
from .conversation import local_intent
from .domain import Brief, NovaError
from .gateway import Capability, Gateway
from .runtime import POTTERY_CANDIDATES, Runtime
from .store import Store


class LocalServer(uvicorn.Server):
    async def shutdown(self, sockets=None):
        app = self.config.app
        app.state.draining = True
        runtime = getattr(app.state, "runtime", None)
        if runtime is not None:
            runtime.activity.set()
        await super().shutdown(sockets)


async def check(settings, speech, fixture=None):
    with tempfile.TemporaryDirectory(prefix="nova-probe-") as scratch:
        store = Store(Path(scratch) / "probe.db")
        gateway = Gateway(settings, store)
        info = {"routes": {}}
        try:
            models = await gateway.catalogue(refresh=True)
            info["catalogue_count"] = len(models)
            for item in (Capability.FAST, Capability.PLANNING, Capability.REASONING, Capability.CODING,
                         Capability.VISION, Capability.EMBEDDING):
                try:
                    info["routes"][item] = await gateway.route(item)
                except NovaError as exc:
                    info["routes"][item] = exc.code
            result = await gateway.chat(Capability.PLANNING, [
                {"role": "system", "content": "Return the requested brief as JSON without markdown."},
                {"role": "user", "content": "Prepare a tiny brief for checking whether NOVA is online."},
            ], max_output=300, schema=Brief)
            info["structured_chat"] = bool(result.next_steps)
        except NovaError as exc:
            info["chat_error"] = {"code": exc.code, "message": str(exc)}
        if speech:
            try:
                phrase = "What are you doing?" if fixture else "NOVA is ready for the website review."
                sample = await gateway.synthesize(phrase)
                info["speech_audio_bytes"] = len(sample)
                info["transcript"] = await gateway.transcribe(sample)
                if fixture:
                    with wave.open(io.BytesIO(sample), "rb") as spoken:
                        params = spoken.getparams()
                        frames = spoken.readframes(spoken.getnframes())
                    padding = bytes(params.framerate * params.sampwidth * params.nchannels)
                    fixture.parent.mkdir(parents=True, exist_ok=True)
                    with wave.open(str(fixture), "wb") as output:
                        output.setparams(params)
                        output.writeframes(padding + frames + padding * 3)
                    info["fixture"] = str(fixture)
            except NovaError as exc:
                info["speech_error"] = {"code": exc.code, "message": str(exc)}
        info["usage"] = store.usage()
        await gateway.close()
        store.db.close()
        print(json.dumps(info, indent=2))
        return int(bool(info.get("chat_error") or info.get("speech_error")))


def first_mission(settings):
    url = f"http://{settings.host}:{settings.port}/api/tasks"
    response = httpx.post(url, headers={"x-nova-owner": "1"}, json={
        "title": "Hyderabad pottery studio website review",
        "candidates": POTTERY_CANDIDATES,
    }, timeout=10, trust_env=False)
    print(json.dumps(response.json(), indent=2))
    return int(response.is_error)


def benchmark(settings):
    """Compare request sizes and local status latency on a fixed synthetic fixture."""
    question = {"role":"user", "content":"What are you doing?"}
    system = {"role":"system", "content":"Answer the current task status."}
    fixture = [{"role":"user" if i % 2 else "assistant", "content":
                f"Earlier message {i} about an unrelated project scope, budget, and delivery date."}
               for i in range(80)]
    with tempfile.TemporaryDirectory(prefix="nova-bench-") as scratch:
        store = Store(Path(scratch) / "bench.db")
        runtime = Runtime(settings, store, None, None)
        durations = []
        for _ in range(200):
            start = time.perf_counter_ns()
            assert local_intent(runtime, question["content"]) == "There are no missions yet."
            durations.append((time.perf_counter_ns() - start) / 1e6)
        durations.sort()
        store.db.close()
    print(json.dumps({
        "fixture": "Synthetic 80-message conversation, 200 local status queries",
        "full_context_estimated_token_upper_bound": Gateway.token_estimate([system, *fixture, question]),
        "selective_context_estimated_token_upper_bound": Gateway.token_estimate([system, question]),
        "deterministic_status_model_calls": 0,
        "deterministic_status_p50_ms": round(durations[99], 4),
        "deterministic_status_p95_ms": round(durations[189], 4),
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="nova")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Start the local owner service")
    probe = commands.add_parser("check-nvidia", help="Run one bounded live structured completion")
    probe.add_argument("--speech", action="store_true", help="Also synthesize and transcribe one short phrase")
    probe.add_argument("--voice-fixture", type=Path, help="Save a synthesized status question for Chromium acceptance")
    commands.add_parser("first-mission", help="Queue the sourced Hyderabad website mission")
    commands.add_parser("benchmark", help="Measure local status latency and compare fixed context sizes")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "check-nvidia":
        raise SystemExit(asyncio.run(check(settings, args.speech or args.voice_fixture is not None, args.voice_fixture)))
    if args.command == "first-mission":
        raise SystemExit(first_mission(settings))
    if args.command == "benchmark":
        benchmark(settings)
        return
    logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    LocalServer(uvicorn.Config(
        create_app(settings), host=settings.host, port=settings.port,
        log_level=settings.log_level.lower(), access_log=False,
        ws="websockets-sansio", ws_max_size=8192, ws_max_queue=8, timeout_graceful_shutdown=6,
    )).run()


if __name__ == "__main__":
    main()
