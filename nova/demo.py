"""Build and verify a local website concept using the first-party design library."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from .design import design_brief, markup, stylesheet
from .domain import NovaError

REVISION_PATTERN = re.compile(r"^[a-f0-9]{12}$")
SOURCE_FILES = ("index.html", "style.css", "demo.js")
SITE_ASSET = re.compile(r"^(?:img-\d{1,2}\.jpg|font-[a-z0-9-]+\.woff2|plan\.json)$")
ARTIFACTS = frozenset({
    *SOURCE_FILES, "design.json", "verification.json", "delivery.md", "proposal.json",
    "desktop.png", "tablet.png", "mobile.png",
})
AXE_PATH = Path(__file__).with_name("design_resources") / "axe.min.js"
AUDIT_URL = "http://nova-preview.invalid/index.html"
CONTENT_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "demo.js": "text/javascript; charset=utf-8",
}
PREVIEW_CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'none'; "
    "base-uri 'none'; form-action 'none'; worker-src 'none'"
)
PREVIEW_SANDBOX = "allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
PREVIEW_META = re.compile(r'<meta\b[^>]*\bhttp-equiv="Content-Security-Policy"[^>]*>\s*', re.I)


def sandbox_preview(html, directory_url):
    # Opaque documents cannot match 'self'. Permit only this project revision's two static resources.
    base = directory_url.rstrip("/")
    policy = (
        f"sandbox {PREVIEW_SANDBOX}; default-src 'none'; script-src {base}/demo.js; "
        f"style-src {base}/style.css; img-src data: {base}/; font-src {base}/; connect-src 'none'; object-src 'none'; "
        "worker-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
    )
    return PREVIEW_META.sub("", html), policy

BROWSER_PROFILES = (("desktop", 1440, 1050), ("tablet", 820, 1024), ("mobile", 390, 844))
DEMO_JS = """
const form = document.querySelector(".demo-form");
if (form) form.addEventListener("submit", (event) => {
  event.preventDefault();
  form.reset();
  form.querySelector('[role="status"]').textContent = "Demo complete. No enquiry was sent.";
});
"""
MEASUREMENT_SETUP = """
window.__novaPreview = {cls: 0, lcp: null};
new PerformanceObserver((entries) => {
  for (const event of entries.getEntries()) {
    if (!event.hadRecentInput) window.__novaPreview.cls += event.value;
  }
}).observe({type: 'layout-shift', buffered: true});
new PerformanceObserver((entries) => {
  for (const event of entries.getEntries()) window.__novaPreview.lcp = event.startTime;
}).observe({type: 'largest-contentful-paint', buffered: true});
"""
MEASURE_PAGE = """
() => {
  const body = document.body;
  const title = document.querySelector('h1');
  const hero = document.querySelector('.hero');
  const range = document.createRange();
  if (title) range.selectNodeContents(title);
  const headlineLines = new Set([...range.getClientRects()].map(rect => Math.round(rect.top))).size;
  const internalLinks = [...document.querySelectorAll('a[href^="#"]')];
  const externalLinks = [...document.querySelectorAll('a[href^="https://"],a[href^="http://"]')];
  const targets = [...document.querySelectorAll('header a, .action, .text-link, .task-index a, .demo-form button')];
  const matches = target => {
    const destination = target.getAttribute('href').slice(1);
    return destination && document.getElementById(destination);
  };
  const metrics = window.__novaPreview;
  return {
    width: document.documentElement.scrollWidth,
    viewport: innerWidth,
    lang: document.documentElement.lang,
    title: document.title,
    renderedCss: hero ? getComputedStyle(hero).display === 'grid' : false,
    structure: body.className || 'legacy',
    hero_width: hero?.clientWidth || 0,
    headline_lines: headlineLines,
    headline_width: title?.clientWidth || 0,
    headline_font_px: title ? parseFloat(getComputedStyle(title).fontSize) : 0,
    broken_internal_links: internalLinks.filter(target => !matches(target)).length,
    external_links: externalLinks.map(link => link.getAttribute('href')),
    touch_min_px: targets.length ? Math.round(Math.min(...targets.map(link => link.getBoundingClientRect().height))) : 0,
    all_image_alternatives: [...document.images].every(img => img.hasAttribute('alt')),
    reduced_motion: getComputedStyle(document.documentElement).scrollBehavior === 'auto',
    duration_ms: Math.round(performance.getEntriesByType('navigation')[0]?.duration || 0),
    fcp_ms: performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null,
    lcp_ms: metrics.lcp,
    cls: Math.round(metrics.cls * 1000) / 1000
  };
}
"""
AXE_RUN = """
async () => {
  const result = await window.axe.run(document, {
    runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']},
    resultTypes: ['violations', 'incomplete']
  });
  return {
    engine: result.testEngine.name + ' ' + result.testEngine.version,
    violations: result.violations.map(rule => ({
      id: rule.id, impact: rule.impact, summary: rule.description, failed_nodes: rule.nodes.length
    })),
    manual_review: result.incomplete.map(rule => rule.id),
  };
}
"""


def project_dir(root: Path, task_id: str, *, create=True):
    if not REVISION_PATTERN.fullmatch(task_id):
        raise NovaError("workspace", "This project identifier is invalid.")
    folder = root.resolve() / task_id
    if folder.is_symlink():
        raise NovaError("workspace", "The project path is a symbolic link.")
    if create:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def check_file(path: Path):
    if path.is_symlink():
        raise NovaError("workspace", "The project contains an unexpected symbolic link.")
    return path


def atomic_write(path: Path, data: str | bytes):
    check_file(path)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        staging = Path(handle.name)
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            staging.replace(path)
        finally:
            staging.unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_design(path):
    design_path = check_file(path / "design.json")
    if not design_path.is_file():
        return None
    data = json.loads(design_path.read_text())
    if not isinstance(data, dict) or not REVISION_PATTERN.fullmatch(data.get("revision", "")):
        raise NovaError("workspace", "The project design manifest is invalid.")
    return data


def revision_dir(path: Path, revision: str, *, create=False):
    if not REVISION_PATTERN.fullmatch(revision):
        raise NovaError("workspace", "This project revision is invalid.")
    parent = check_file(path / "revisions")
    folder = check_file(parent / revision)
    if create:
        folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    return folder


def archive_revision(path: Path, design: dict):
    folder = revision_dir(path, design["revision"], create=True)
    for name in ARTIFACTS:
        artifact = check_file(path / name)
        if artifact.is_file():
            atomic_write(folder / name, artifact.read_bytes())
    return folder


def revision_history(root, task_id):
    path = project_dir(root, task_id, create=False)
    parent = check_file(path / "revisions")
    if not parent.is_dir():
        return []
    revisions = []
    for item in parent.iterdir():
        if not REVISION_PATTERN.fullmatch(item.name) or item.is_symlink() or not item.is_dir():
            continue
        design = load_design(item)
        if design is None:
            continue
        artifacts = sorted(name for name in ARTIFACTS if not (item / name).is_symlink() and (item / name).is_file())
        revisions.append({
            "revision": item.name, "design": design,
            "artifacts": artifacts, "verified": "verification.json" in artifacts,
            "updated": item.stat().st_mtime,
        })
    return sorted(revisions, key=lambda item: item["updated"], reverse=True)


def source_revision(files: dict, brief: dict) -> str:
    content = json.dumps({"files": files, "brief": brief}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def write_delivery(path, brief):
    content = f"""# Local website concept

## Project direction

{brief['direction']}. {brief['composition']}

Official source [{brief['source']}]({brief['source']}).

## Hand-off

The build comprises index.html, style.css and demo.js. Review the static files with a local HTTP server. The enquiry example handles sample inputs locally and sends no messages. Keep the preview private while scope, content rights and business contact details are under review.

The verification report records desktop, tablet and mobile Chromium checks. Automated checks cover a subset of accessibility requirements. The original NOVA CSS artwork uses system fonts and no third-party brand assets.

See verification.json for observed checks and proposal.json for the planning estimate.
"""
    atomic_write(path / "delivery.md", content)


def create_demo(root, task_id, lead, *, skill_ids=()):
    path = project_dir(root, task_id)
    brief = design_brief(lead, tuple(skill_ids))
    files = {"index.html": markup(lead, brief), "style.css": stylesheet(brief), "demo.js": DEMO_JS}
    revision = source_revision(files, brief)
    previous = load_design(path)
    if previous and previous["revision"] != revision:
        archive_revision(path, previous)
        stale = ARTIFACTS - set(SOURCE_FILES) - {"design.json", "delivery.md"}
        for item in stale:
            check_file(path / item).unlink(missing_ok=True)
    for name, content in files.items():
        atomic_write(path / name, content)
    brief = {**brief, "revision": revision}
    write_json(path / "design.json", brief)
    write_delivery(path, brief)
    return {
        "preview": f"/projects/{task_id}/index.html", "revision": revision, "design": brief,
        "bytes": sum(len(content.encode()) for content in files.values()),
        "files": [*SOURCE_FILES, "design.json", "delivery.md"],
    }


def browser_env():
    allowed = ("PATH", "HOME", "TMPDIR", "LANG")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def browser_sources(path):
    sources = {}
    for name in SOURCE_FILES:
        artifact = check_file(path / name)
        if not artifact.is_file() and name == "demo.js":
            continue
        if not artifact.is_file() or artifact.stat().st_size > 64 * 1024:
            raise NovaError("verify_failed", "A required preview file is absent or exceeds the asset limit.")
        sources[name] = artifact.read_bytes()
    return sources


def color_contrast(ink, paper):
    def luminance(color):
        channels = (int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))
        rgb = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
        return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722

    lighter, darker = sorted((luminance(ink), luminance(paper)), reverse=True)
    return round((lighter + .05) / (darker + .05), 2)


async def audit_profile(browser, profile, width, height, path, task_id, lead, sources, brief):
    context = await browser.new_context(
        viewport={"width": width, "height": height}, offline=True,
        reduced_motion="reduce", service_workers="block",
    )
    errors = []
    blocked = []
    permitted = {urlsplit(AUDIT_URL)._replace(path=f"/{name}").geturl(): name for name in sources}

    async def serve(route):
        name = permitted.get(route.request.url)
        if name is None or route.request.method != "GET":
            blocked.append(route.request.url)
            await route.abort()
        else:
            await route.fulfill(status=200, body=sources[name], content_type=CONTENT_TYPES[name], headers={
                "Content-Security-Policy": PREVIEW_CSP, "X-Content-Type-Options": "nosniff",
            })

    try:
        await context.route("**/*", serve)
        await context.add_init_script(MEASUREMENT_SETUP)
        page = await context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda line: errors.append(line.text) if line.type == "error" else None)
        await page.goto(AUDIT_URL, wait_until="load", timeout=10000)
        await page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        result = await page.evaluate(MEASURE_PAGE)
        # Inject only the pinned first-party audit dependency. The generated preview never loads this script.
        axe = AXE_PATH.read_text(encoding="utf-8")
        await page.evaluate(axe)
        accessibility = await page.evaluate(AXE_RUN)
        keyboard_focus = False
        if brief:
            await page.keyboard.press("Tab")
            keyboard_focus = await page.evaluate("document.activeElement?.classList.contains('skip')") is True
            if keyboard_focus:
                await page.keyboard.press("Enter")
                keyboard_focus = await page.evaluate("document.activeElement?.id === 'top'") is True
        await page.get_by_role("link", name="Concept", exact=True).click(timeout=4000)
        navigation = page.url.endswith("#concept")
        heading = await page.get_by_role("heading", level=1).all_text_contents()
        official = await page.get_by_role("link", name="Open official website").get_attribute("href")
        form_checked = False
        if lead.get("unlabeled_fields"):
            await page.get_by_role("button", name="Test enquiry").click()
            invalid = await page.locator(".demo-form").evaluate("(form) => !form.checkValidity()")
            await page.get_by_label("Sample name").fill("Sample visitor")
            await page.get_by_label("Enquiry topic").select_option(label="Availability")
            await page.get_by_role("button", name="Test enquiry").click()
            await page.get_by_role("status").filter(has_text="Demo complete.").wait_for(timeout=3000)
            form_checked = bool(invalid and not await page.get_by_label("Sample name").input_value())
        await page.evaluate("scrollTo(0,0)")
        picture = await page.screenshot(full_page=True, timeout=8000, animations="disabled")
        atomic_write(path / f"{profile}.png", picture)
        palette = brief["palette"] if brief else None
        contrast = color_contrast(palette["ink"], palette["paper"]) if palette else None
        issues = []
        if errors or not navigation or result["broken_internal_links"] or not result["renderedCss"]:
            issues.append("Functional controls or preview resources did not pass.")
        if result["width"] > result["viewport"] or (brief and result["touch_min_px"] < 44):
            issues.append("Viewport bounds or touch targets did not pass.")
        if accessibility["violations"] or (brief and not keyboard_focus) or not result["reduced_motion"]:
            issues.append("Automated accessibility or keyboard checks need review.")
        if result["cls"] > .1 or sum(map(len, sources.values())) > 64 * 1024 or blocked:
            issues.append("Layout stability, asset budget or network isolation did not pass.")
        expected = {lead["url"], lead.get("next_url") or lead["url"]}
        if (not result["lang"] or not result["title"] or not result["all_image_alternatives"]
                or heading != [lead["name"]] or official != lead["url"] or set(result["external_links"]) != expected
                or (lead.get("unlabeled_fields") and not form_checked)):
            issues.append("Content evidence and labelled enquiry behavior did not pass.")
        if not result["headline_lines"] or result["headline_width"] > result["hero_width"] or (contrast is not None and contrast < 4.5):
            issues.append("Heading composition or color contrast needs review.")
        return {
            "width": width, "height": height, "navigation": navigation,
            "console_errors": len(errors), "document_load_ms": result["duration_ms"],
            "content_matches_source_reference": heading == [lead["name"]] and official == lead["url"],
            "accessibility_basics": ["Document language", "Named H1", "Image alternatives", "Named navigation"],
            "accessibility": {**accessibility, "keyboard_focus": keyboard_focus,
                              "reduced_motion": result["reduced_motion"], "min_touch_target_px": result["touch_min_px"]},
            "performance": {
                "fcp_ms": result["fcp_ms"], "lcp_ms": result["lcp_ms"], "cls": result["cls"],
                "code_bytes": sum(map(len, sources.values())), "network_requests_blocked": len(blocked),
                "measurement": "Local Chromium laboratory observation",
            },
            "visual": {key: result[key] for key in ("hero_width", "headline_lines", "headline_font_px", "structure")}
                      | {"contrast": contrast},
            "enquiry_preview_verified": form_checked,
            "screenshot": f"/projects/{task_id}/{profile}.png", "issues": issues, "passed": not issues,
        }
    finally:
        await context.close()


async def verify(root, task_id, lead, *, strict=True):
    path = project_dir(root, task_id)
    sources = browser_sources(path)
    brief = load_design(path)
    checks = {}
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(env=browser_env(), args=["--disable-background-networking"])
            try:
                for profile, width, height in BROWSER_PROFILES:
                    checks[profile] = await audit_profile(browser, profile, width, height, path, task_id, lead, sources, brief)
            finally:
                await browser.close()
    except PlaywrightError as exc:
        raise NovaError("browser", "Chromium verification failed. Check the preview files or install Chromium with uv run playwright install chromium.") from exc
    write_json(path / "verification.json", {
        "revision": brief["revision"] if brief else None, "profiles": checks,
        "assessment": "Automated browser gates and layout indicators. Accessibility and aesthetic review remain owner judgments.",
    })
    if strict and any(not result["passed"] for result in checks.values()):
        failures = [profile for profile, result in checks.items() if not result["passed"]]
        raise NovaError("verify_failed", f"The concept has verification issues on {', '.join(failures)}.")
    if brief:
        archive_revision(path, brief)
    return checks


def proposal(root, task_id, lead, checks):
    changes = lead["findings"][:3]
    hours = min(16, 6 + len(changes) * 2)
    demonstrated = ["Responsive layout", "Working navigation", "Direct link to official information"]
    if checks and all(item.get("enquiry_preview_verified") for item in checks.values()):
        demonstrated.append("Enquiry preview with persistent labels and local validation")
    path = project_dir(root, task_id)
    brief = load_design(path)
    draft = {
        "business": lead["name"], "source": lead["url"],
        "observations": [item["observation"] for item in changes],
        "scope": [item["change"] for item in changes],
        "demonstrated": demonstrated, "verification": sorted(checks),
        "effort_hours": hours, "proposed_price_inr": hours * 1200,
        "rate_basis": "Internal planning assumption of ₹1,200/hour.",
        "limitations": [
            "Based on one publicly accessible page and a locally tested concept.",
            "Validate requirements, content, rights, booking needs and pricing with the business before delivery.",
        ],
    }
    if brief:
        draft.update(design_direction=brief["direction"], revision=brief["revision"])
        stock = (brief.get("photo_sources") or {}).get("stock", 0)
        if stock:
            draft["limitations"].append(f"{stock} photo(s) in the concept are representative stock images (Openverse, "
                                        "credited in the footer); replace them with the business's own photos before launch.")
    write_json(path / "proposal.json", draft)
    if brief:
        archive_revision(path, brief)
    return draft
