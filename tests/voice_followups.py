"""Live voice action acceptance with a prerecorded Claysutra command fixture."""

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect


async def run(args):
    fixture = args.fixture.resolve()
    events = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=[
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            f"--use-file-for-fake-audio-capture={fixture}%noloop", "--autoplay-policy=no-user-gesture-required",
        ])
        page = await browser.new_page(viewport={"width": 1440, "height": 960}, permissions=["microphone"])

        def packet(raw):
            if isinstance(raw, str):
                item = json.loads(raw)
                if item.get("type") in {"transcript", "action", "delta", "error", "voice_error"}:
                    events.append(item)

        page.on("websocket", lambda connection: connection.on("framereceived", packet))
        await page.goto(args.url + "/#overview")
        await expect(page.locator("#send")).to_be_enabled()
        await page.locator("#voice-expand").click()
        await page.locator(".voice-settings summary").click()
        await page.locator("#headphones").check()
        await page.get_by_role("button", name="Enable microphone").click()
        try:
            async with asyncio.timeout(38):
                while not any(item.get("draft_id") for item in events):
                    await asyncio.sleep(.2)
        except TimeoutError as exc:
            raise RuntimeError(json.dumps(events, ensure_ascii=False)) from exc
        review = next(item for item in events if item.get("draft_id"))
        task = await (await page.request.get(args.url + "/api/tasks/" + review["task_id"])).json()
        assert task["task"]["state"] == "completed"
        assert len(task["checkpoints"]["report"]["sources"]) == 1
        assert any("Claysutra" in item.get("text", "") for item in events if item.get("type") == "delta")
        await page.get_by_role("button", name="Disable microphone").click()
        await page.get_by_role("button", name="Review delivery").click()
        await page.get_by_label("Recipient", exact=True).fill("example@example.org")
        await page.get_by_role("button", name="Review recipient and message").click()
        await expect(page.locator("#email-preview")).to_contain_text("example@example.org")
        state = await (await page.request.get(args.url + "/api/state")).json()
        if not state["email_configured"]:
            await expect(page.get_by_text("A sender mailbox is required.", exact=True)).to_be_visible()
        await page.screenshot(path=fixture.parent / "review-delivery.png", animations="disabled")
        await browser.close()
        print(json.dumps({"task_id": review["task_id"], "draft_id": review["draft_id"],
                          "transcripts": [item["text"] for item in events if item.get("type") == "transcript"],
                          "completed_website_audits": 1, "email_preview_verified": True}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--fixture", type=Path, default=Path("output/playwright/nova-workbench/voice-mission.wav"))
    asyncio.run(run(parser.parse_args()))
