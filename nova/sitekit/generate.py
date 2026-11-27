"""Plan → render → evaluate → critique → revise, using the site kit."""
import json
import re
from pathlib import Path

from pydantic import ValidationError

from ..domain import NovaError
from .. import sitegen
from . import PLAN_SCHEMA_HINT, THEMES, SitePlan, render

ALTERNATE = {"editorial": "noir", "noir": "editorial", "modern": "fresh", "fresh": "modern"}
SKILLS = ("copywriting", "frontend-design", "theme-factory")


def skill_guidance(registry):
    if registry is None:
        return ""
    parts = []
    for skill_id in SKILLS:
        try:
            guide = registry.agent_guide(skill_id)
        except NovaError:
            continue
        parts.append(f"### {guide.title}\n{guide.instructions[:2600]}")
    return "\n\n".join(parts)


def _text(value):
    if isinstance(value, list):
        return "\n\n".join(_text(item) for item in value if item)
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values() if item)
    return "" if value is None else str(value)


def _fit(text, limit):
    """Trim to a limit at a sentence or word boundary instead of rejecting the whole plan."""
    text = " ".join(text.split()) if "\n" not in text else text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in (". ", "! ", "? "):
        if cut.rfind(mark) > limit * .6:
            return cut[:cut.rfind(mark) + 1]
    return cut.rsplit(" ", 1)[0].rstrip(",;:—-")


def parse_plan(text):
    """Extract and repair the first JSON object in a model reply, then validate it as a SitePlan."""
    start = text.find("{")
    if start < 0:
        raise NovaError("sitekit_format", "The model did not return a JSON plan.")
    data, _ = json.JSONDecoder().raw_decode(text[start:])  # ignores anything after the first object
    if not isinstance(data, dict):
        raise NovaError("sitekit_format", "The model did not return a JSON plan.")
    fields = SitePlan.model_fields
    clean = {}
    for key, value in data.items():
        if key not in fields:
            continue
        if key in ("highlights", "offerings", "steps", "locations", "faq"):
            items = []
            for item in value if isinstance(value, list) else []:
                if isinstance(item, str):
                    item = {"title": item}
                if isinstance(item, dict) and item.get("title"):
                    items.append({"title": _fit(_text(item.get("title")), 70), "text": _fit(_text(item.get("text") or item.get("description")), 320),
                                  "meta": _fit(_text(item.get("meta")), 60)})
            clean[key] = items[:{"highlights": 4, "steps": 4, "locations": 3, "faq": 5}.get(key, 6)]
        elif key == "enquiry_topics":
            clean[key] = [_fit(_text(item), 60) for item in (value if isinstance(value, list) else [value]) if item][:6]
        elif key == "theme":
            clean[key] = _text(value).strip().lower()
        else:
            limit = next((item.max_length for item in fields[key].metadata if hasattr(item, "max_length")), None)
            clean[key] = _fit(_text(value), limit) if limit else _text(value)
    return SitePlan.model_validate(clean)


async def plan_site(gateway, model, system, brief, *, feedback=None, previous=None, log=print):
    messages = [{"role": "system", "content": system}, {"role": "user", "content": brief}]
    if previous is not None:
        messages += [{"role": "assistant", "content": previous.model_dump_json()},
                     {"role": "user", "content": "A design director reviewed the rendered page. Improve the plan accordingly: "
                      "sharper, more specific headline and copy, better section choices, a better-fitting theme or accent if "
                      "needed. Same JSON format.\n\n" + feedback}]
    last_error = None
    for _ in range(2):
        result = await gateway.long_completion(messages, model=model, max_output=2600)
        try:
            return parse_plan(result["text"]), result["usage"]
        except (ValueError, ValidationError, NovaError) as exc:
            last_error = exc
            messages += [{"role": "assistant", "content": result["text"][:6000]},
                         {"role": "user", "content": f"That was not valid. Error: {str(exc)[:400]}. Return only the corrected JSON object."}]
    raise NovaError("sitekit_plan", f"The model could not produce a valid site plan ({type(last_error).__name__}).")


async def score_variant(gateway, files, out_dir: Path, critic=True, log=print):
    report = await sitegen.evaluate(files, out_dir)
    critique = None
    if critic:
        try:
            critique = await sitegen.visual_critique(gateway, out_dir / "desktop-full.png")
        except NovaError as exc:
            log(f"  visual critique unavailable: {exc}")
    design = critique["overall"] * 10 if critique else None
    report.update(design_score=design, critique=critique,
                  combined=round(report["score"] * .4 + design * .6, 1) if design is not None else report["score"])
    return report


async def build(gateway, lead, page, photos, *, settings, registry=None, out_dir: Path, concept_by="", log=print,
                rounds=1, alternates=True):
    contacts = (page or {}).get("contacts", {})
    phone = (contacts.get("phones") or [""])[0]
    system = ("You are the creative director and senior copywriter of a top web design studio. You plan landing pages "
              "that make small businesses look premium and win them customers. A design system renders your plan, so "
              "focus on direction, structure and words.\n\n" + skill_guidance(registry) + "\n\n" + PLAN_SCHEMA_HINT)
    brief = (sitegen.brief_text(lead, page) + f"\nPhotos available from their site: {len(photos)}."
             + (f"\nPublished phone: {phone}" if phone else ""))
    plan, _ = await plan_site(gateway, settings.site_model, system, brief, log=log)
    log(f"  plan: theme {plan.theme}, headline “{plan.hero_headline}”")
    candidates = []

    async def attempt(current, theme, label):
        variant = current.model_copy(update={"theme": theme})
        files = render(variant, images=photos, phone=phone, source_url=lead["url"], concept_by=concept_by)
        report = await score_variant(gateway, files, out_dir / label, log=log)
        (out_dir / label / "plan.json").write_text(variant.model_dump_json(indent=2), encoding="utf-8")
        log(f"  {label}: theme {theme} · technical {report['score']} · design {report['design_score']} · combined {report['combined']}")
        candidates.append({"plan": variant, "files": files, "report": report, "label": label})

    await attempt(plan, plan.theme, "a-chosen")
    if alternates:
        await attempt(plan, ALTERNATE.get(plan.theme, THEMES[0]), "b-alternate")
    best = max(candidates, key=lambda item: item["report"]["combined"])
    for round_index in range(rounds):
        critique = best["report"].get("critique")
        if not critique:
            break
        feedback = critique["fixes"] + ("\nMeasured issues: " + "; ".join(best["report"]["issues"]) if best["report"]["issues"] else "")
        try:
            revised, _ = await plan_site(gateway, settings.site_model, system, brief, feedback=feedback, previous=best["plan"], log=log)
        except NovaError as exc:
            log(f"  revision skipped: {exc}")
            break
        await attempt(revised, revised.theme, f"c-revision-{round_index + 1}")
        best = max(candidates, key=lambda item: item["report"]["combined"])
    return {"best": best, "candidates": candidates}


async def build_project(root: Path, task_id: str, lead: dict, research, gateway, settings, registry=None, log=None):
    """Kit-built concept written into the project folder in the layout the dashboard and preview server expect."""
    import hashlib
    import shutil

    from .. import demo
    from ..sitegen import PROFILES

    log = log or (lambda _: None)
    try:
        page = await research.read_page(lead["url"])
    except NovaError:
        page = None
    try:
        photos = await research.images(lead["url"])
    except NovaError:
        photos = []
    concept_by = settings.business_name or settings.owner_name
    scratch = root / f".sitekit-{task_id}"
    shutil.rmtree(scratch, ignore_errors=True)
    try:
        outcome = await build(gateway, lead, page, photos, settings=settings, registry=registry, out_dir=scratch,
                              concept_by=concept_by, log=log, rounds=settings.site_revision_rounds)
        best = outcome["best"]
        path = demo.project_dir(root, task_id)
        for stale in path.iterdir():
            if stale.is_file() and (stale.suffix in {".jpg", ".woff2"} or stale.name == "demo.js"):
                stale.unlink()
        for name, content in best["files"].items():
            demo.atomic_write(path / name, content)
        for profile, _, _ in PROFILES:
            demo.atomic_write(path / f"{profile}.png", (scratch / best["label"] / f"{profile}-full.png").read_bytes())
        (path / "plan.json").write_text(best["plan"].model_dump_json(indent=2), encoding="utf-8")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    report = best["report"]
    revision = hashlib.sha256((best["files"]["index.html"] + best["files"]["style.css"]).encode()).hexdigest()[:12]
    checks = {}
    for profile, width, _ in PROFILES:
        data = report["profiles"][profile]
        problems = [rule["summary"] for rule in data["axe"]] + (["Horizontal overflow"] if data["overflow_px"] > 2 else [])
        checks[profile] = {"width": width, "console_errors": len(data["errors"]), "navigation": data["landmarks"] >= 4,
                           "accessibility": {"engine": "axe-core", "violations": data["axe"], "manual_review": []},
                           "screenshot": f"/projects/{task_id}/{profile}.png", "issues": problems, "passed": not problems}
    critique = report.get("critique") or {}
    plan = best["plan"]
    design = {"revision": revision, "builder": "kit", "model": settings.site_model, "category": plan.theme,
              "direction": f"{plan.theme.title()} theme · “{plan.hero_headline}”",
              "composition": f"Best of {len(outcome['candidates'])} rendered variants ({', '.join(c['label'] for c in outcome['candidates'])})",
              "source": {"business": lead["name"], "url": lead["url"]}, "photos": len(photos),
              "skills": [skill for skill in SKILLS if registry is not None],
              "scores": {"technical": report["score"], "design": report.get("design_score"), "combined": report["combined"]},
              "critique": critique.get("fixes")}
    demo.write_json(path / "design.json", design)
    demo.write_json(path / "verification.json", {"revision": revision, "profiles": checks, "scores": design["scores"],
                                                  "issues": report["issues"],
                                                  "assessment": "Chromium render, axe-core and an NVIDIA vision design review."})
    demo.atomic_write(path / "delivery.md", f"# {lead['name']} concept\n\n{design['direction']}. Technical {report['score']}/100, "
                      f"design {report.get('design_score')}/100. Fonts: SIL Open Font License. Photos: the business's own site.\n")
    return {"preview": f"/projects/{task_id}/index.html", "revision": revision, "design": design, "builder": "kit",
            "checks": checks, "score": report["combined"], "attempts": len(outcome["candidates"]),
            "files": sorted(best["files"])}
