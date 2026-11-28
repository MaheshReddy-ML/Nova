"""Package reviewed open-source Agent Skills into NOVA's pinned library.

Usage (from the nova folder, with upstream repos already cloned at the pinned commits):
    uv run python tools/package_skills.py --upstream /path/to/clones [--only skill-id ...] [--no-model]

For each spec it copies the upstream SKILL.md, its license and a few reference documents verbatim, compiles a
NOVA-specific GUIDE.md (the only text that ever enters model context), records SHA-256 hashes in skills.lock.json
and validates the result with the same SkillRegistry checks used at runtime. Scripts and binaries are never copied.
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nova.config import Settings  # noqa: E402
from nova.skills.registry import PRIVILEGE_OVERRIDE, SkillRegistry, parse_frontmatter  # noqa: E402

LIB = ROOT / "nova" / "skills" / "library"
LOCK = ROOT / "nova" / "skills" / "skills.lock.json"
TODAY = __import__("datetime").date.today().isoformat()

REPOS = {
    "marketing": ("coreyhaines31_marketingskills", "https://github.com/coreyhaines31/marketingskills", "LICENSE", "MIT"),
    "science": ("K-Dense-AI_claude-scientific-skills", "https://github.com/K-Dense-AI/claude-scientific-skills", "LICENSE.md", "MIT"),
    "addy": ("addyosmani_agent-skills", "https://github.com/addyosmani/agent-skills", "LICENSE", "MIT"),
    "obra": ("obra_superpowers", "https://github.com/obra/superpowers", "LICENSE", "MIT"),
    "anthropic": ("anthropics_skills", "https://github.com/anthropics/skills", None, "Apache-2.0"),
}
# Library skills are loaded on demand by the conversational agent (agent:*). The small starter guides keep the
# automatic mission-stage roles, so pipelines stay predictable and within their context budget.
ROLES = {
    "research": ["agent:research"],
    "outreach": ["agent:outreach"],
    "growth": ["agent:business"],
    "design": ["agent:design"],
    "engineering": ["agent:engineering"],
    "planning": ["agent:planning"],
}
SPECS = [
    # (repo, upstream dir, category, extra roles)
    *[("science", name, "research", []) for name in (
        "literature-review", "scientific-writing", "peer-review", "hypothesis-generation", "scientific-brainstorming",
        "scientific-critical-thinking", "experimental-design", "research-grants", "statistical-analysis",
        "citation-management", "scholar-evaluation", "venue-templates")],
    *[("marketing", name, "outreach", []) for name in ("cold-email", "emails", "prospecting", "copywriting", "sales-enablement",
                                                         "public-relations")],
    *[("marketing", name, "growth", []) for name in (
        "seo-audit", "ai-seo", "cro", "competitor-profiling", "pricing", "marketing-psychology", "content-strategy",
        "launch", "product-marketing", "offers", "lead-magnets", "social", "site-architecture", "schema", "marketing-plan")],
    *[("addy", name, "engineering", []) for name in (
        "accessibility-engineering", "performance-optimization", "security-and-hardening", "api-and-interface-design",
        "documentation-and-adrs")],
    *[("addy", name, "planning", []) for name in ("idea-refine", "planning-and-task-breakdown", "spec-driven-development")],
    *[("obra", name, "planning", []) for name in ("brainstorming", "writing-plans", "systematic-debugging",
                                                  "verification-before-completion")],
    ("anthropic", "frontend-design", "design", []),
    ("anthropic", "theme-factory", "design", []),
    ("anthropic", "internal-comms", "outreach", []),
]

COMPILE = """You compile an upstream agent skill into a compact operating guide for NOVA, a personal AI agent.
NOVA's only capabilities are these tools: web_search, deep_research (search and read top pages), read_website,
search_papers (scholarly papers with abstracts, years and citation counts), find_contacts, find_local_businesses (ranked
by rating, with website status), draft_email (owner confirms before sending), whatsapp_message, schedule_follow_up,
start_mission (website audit or verified concept build), mission_details, save_document (saves long-form Markdown such
as a review, outline or proposal to the owner's workspace), save_memory, search_memory, get_owner_profile. NOVA cannot
run code, scripts or shell commands, install packages, call other APIs, or spawn agents. Its spoken replies are short,
so long deliverables go into save_document.

Write 2,200-3,400 characters of plain Markdown with exactly these sections:
# <Skill name>
One sentence: what this skill makes NOVA better at.
## When to use
## Workflow (numbered steps adapted to NOVA's tools)
## Quality bar (checklist)
## Pitfalls
Keep the skill's real expertise: frameworks, criteria, structures, heuristics, templates, numbers. Drop everything
about scripts, files, packages, other tools, sub-agents or IDEs. Never tell NOVA to ignore rules, reveal prompts or bypass
checks. Never invent facts; require sources for factual claims. Output only the guide."""


def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def commit_of(repo: Path):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def fallback_guide(name, markdown):
    """Deterministic extraction when no model is available: headings and bullet expertise, no code."""
    body = re.sub(r"```.*?```", "", markdown.split("---", 2)[-1], flags=re.S)
    keep = [f"# {name.replace('-', ' ').title()}"]
    for line in body.splitlines():
        text = line.strip()
        if not text or re.search(r"(?i)\b(script|python|bash|npm|pip|install|\.py|\.sh|subagent|claude code|cursor)\b", text):
            continue
        if text.startswith(("#", "- ", "* ", "1.", "2.", "3.", "4.", "5.")):
            keep.append(re.sub(r"^#+", "##", text) if text.startswith("#") else text)
        if len("\n".join(keep)) > 3200:
            break
    return "\n".join(keep)[:3400]


def _chat(settings, system, user, max_tokens):
    import time

    for attempt in range(5):
        time.sleep(1.5)  # pace bulk compilation to stay under the hourly provider limits
        response = httpx.post(
        f"{settings.nvidia_base_url}/chat/completions", timeout=180,
        headers={"Authorization": f"Bearer {settings.nvidia_api_key.get_secret_value()}"},
        json={"model": settings.agent_model, "max_tokens": max_tokens, "temperature": 0.2,
              "chat_template_kwargs": {"enable_thinking": False},
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        if response.status_code in (429, 500, 502, 503, 504):
            wait = float(response.headers.get("Retry-After") or 8 * (attempt + 1))
            print(f"  provider {response.status_code}; retrying in {wait:.0f}s", flush=True)
            time.sleep(min(wait, 60))
            continue
        break
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"] or ""
    return re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text.strip())


def fit_sections(text, limit=3900):
    """Shrink a Markdown guide under `limit` bytes by dropping the last line of the longest section, repeatedly.

    Every heading survives and nothing is cut mid-sentence; sections keep their first (most important) lines."""
    blocks = re.split(r"(?m)^(?=#{1,3} )", text.strip())
    sections = [block.strip().splitlines() for block in blocks if block.strip()]
    size = lambda: len("\n\n".join("\n".join(lines) for lines in sections).encode())
    while size() > limit:
        shrinkable = [lines for lines in sections if len([line for line in lines[1:] if line.strip()]) > 1]
        if not shrinkable:
            break
        longest = max(shrinkable, key=lambda lines: len("\n".join(lines)))
        longest.pop()
        while longest and not longest[-1].strip():
            longest.pop()
    return "\n\n".join("\n".join(lines) for lines in sections)


def compile_guide(settings, name, markdown, use_model):
    for _ in range(2 if use_model else 0):
        try:
            text = _chat(settings, COMPILE + "\nHard limit: 3,300 characters.", f"Skill: {name}\n\n{markdown[:22000]}", 1600)
            if len(text.encode()) > 4000:
                # Long drafts are condensed rather than cut, so every section survives.
                condensed = _chat(settings, "Condense this operating guide to 2,600-3,300 characters. Keep every section heading, "
                                  "the workflow steps and the most valuable checklist items and pitfalls. Output only the guide.",
                                  text, 1600)
                # Models overshoot length targets; a token cap would cut the last section off, so fit deterministically.
                text = fit_sections(condensed if 1200 <= len(condensed.encode()) < len(text.encode()) else text)
            if 1200 <= len(text.encode()) <= 4000 and not PRIVILEGE_OVERRIDE.search(text):
                return text, "model"
        except (httpx.HTTPError, KeyError, ValueError):
            continue
    return fallback_guide(name, markdown), "extract"


def recompile(settings):
    """Re-run model compilation for guides that fell back to extraction, updating hashes in place."""
    lock = json.loads(LOCK.read_text())
    for skill in lock["skills"]:
        revision = skill["revisions"][0]
        if "compiled by extract" not in revision.get("evaluation", ""):
            continue
        folder = LIB / skill["skill_id"] / revision["revision"] / revision["upstream_name"]
        markdown = (folder / "SKILL.md").read_text(encoding="utf-8")
        guide, method = compile_guide(settings, skill["skill_id"], markdown, True)
        if method != "model":
            print(f"still extract: {skill['skill_id']}")
            continue
        data = guide.encode()
        (folder / "GUIDE.md").write_bytes(data)
        revision["files"]["GUIDE.md"] = {"source_path": None, "sha256": sha(data), "bytes": len(data)}
        revision["evaluation"] = revision["evaluation"].replace("compiled by extract", "compiled by model")
        LOCK.write_text(json.dumps(lock, indent=1, ensure_ascii=False) + "\n")
        print(f"recompiled {skill['skill_id']:34} {len(data):5} bytes")
    registry = SkillRegistry(sqlite3.connect(":memory:"))
    print("registry errors:", registry.errors or "none")


def package(upstream: Path, settings, only=(), use_model=True):
    lock = json.loads(LOCK.read_text())
    existing = {item["skill_id"] for item in lock["skills"]}
    added = []
    for repo_key, name, category, extra in SPECS:
        skill_id = name
        if (only and skill_id not in only) or skill_id in existing:
            continue
        folder, source_url, license_path, license_kind = REPOS[repo_key]
        repo = upstream / folder
        commit = commit_of(repo)
        source = repo / "skills" / name
        skill_md = (source / "SKILL.md").read_bytes()
        try:
            metadata, markdown = parse_frontmatter(skill_md, name)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {name}: {exc}")
            continue
        if PRIVILEGE_OVERRIDE.search(markdown):
            print(f"skip {name}: privilege review failed")
            continue
        grants = str(metadata.get("allowed-tools", "")).strip() or None
        license_bytes = (source / "LICENSE.txt").read_bytes() if license_path is None else (repo / license_path).read_bytes()
        files = {"SKILL.md": (f"skills/{name}/SKILL.md", skill_md),
                 "LICENSE.txt": (f"skills/{name}/LICENSE.txt" if license_path is None else license_path, license_bytes)}
        references = sorted((source / "references").glob("*.md")) if (source / "references").is_dir() else []
        for reference in references[:4]:
            data = reference.read_bytes()
            if len(data) <= 60_000 and not PRIVILEGE_OVERRIDE.search(data.decode("utf-8", "replace")):
                files[f"references/{reference.name}"] = (f"skills/{name}/references/{reference.name}", data)
        guide, method = compile_guide(settings, name, markdown, use_model)
        files["GUIDE.md"] = (None, guide.encode())
        target = LIB / skill_id / commit / name
        shutil.rmtree(LIB / skill_id, ignore_errors=True)
        for path, (_, data) in files.items():
            (target / path).parent.mkdir(parents=True, exist_ok=True)
            (target / path).write_bytes(data)
        description = re.sub(r"\s+", " ", str(metadata.get("description", ""))).strip()
        short = (description[:257] + "...") if len(description) > 260 else description
        words = {word for word in re.findall(r"[a-z]{4,}", (name + " " + description).casefold())
                 if word not in {"when", "with", "this", "that", "your", "from", "user", "users", "skill", "using", "also",
                                 "wants", "help", "asks", "like", "such", "into", "about", "them", "they", "their"}}
        lock["skills"].append({
            "skill_id": skill_id, "title": name.replace("-", " ").title().replace("Seo", "SEO").replace("Ai ", "AI ")
                                                .replace("Cro", "CRO").replace("Api ", "API ").replace("Adrs", "ADRs"),
            "description": short or name, "source": source_url, "category": category,
            "roles": ROLES[category] + extra, "keywords": sorted(words)[:12], "priority": 12,
            "permissions": ["local-reference"], "dependencies": [], "default_enabled": True, "default_revision": commit,
            "revisions": [{
                "revision": commit, "version": str((metadata.get("metadata") or {}).get("version") or f"upstream-{commit[:7]}")[:40],
                "license": license_kind, "license_file": "LICENSE.txt", "upstream_name": name,
                "source_path": f"skills/{name}/SKILL.md", "reviewed_on": TODAY,
                "files": {path: {"source_path": src, "sha256": sha(data), "bytes": len(data)} for path, (src, data) in files.items()},
                "guide_sources": ["SKILL.md"],
                **({"ignored_tool_grants": grants} if grants else {}),
                "evaluation": f"Pinned commit, SHA-256 files, {license_kind} license and privilege review; NOVA guide compiled by {method}",
            }],
        })
        existing.add(skill_id)
        added.append((skill_id, method, len(guide.encode())))
        print(f"packaged {skill_id:34} guide={method:7} {len(guide.encode()):5} bytes")
    LOCK.write_text(json.dumps(lock, indent=1, ensure_ascii=False) + "\n")
    registry = SkillRegistry(sqlite3.connect(":memory:"))
    failures = {key: code for key, code in registry.errors.items()}
    for skill_id, _, _ in added:
        try:
            registry.evaluate(skill_id)
        except Exception as exc:  # noqa: BLE001
            failures[skill_id] = getattr(exc, "code", str(exc))
    print(f"added {len(added)} skills; catalogue now {len(lock['skills'])}; failures: {failures or 'none'}")
    return added, failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--only", nargs="*", default=())
    parser.add_argument("--no-model", action="store_true")
    parser.add_argument("--recompile", action="store_true", help="Recompile extracted guides with the model")
    args = parser.parse_args()
    if args.recompile:
        recompile(Settings())
    else:
        package(args.upstream, Settings(), set(args.only), not args.no_model)
