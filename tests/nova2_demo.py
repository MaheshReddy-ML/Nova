"""Run the private NOVA 2 demonstration through a Chromium microphone fixture."""

import argparse
import asyncio
import io
import json
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.async_api import async_playwright, expect

from nova.config import Settings
from nova.gateway import Gateway
from nova.store import Store

COMMANDS = ("Start the assisted website review.", "What are you doing?")


async def make_fixture(path):
    with TemporaryDirectory(prefix="nova-demo-voice-") as scratch:
        store = Store(Path(scratch) / "probe.db")
        provider = Gateway(Settings(), store)
        try:
            audio = [await provider.synthesize(text) for text in COMMANDS]
        finally:
            await provider.close()
            store.db.close()
    chunks = []
    params = None
    for content in audio:
        with wave.open(io.BytesIO(content), "rb") as reader:
            if params is None:
                params = reader.getparams()
            else:
                assert reader.getframerate() == params.framerate and reader.getsampwidth() == params.sampwidth
            chunks.append(reader.readframes(reader.getnframes()))
    second = bytes(params.framerate * params.sampwidth * params.nchannels)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setparams(params)
        output.writeframes(second + chunks[0] + second * 3 + chunks[1] + second * 4)


async def exercise(url, fixture, output):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=[
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            f"--use-file-for-fake-audio-capture={fixture.resolve()}%noloop",
            "--autoplay-policy=no-user-gesture-required",
        ])
        page = await browser.new_page(viewport={"width": 1480, "height": 1000}, permissions=["microphone"])
        received, sent, texts = [], [], []
        page.on("websocket", lambda socket: watch(socket, received, sent, texts))
        await page.goto(url)
        await expect(page.get_by_role("button", name="Send", exact=True)).to_be_enabled()
        state = await page.request.get(url + "/api/state")
        initial = {item["id"] for item in (await state.json())["tasks"]}
        voice = page.locator("#voice-dock")
        if await voice.locator("#voice-detail").is_hidden():
            await voice.locator("#voice-expand").click()
        settings = voice.locator("details")
        if await settings.count() and not await settings.first.evaluate("(element) => element.open"):
            await settings.first.locator("summary").click()
        await page.locator("#headphones").check()
        await page.locator("#notifications").check()
        await page.get_by_role("button", name="Enable microphone").click()
        try:
            async with asyncio.timeout(45):
                task = None
                while task is None or task["state"] not in {"completed", "failed", "cancelled"}:
                    response = await page.request.get(url + "/api/state")
                    tasks = (await response.json())["tasks"]
                    task = next((item for item in tasks if item["id"] not in initial and item["spec"].get("design_assist")), None)
                    if task is None or task["state"] not in {"completed", "failed", "cancelled"}:
                        await asyncio.sleep(.35)
        except TimeoutError as error:
            raise RuntimeError(f"Voice mission was not observed. Fixed-fixture transcripts were {texts!r}.") from error
        assert task["state"] == "completed", task
        await asyncio.sleep(2)
        await page.get_by_role("button", name="Disable microphone").click()
        response = await page.request.get(url + "/api/tasks/" + task["id"])
        mission = await response.json()
        response = await page.request.get(url + "/api/drafts", params={"task_id": task["id"]})
        drafts = (await response.json())["drafts"]
        output.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=output / "nova2-demo-console.png", full_page=True)
        await browser.close()

    assert drafts and drafts[0]["status"] == "pending"
    assert "partial" in received and "pcm" in received and "audio_start" in sent
    metrics = {
        "task_id": task["id"], "voice_transcripts": texts, "voice_partials": received.count("partial"),
        "speech_packets": received.count("pcm"), "proactive_announcements": sent.count("announce"),
        "workflow_steps": mission["tool_calls"], "execution_seconds": mission["execution_seconds"],
        "audit_cache_hits": mission["audit_cache_hits"], "usage": mission["usage"],
        "skills": sorted({entry["skill_id"] for entry in mission["skill_activations"]}),
        "verification_profiles": sorted(mission["checkpoints"]["verify"]),
        "design_assistance": mission["checkpoints"]["build"]["model_direction"],
        "draft_id": drafts[0]["id"], "draft_status": drafts[0]["status"],
    }
    (output / "nova2-demo.json").write_text(json.dumps(metrics, indent=2) + "\n")
    return metrics


def watch(socket, received, sent, texts):
    def on_frame(frame, target):
        if not isinstance(frame, str):
            return
        try:
            packet = json.loads(frame)
            target.append(packet["type"])
            if packet["type"] == "transcript":
                texts.append(packet["text"])
        except (TypeError, KeyError, ValueError):
            return

    socket.on("framereceived", lambda frame: on_frame(frame, received))
    socket.on("framesent", lambda frame: on_frame(frame, sent))


async def run(args):
    if args.make_fixture:
        await make_fixture(args.fixture)
    if not args.fixture_only:
        print(json.dumps(await exercise(args.url, args.fixture, args.output), indent=2))


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--url", default="http://127.0.0.1:8000")
    cli.add_argument("--fixture", type=Path, default=Path("output/playwright/nova2-microphone.wav"))
    cli.add_argument("--output", type=Path, default=Path("output/playwright"))
    cli.add_argument("--make-fixture", action="store_true")
    cli.add_argument("--fixture-only", action="store_true")
    asyncio.run(run(cli.parse_args()))
