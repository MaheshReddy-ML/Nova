"""Exercise the local console with Chromium. Use a fixed WAV to opt into a live NVIDIA voice check."""

import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright, expect


async def verify(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    flags = []
    if args.voice_fixture:
        flags = [
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            f"--use-file-for-fake-audio-capture={args.voice_fixture.resolve()}%noloop",
            "--autoplay-policy=no-user-gesture-required",
        ]
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=flags)
        page = await browser.new_page(viewport={"width": 1440, "height": 1050}, permissions=["microphone"])
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        await page.goto(args.url)
        await expect(page.get_by_text("Live connection", exact=True)).to_be_visible()
        await expect(page.get_by_role("heading", name="Mission control")).to_be_visible()
        await page.screenshot(path=output / "console-desktop.png", full_page=True)
        await page.get_by_role("button", name="New mission").click()
        await expect(page.get_by_role("dialog")).to_be_visible()
        await page.get_by_role("button", name="Use Hyderabad studio list").click()
        assert "claysutra.com" in await page.get_by_label("Public websites").input_value()
        await page.get_by_role("button", name="Close", exact=True).click()
        await page.get_by_role("textbox", name="Message NOVA").fill("What are you doing?")
        await page.get_by_role("button", name="Send", exact=True).click()
        await expect(page.locator("#response")).to_contain_text(re.compile("Mission status|There are no missions"))
        await page.get_by_role("link", name="Projects", exact=True).click()
        await expect(page.get_by_role("heading", name="Projects")).to_be_visible()
        preview = page.get_by_role("link", name="Preview").first
        if await preview.count():
            async with page.expect_popup() as popup:
                await preview.click()
            demo = await popup.value
            await expect(demo.get_by_text("Unofficial demonstration", exact=False)).to_be_visible()
            if await demo.get_by_role("button", name="Test enquiry").count():
                await demo.get_by_label("Sample name").fill("Alex")
                await demo.get_by_label("Enquiry topic").select_option(label="Availability")
                await demo.get_by_role("button", name="Test enquiry").click()
                await expect(demo.get_by_role("status")).to_contain_text("Demo complete")
            await demo.close()
        await page.get_by_role("link", name="Overview", exact=True).click()
        await page.set_viewport_size({"width": 390, "height": 844})
        assert await page.evaluate("document.documentElement.scrollWidth === innerWidth")
        await page.screenshot(path=output / "console-mobile.png", full_page=True)

        result = {"dashboard_desktop": True, "dashboard_mobile": True, "fixture_voice": False}
        if args.voice_fixture:
            audio_packets = []
            page.on("websocket", lambda ws: ws.on("framereceived", lambda frame: capture(frame, audio_packets)))
            await page.reload()
            await expect(page.get_by_role("button", name="Send", exact=True)).to_be_enabled()
            await expect(page.get_by_text("Live connection", exact=True)).to_be_visible()
            await page.get_by_role("button", name="Enable microphone").click()
            await expect(page.get_by_role("button", name="Disable microphone")).to_be_visible()
            await expect(page.locator("#response")).to_contain_text("You said: What are you doing?", timeout=13000)
            await expect(page.locator("#response")).to_contain_text("Mission status", timeout=5000)
            await expect(page.locator("#voice-metrics")).to_contain_text("First audio", timeout=12000)
            result["voice_timing"] = await page.locator("#voice-metrics").inner_text()
            result["voice_packets"] = {kind: audio_packets.count(kind) for kind in ("partial", "transcript", "pcm")}
            assert result["voice_packets"]["partial"] > 0 and result["voice_packets"]["pcm"] > 0
            await page.get_by_role("button", name="Stop audio").click()
            await expect(page.locator("#voice-state")).to_have_text("Listening")
            await page.get_by_role("button", name="Disable microphone").click()
            await expect(page.get_by_role("button", name="Enable microphone")).to_be_visible()
            result["fixture_voice"] = True
        await browser.close()
        assert not errors, errors
        return result


def capture(frame, packets):
    try:
        packets.append(json.loads(frame)["type"])
    except (ValueError, KeyError):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("output/playwright"))
    parser.add_argument("--voice-fixture", type=Path)
    options = parser.parse_args()
    print(json.dumps(asyncio.run(verify(options)), indent=2))
