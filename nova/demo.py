import json
import os
import re
from html import escape
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from .domain import NovaError

CSS = """
:root{color-scheme:light;--paper:#f5efe5;--ink:#29221d;--rust:#903c24;--line:#cbbbab}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:1rem/1.65 system-ui,sans-serif}
.wrap{width:min(1120px,calc(100% - 48px));margin-inline:auto}a{color:inherit;text-underline-offset:.25em}a:focus-visible{outline:3px solid #18527b;outline-offset:4px}
header{border-bottom:1px solid var(--line)}header .wrap{display:flex;justify-content:space-between;align-items:center;gap:1rem;min-height:78px}
.brand{font-weight:750;text-decoration:none}nav{display:flex;flex-wrap:wrap;gap:1rem}.notice{color:#613c2e;margin:1rem 0;font-size:.875rem}
.hero{display:grid;grid-template-columns:1.2fr 1fr;min-height:460px;align-items:center;padding:1rem 0 3rem;gap:3rem}
h1,h2{font-family:Georgia,serif;font-weight:400;line-height:1.07;letter-spacing:-.055em;margin:.25em 0}
h1{font-size:clamp(3.4rem,8vw,7rem)}h2{font-size:clamp(2.1rem,5vw,3.8rem)}p{max-width:54ch}.hero p{font-size:1.12rem}
.button{display:inline-flex;align-items:center;min-height:48px;padding:.55rem 1.25rem;background:var(--rust);color:#fff;text-decoration:none;font-weight:650;margin-top:1rem}
.figure{background:#d8a487;aspect-ratio:4/3;display:grid;place-content:center;overflow:hidden}
.form{width:clamp(110px,19vw,240px);aspect-ratio:1;background:#a34c30;border-radius:45% 41% 33% 35%;outline:1.2rem solid #b66c4e;box-shadow:0 1.3rem 0 1.4rem #71452f;transform:rotate(-12deg)}
section.block{border-top:1px solid var(--line);padding:3rem 0;scroll-margin-top:1rem}.block ul{padding-inline-start:1.3rem;max-width:66ch}.block li+li{margin-top:.6rem}
.demo-form{display:grid;gap:1.1rem;max-width:34rem;margin-top:1.35rem}.demo-form label{display:grid;gap:.3rem;font-weight:650}.demo-form input,.demo-form select{background:#fffefa;color:var(--ink);border:1px solid #9b8072;min-height:44px;padding:.55rem;font:inherit}.demo-form button{font:inherit;border:0;cursor:pointer;width:max-content}.demo-form p{min-height:1.4rem}
.official-links{display:flex;align-items:center;gap:1.1rem;flex-wrap:wrap;margin-top:1rem}.official-links .button{margin:0}
footer{border-top:1px solid var(--line);padding:1.5rem 0 3rem;color:#613c2e}
@media(max-width:680px){.wrap{width:calc(100% - 32px)}header .wrap{flex-wrap:wrap;padding:12px 0;gap:.25rem 1rem}nav a{padding:.45rem 0}.hero{grid-template-columns:1fr;gap:2rem}.form{width:35vw}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""

ENQUIRY = """
<section class="block" id="enquiry">
<h2>Try the enquiry form</h2>
<p>Use sample information to try this interaction. The preview does not send or store entries.</p>
<form class="demo-form">
<label>Sample name<input placeholder="Alex" required autocomplete="off" maxlength="60"></label>
<label>Enquiry topic<select required>
<option value="">Choose a topic</option><option>Availability</option><option>Group enquiry</option></select></label>
<button class="button" type="submit">Test enquiry</button>
<p role="status"></p>
</form>
</section>
"""
DEMO_JS = """
const form = document.querySelector(".demo-form");
if (form) form.addEventListener("submit", (event) => {
  event.preventDefault();
  form.reset();
  form.querySelector('[role="status"]').textContent = "Demo complete. No enquiry was sent.";
});
"""


def project_dir(root: Path, task_id: str):
    folder = root.resolve() / task_id
    if folder.is_symlink():
        raise NovaError("workspace", "The project path is a symbolic link.")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def atomic_write(path: Path, data: str):
    staging = path.with_name(f".{path.name}.new")
    if staging.is_symlink() or path.is_symlink():
        raise NovaError("workspace", "The project contains an unexpected symbolic link.")
    with staging.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    staging.replace(path)


def site_markup(lead):
    name = escape(lead["name"])
    url = escape(lead["url"], quote=True)
    next_url = escape(lead.get("next_url") or lead["url"], quote=True)
    ideas = "\n".join(f'<li>{escape(item["change"])}</li>' for item in lead["findings"][:3])
    has_enquiry = lead.get("unlabeled_fields", 0) > 0
    pottery = any(re.search(r"\b(pottery|ceramic|clay)\w*", line, re.I)
                  for line in [lead["name"], lead["title"], *lead["headings"]])
    introduction = ("Explore the studio’s pottery workshops and find the next step to book or enquire."
                    if pottery else "Find the business’s latest information and the next step to get in touch.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'none'">
<title>{name} | Website concept</title>
<link rel="stylesheet" href="style.css">
{('<script src="demo.js" defer></script>' if has_enquiry else '')}
</head>
<body>
<header><div class="wrap"><a class="brand" href="#top">{name}</a><nav aria-label="Main navigation">
<a href="#concept">Concept</a><a href="#next">Official website</a></nav></div></header>
<main class="wrap" id="top">
<p class="notice">Unofficial demonstration · Prepared for private review</p>
<div class="hero"><div><h1>{name}</h1><p>{introduction}</p>
<a class="button" href="#next">Find out more</a></div>
<div class="figure" aria-hidden="true"><div class="form"></div></div></div>
<section class="block" id="concept"><h2>Design changes</h2>
<p>This concept applies a responsive layout, clear navigation and readable page structure.</p>
{f"<ul>{ideas}</ul>" if ideas else ""}</section>
{ENQUIRY if has_enquiry else ''}
<section class="block" id="next"><h2>Official information</h2>
<p>For current offerings and availability, check the business’s own website.</p>
<div class="official-links"><a class="button" href="{next_url}" rel="noreferrer">See official offerings</a>
<a href="{url}" rel="noreferrer">Open official website</a></div></section>
</main>
<footer><div class="wrap">Private concept prepared by NOVA.</div></footer>
</body></html>
"""


def create_demo(root, task_id, lead):
    path = project_dir(root, task_id)
    atomic_write(path / "index.html", site_markup(lead))
    atomic_write(path / "style.css", CSS)
    atomic_write(path / "demo.js", DEMO_JS)
    return {"preview": f"/projects/{task_id}/index.html",
            "bytes": sum((path / item).stat().st_size for item in ("index.html", "style.css", "demo.js"))}


async def verify(root, task_id, lead):
    path = project_dir(root, task_id)
    for name in ("index.html", "style.css", "demo.js", "desktop.png", "mobile.png"):
        if (path / name).is_symlink():
            raise NovaError("workspace", "The project contains an unexpected symbolic link.")
    url = (path / "index.html").as_uri()
    checks = {}
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                env={k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG") if k in os.environ},
                args=["--disable-background-networking"],
            )
            try:
                for profile, width, height in (("desktop", 1440, 1050), ("mobile", 390, 844)):
                    page = await browser.new_page(viewport={"width": width, "height": height}, offline=True,
                                                  reduced_motion="reduce", service_workers="block")
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("console", lambda line: errors.append(line.text) if line.type == "error" else None)
                    await page.goto(url, wait_until="load", timeout=10000)
                    await page.get_by_role("link", name="Concept", exact=True).click(timeout=4000)
                    navigation = page.url.endswith("#concept")
                    result = await page.evaluate("""() => ({
                      width: document.documentElement.scrollWidth, viewport: innerWidth,
                      lang: document.documentElement.lang, title: document.title,
                      renderedCss: getComputedStyle(document.querySelector('.hero')).display === 'grid',
                      allImageAlternatives: [...document.images].every(img => img.hasAttribute('alt')),
                      durationMs: Math.round(performance.getEntriesByType('navigation')[0]?.duration || 0)
                    })""")
                    heading = await page.get_by_role("heading", level=1).all_text_contents()
                    official = await page.get_by_role("link", name="Open official website").get_attribute("href")
                    form_checked = False
                    if lead.get("unlabeled_fields"):
                        await page.get_by_label("Sample name").fill("Alex")
                        await page.get_by_label("Enquiry topic").select_option(label="Availability")
                        await page.get_by_role("button", name="Test enquiry").click()
                        await page.get_by_role("status").filter(has_text="Demo complete.").wait_for(timeout=3000)
                        form_checked = True
                    await page.evaluate("scrollTo(0,0)")
                    await page.screenshot(path=path / f"{profile}.png", full_page=True, timeout=8000)
                    await page.close()
                    if (errors or not navigation or result["width"] > result["viewport"]
                            or not result["lang"] or not result["renderedCss"] or not result["allImageAlternatives"]
                            or not result["title"] or heading != [lead["name"]] or official != lead["url"]):
                        raise NovaError("verify_failed", f"The {profile} preview did not pass its browser checks.")
                    checks[profile] = {
                        "width": width, "navigation": navigation, "console_errors": len(errors),
                        "document_load_ms": result["durationMs"], "content_matches_source_reference": True,
                        "accessibility_basics": ["document language", "one named H1", "image alternatives", "named navigation"],
                        "enquiry_preview_verified": form_checked,
                        "screenshot": f"/projects/{task_id}/{profile}.png",
                    }
            finally:
                await browser.close()
    except PlaywrightError as exc:
        raise NovaError("browser", "Chromium verification failed. Install the bundled browser with uv run playwright install chromium.") from exc
    return checks


def proposal(root, task_id, lead, checks):
    changes = lead["findings"][:3]
    hours = min(16, 6 + len(changes) * 2)
    demonstrated = ["Responsive layout", "Working navigation", "Direct link to official information"]
    if all(item["enquiry_preview_verified"] for item in checks.values()):
        demonstrated.append("Enquiry preview with persistent labels and local validation")
    draft = {
        "business": lead["name"], "source": lead["url"],
        "observations": [item["observation"] for item in changes],
        "scope": [item["change"] for item in changes],
        "demonstrated": demonstrated,
        "verification": sorted(checks), "effort_hours": hours, "proposed_price_inr": hours * 1200,
        "rate_basis": "Internal planning assumption of ₹1,200/hour. No quote was accepted and no revenue was recorded.",
        "limitations": [
            "Based on one publicly accessible page and a locally tested concept.",
            "Validate requirements, content, rights, booking needs and pricing with the business before delivery.",
        ],
    }
    atomic_write(project_dir(root, task_id) / "proposal.json", json.dumps(draft, indent=2, ensure_ascii=False))
    return draft
