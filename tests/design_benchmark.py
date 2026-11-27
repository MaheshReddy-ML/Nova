"""Reproduce NOVA's fixture-based cross-industry website evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import statistics
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright

from nova import demo
from nova.skills import SkillRegistry

BASELINE_COMMIT = "2bf16ff5ad9517fa8f545d5095aecad5f074a99b"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    "restaurant": ("Amber Table Restaurant", "Seasonal dining"),
    "architecture": ("Stillline Architecture", "Architecture and urban design"),
    "healthcare": ("Northwood Dental Clinic", "Dental clinic visitor information"),
    "hospitality": ("Alder Bay Boutique Hotel", "Boutique hotel reservations"),
    "software": ("Indexline Software", "Analytics platform and developer documentation"),
}
LIGHTHOUSE_RELEASE = "13.6.0"


def evidence(category, name, title):
    return {
        "name": name, "title": title, "headings": [title],
        "url": f"https://example.com/{category}", "next_url": f"https://example.com/{category}/contact",
        "unlabeled_fields": 1,
        "findings": [
            {"observation": "One fixture form field had no associated label.",
             "change": "Keep visible labels associated with each enquiry control."},
            {"observation": "The fixture treated multiple section titles as top-level headings.",
             "change": "Use a single top-level heading and put sections below it."},
        ],
    }


def local_baseline():
    # Run the known, immutable pre-upgrade implementation from the project checkpoint.
    snapshot = subprocess.run(
        ["git", "show", f"{BASELINE_COMMIT}:nova/demo.py"], cwd=PROJECT_ROOT,
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout
    namespace = {"__package__": "nova", "__name__": "nova._baseline"}
    exec(compile(snapshot, f"nova/demo.py@{BASELINE_COMMIT}", "exec"), namespace)
    return namespace["create_demo"]


async def run_case(build, folder, case_id, category, name, title, skill_ids=None):
    lead = evidence(category, name, title)
    started = time.perf_counter()
    if skill_ids is None:
        result = build(folder, case_id, lead)
    else:
        result = build(folder, case_id, lead, skill_ids=skill_ids)
    built_in = time.perf_counter() - started
    checks = await demo.verify(folder, case_id, lead, strict=False)
    verified_in = time.perf_counter() - started - built_in
    return {
        "category": category,
        "direction": result.get("design", {}).get("direction", "Shared baseline template"),
        "selected_category": result.get("design", {}).get("category"),
        "code_bytes": result["bytes"],
        "build_seconds": round(built_in, 4),
        "browser_seconds": round(verified_in, 3),
        "screenshots_dir": str(folder / case_id),
        "profiles": [
            {"profile": profile, "passed": item["passed"], "issues": item["issues"],
             "axe_violations": len(item["accessibility"]["violations"]),
             "min_touch_target_px": item["accessibility"]["min_touch_target_px"],
             "keyboard_skip_usable": item["accessibility"]["keyboard_focus"],
             "fcp_ms": item["performance"]["fcp_ms"], "lcp_ms": item["performance"]["lcp_ms"],
             "cls": item["performance"]["cls"], "structure": item["visual"]["structure"]}
            for profile, item in checks.items()
        ],
    }


async def browser_executable():
    async with async_playwright() as playwright:
        return playwright.chromium.executable_path


def lighthouse_case(folder, chrome):
    assets = {name: (folder / name).read_bytes() for name in demo.SOURCE_FILES}

    class PreviewServer(BaseHTTPRequestHandler):
        def do_GET(self):
            name = self.path.removeprefix("/")
            if name not in assets:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", demo.CONTENT_TYPES[name])
            self.send_header("Content-Security-Policy", demo.PREVIEW_CSP)
            self.send_header("Content-Length", str(len(assets[name])))
            self.end_headers()
            self.wfile.write(assets[name])

        def log_message(self, *_):
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), PreviewServer) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        report_path = folder / "lighthouse.tmp.json"
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("Install Node.js and npm to run the optional Lighthouse benchmark.")
        try:
            subprocess.run(
                [npm, "exec", "--yes", f"--package=lighthouse@{LIGHTHOUSE_RELEASE}", "--",
                 "lighthouse", f"http://127.0.0.1:{server.server_port}/index.html", "--quiet",
                 "--only-categories=performance", "--output=json", f"--output-path={report_path}",
                 "--chrome-flags=--headless --disable-background-networking --no-proxy-server"],
                env=demo.browser_env() | {"CHROME_PATH": chrome, "NPM_CONFIG_IGNORE_SCRIPTS": "true",
                                           "NPM_CONFIG_USERCONFIG": "/dev/null"},
                check=True, timeout=90, capture_output=True, text=True,
            )
            report = json.loads(report_path.read_text())
        finally:
            server.shutdown()
            worker.join(timeout=3)
            report_path.unlink(missing_ok=True)
    audits = report["audits"]
    return {
        "version": report["lighthouseVersion"],
        "score": report["categories"]["performance"]["score"],
        "fcp_ms": audits["first-contentful-paint"]["numericValue"],
        "lcp_ms": audits["largest-contentful-paint"]["numericValue"],
        "cls": audits["cumulative-layout-shift"]["numericValue"],
        "measurement": "Lighthouse simulated mobile run against the loopback fixture",
    }


def totals(cases):
    profiles = [profile for case in cases for profile in case["profiles"]]
    fcp = [profile["fcp_ms"] for profile in profiles if profile["fcp_ms"] is not None]
    return {
        "projects": len(cases), "profile_checks": len(profiles),
        "profiles_passing_gates": sum(profile["passed"] for profile in profiles),
        "axe_violations": sum(profile["axe_violations"] for profile in profiles),
        "min_touch_target_px": min(profile["min_touch_target_px"] for profile in profiles),
        "profiles_with_working_keyboard_skip": sum(profile["keyboard_skip_usable"] for profile in profiles),
        "distinct_rendered_structures": len({item["structure"] for item in profiles}),
        "median_browser_fcp_ms": statistics.median(fcp) if fcp else None,
        "median_code_bytes": statistics.median(case["code_bytes"] for case in cases),
        "model_calls": 0, "provider_tokens": 0,
    }


async def benchmark(output, run_lighthouse):
    db = sqlite3.connect(":memory:")
    try:
        registry = SkillRegistry(db)
        guide = registry.evaluate("impeccable")
        skills = tuple(item.skill_id for item in registry.resolve("website", "build"))
    finally:
        db.close()
    output.mkdir(parents=True, exist_ok=True)
    old_build = local_baseline()
    before, after = [], []
    for index, (category, (name, title)) in enumerate(CATEGORIES.items(), start=1):
        task = f"{index:012x}"
        before.append(await run_case(old_build, output / "baseline", task, category, name, title))
        after.append(await run_case(demo.create_demo, output / "upgraded", task, category, name, title, skills))
    report = {
        "scope": "Five synthetic briefs and offline Chromium. Names, observations and URLs are fixtures.",
        "baseline_commit": BASELINE_COMMIT,
        "phases": {
            "A_baseline": totals(before) | {"cases": before},
            "B_full_skill_size_only": {
                "skill": "impeccable", "estimated_context_upper_bound": guide["source_estimated_tokens"],
                "measurement": "Pinned upstream skill byte estimate. Raw upstream text is outside inference.",
            },
            "C_compiled_skill": {
                "skill": "impeccable", "estimated_context_upper_bound": guide["guide_estimated_tokens"],
                "measurement": "Compiled guide byte estimate. Local fixtures use category-driven components.",
            },
            "D_upgraded_verified": totals(after) | {"cases": after, "activated_skills": skills},
        },
    }
    if run_lighthouse:
        chrome = await browser_executable()
        report["lighthouse"] = {
            "baseline_restaurant": await asyncio.to_thread(lighthouse_case, Path(before[0]["screenshots_dir"]), chrome),
            "upgraded_restaurant": await asyncio.to_thread(lighthouse_case, Path(after[0]["screenshots_dir"]), chrome),
        }
    path = output / "benchmark.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "report": str(path),
        "baseline": totals(before), "upgraded": totals(after),
        "skill_context_estimates": [guide["source_estimated_tokens"], guide["guide_estimated_tokens"]],
        "lighthouse": report.get("lighthouse"),
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/playwright/nova-2-design"))
    parser.add_argument("--lighthouse", action="store_true", help="Also benchmark the restaurant fixture with pinned Lighthouse")
    args = parser.parse_args()
    asyncio.run(benchmark(args.output.resolve(), args.lighthouse))
