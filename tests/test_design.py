from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from nova import demo
from nova.design import classify_category, design_brief
from nova.domain import NovaError


def fixture(category=None):
    return {
        "name": "Example Pottery Studio",
        "url": "https://example.com/",
        "next_url": "https://example.com/visit",
        "title": "Studio and workshops",
        "headings": ["Pottery classes"],
        "unlabeled_fields": 1,
        "findings": [{"change": "Keep labels visible", "observation": "A control lacked an associated label."}],
        **({"category": category} if category else {}),
    }


@pytest.mark.parametrize(("name", "industry"), [
    ("Example Tasting Menu & Restaurant", "restaurant"),
    ("Example Architecture Practice", "architecture"),
    ("Example Dental Clinic", "healthcare"),
    ("Example Boutique Hotel", "hospitality"),
    ("Example Analytics Platform", "software"),
    ("Example Clay Studio", "craft"),
    ("Example Local Business", "general"),
])
def test_category_is_evidence_based(name, industry):
    lead = {**fixture(), "name": name, "title": "", "headings": []}
    assert classify_category(lead) == industry


@pytest.mark.parametrize("bad_url", [
    "javascript:alert(1)", "//example.com", "https://owner@example.com",
    "http://127.0.0.1/", "http://127.1/", "http://[::1]/", "http://nova.localhost/",
    "https://example.com\\@other.test/",
])
def test_unsafe_or_local_source_link_is_rejected(bad_url):
    with pytest.raises(NovaError, match="valid public HTTP"):
        design_brief({**fixture(), "next_url": bad_url})


def test_untrusted_evidence_is_escaped(tmp_path: Path):
    task_id = "123abc456def"
    lead = {
        **fixture("software"),
        "name": "<script>alert(1)</script>",
        "findings": [{"observation": "<iframe src=/api/state>", "change": "<img onerror=alert(1)>"}],
    }
    demo.create_demo(tmp_path, task_id, lead)
    markup = (tmp_path / task_id / "index.html").read_text()
    parsed = BeautifulSoup(markup, "html.parser")
    assert parsed.h1.get_text(strip=True) == lead["name"]
    assert [tag.get("src") for tag in parsed.find_all("script")] == ["demo.js"]
    assert not parsed.select("iframe, img")
    assert "form-action 'none'" in markup
    assert "connect-src 'none'" in markup


def test_revision_history_preserves_the_previous_design(tmp_path: Path):
    task_id = "abc123def456"
    lead = fixture("restaurant")
    initial = demo.create_demo(tmp_path, task_id, lead)
    identical = demo.create_demo(tmp_path, task_id, lead)
    assert initial["revision"] == identical["revision"]
    initial_markup = (tmp_path / task_id / "index.html").read_text()
    latest = demo.create_demo(tmp_path, task_id, {**lead, "category": "architecture"})
    assert latest["revision"] != initial["revision"]
    previous, = demo.revision_history(tmp_path, task_id)
    assert previous["design"]["category"] == "restaurant"
    assert not previous["verified"]
    archive = demo.revision_dir(tmp_path / task_id, previous["revision"])
    assert (archive / "index.html").read_text() == initial_markup


def test_workspace_paths_are_checked_at_every_artifact_boundary(tmp_path: Path):
    with pytest.raises(NovaError, match="identifier"):
        demo.create_demo(tmp_path, "../outside", fixture())
    folder = demo.project_dir(tmp_path, "123abc123abc")
    (folder / "index.html").symlink_to(tmp_path / "outside.html")
    with pytest.raises(NovaError, match="symbolic link"):
        demo.create_demo(tmp_path, folder.name, fixture())
    assert not (tmp_path / "outside.html").exists()


async def test_chromium_passes_all_design_profiles(tmp_path: Path):
    task = "123abc456789"
    lead = {**fixture("restaurant"), "name": "Long Name Test Restaurant"}
    built = demo.create_demo(tmp_path, task, lead, skill_ids=("impeccable",))
    checks = await demo.verify(tmp_path, task, lead)
    draft = demo.proposal(tmp_path, task, lead, checks)
    assert set(checks) == {"desktop", "tablet", "mobile"}
    assert draft["revision"] == built["revision"]
    assert draft["proposed_price_inr"] == draft["effort_hours"] * 1200
    assert all(check["passed"] and check["enquiry_preview_verified"] and check["accessibility"]["keyboard_focus"]
               for check in checks.values())
    revision, = demo.revision_history(tmp_path, task)
    assert revision["verified"] and "proposal.json" in revision["artifacts"]
    assert (tmp_path / task / "tablet.png").stat().st_size > 0


async def test_preview_enquiry_and_canonical_link_in_an_opaque_iframe(tmp_path: Path):
    task = "123abc456789"
    lead = fixture()
    demo.create_demo(tmp_path, task, lead)
    sources = demo.browser_sources(tmp_path / task)
    origin = "http://nova-fixture.invalid"
    sandbox = demo.PREVIEW_SANDBOX
    requests = []

    async def serve(route):
        url = route.request.url
        requests.append(url)
        if url == f"{origin}/owner":
            await route.fulfill(status=200, content_type="text/html", body=(
                f'<iframe title="Concept" sandbox="{sandbox}" src="/project/index.html"></iframe>'
            ))
        elif url.startswith(f"{origin}/project/") and (name := url.rsplit("/", 1)[-1]) in sources:
            content = sources[name]
            headers = {}
            if name == "index.html":
                content, policy = demo.sandbox_preview(content.decode(), f"{origin}/project")
                headers["Content-Security-Policy"] = policy
            await route.fulfill(status=200, content_type=demo.CONTENT_TYPES[name], body=content, headers=headers)
        elif url == lead["url"]:
            assert not route.request.headers.get("referer")
            await route.fulfill(status=200, content_type="text/html", body="<title>Official fixture</title>")
        else:
            await route.abort()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(env=demo.browser_env())
        try:
            context = await browser.new_context(offline=True)
            await context.route("**/*", serve)
            page = await context.new_page()
            await page.goto(f"{origin}/owner")
            child = page.frame_locator("iframe")
            await child.get_by_label("Sample name").fill("Sample visitor")
            await child.get_by_label("Enquiry topic").select_option(label="Availability")
            await child.get_by_role("button", name="Test enquiry").click()
            await child.get_by_role("status").filter(has_text="Demo complete.").wait_for()
            assert await page.locator("iframe").evaluate("(frame) => frame.contentDocument === null")
            frame = page.frames[1]
            assert await frame.evaluate("async () => { try { await fetch('/api/state'); return false } catch { return true } }")
            assert f"{origin}/api/state" not in requests
            async with page.expect_popup() as popup:
                await child.get_by_role("link", name="Open official website").click()
            opened = await popup.value
            assert await opened.title() == "Official fixture"
            assert await opened.evaluate("window.opener === null")
        finally:
            await browser.close()
