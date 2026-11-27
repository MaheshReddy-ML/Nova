"""Benchmark NVIDIA catalogue chat models on NOVA's real jobs and print a routing recommendation.

    uv run python tools/model_bench.py [--models id ...] [--skip-site] [--out output/model-bench]

Tasks: (1) agent tool selection on four real requests, (2) spoken chat time-to-first-token, (3) a website plan rendered
through the site kit and scored by Chromium plus the vision critic. Calls go straight to the NVIDIA API and do not count
against NOVA's in-app budgets, but they do use the account's quota.
"""
import argparse
import asyncio
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nova.agent import TOOLS, Agent  # noqa: E402
from nova.commands import Commands  # noqa: E402
from nova.config import Settings  # noqa: E402
from nova.domain import Candidate, NovaError  # noqa: E402
from nova.gateway import Gateway, thinking_off  # noqa: E402
from nova.research import PublicResearch  # noqa: E402
from nova.runtime import Runtime  # noqa: E402
from nova.sitekit import render  # noqa: E402
from nova.sitekit.generate import parse_plan, score_variant, skill_guidance  # noqa: E402
from nova.sitekit import PLAN_SCHEMA_HINT  # noqa: E402
from nova.skills import SkillRegistry  # noqa: E402
from nova import sitegen  # noqa: E402

DEFAULT_MODELS = [
    "moonshotai/kimi-k3.1-pro", "mistralai/mistral-large-4-1t-a52b", "minimaxai/minimax-m3.1-flash", "z-ai/glm-5.3-flash",
    "stepfun-ai/step-5-preview", "nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia/nemotron-3.5-bolt-e4b", "google/gemma-3-12b-it",
]
TOOL_CASES = [
    ("What does claysutra.com offer?", {"read_website", "deep_research"}, "claysutra"),
    ("Find the contact details for allkind.studio", {"find_contacts"}, "allkind"),
    ("Build a website concept for regalmuse.in", {"start_mission"}, "regalmuse"),
    ("Find research internships abroad for summer 2027 that fit my profile", {"deep_research", "web_search", "get_owner_profile"}, ""),
]
CHAT = "Hey, quick one: in two sentences, why do reproducible evaluations matter for local language models?"


def strip_reasoning(text):
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


class Bench:
    def __init__(self, settings):
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(90, connect=10))
        self.headers = {"Authorization": f"Bearer {settings.nvidia_api_key.get_secret_value()}"}

    async def post(self, payload):
        for attempt in range(2):
            response = await self.client.post(f"{self.settings.nvidia_base_url}/chat/completions", headers=self.headers, json=payload)
            if response.status_code in (429, 502, 503, 504):
                await asyncio.sleep(6 * (attempt + 1))
                continue
            return response
        return response

    async def tool_case(self, model, system, prompt, expected, needle):
        payload = {"model": model, "max_tokens": 700, "temperature": 0.2, "tools": TOOLS, "tool_choice": "auto",
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], **thinking_off(model)}
        started = time.perf_counter()
        response = await self.post(payload)
        seconds = time.perf_counter() - started
        if response.status_code != 200:
            return {"ok": False, "seconds": seconds, "error": f"HTTP {response.status_code}: {response.text[:120]}"}
        body = response.json()
        message = body["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        names = [call["function"]["name"] for call in calls]
        args = " ".join(call["function"].get("arguments") or "" for call in calls).lower()
        ok = bool(set(names) & expected) and (needle in args if needle else True)
        return {"ok": ok, "seconds": seconds, "tools": names, "tokens": (body.get("usage") or {}).get("total_tokens")}

    async def chat_case(self, model):
        payload = {"model": model, "max_tokens": 300, "temperature": 0.4, "stream": True,
                   "messages": [{"role": "user", "content": CHAT}], **thinking_off(model)}
        started = time.perf_counter()
        first, text, chunks = None, "", 0
        async with self.client.stream("POST", f"{self.settings.nvidia_base_url}/chat/completions", headers=self.headers, json=payload) as response:
            if response.status_code != 200:
                return {"ok": False, "error": f"HTTP {response.status_code}"}
            async for line in response.aiter_lines():
                if not line.startswith("data:") or line.strip() == "data: [DONE]":
                    continue
                try:
                    delta = json.loads(line[5:])["choices"][0]["delta"]
                except (ValueError, KeyError, IndexError):
                    continue
                piece = delta.get("content") or ""
                if piece:
                    first = first or time.perf_counter()
                    text += piece
                    chunks += 1
        total = time.perf_counter() - started
        clean = strip_reasoning(text)
        return {"ok": bool(clean), "ttft": (first - started) if first else None, "seconds": total, "chars": len(clean),
                "chars_per_s": round(len(clean) / max(.01, total - ((first or started) - started)), 1), "sample": clean[:220]}

    async def long_completion(self, messages, *, model, max_output=2600, **_):
        payload = {"model": model, "messages": messages, "max_tokens": max_output, "temperature": 0.6, **thinking_off(model)}
        response = await self.post(payload)
        if response.status_code != 200:
            raise NovaError("provider_request", f"HTTP {response.status_code}")
        body = response.json()
        return {"text": strip_reasoning(body["choices"][0]["message"].get("content") or ""), "model": model,
                "usage": body.get("usage") or {}}


async def main(models, out, skip_site):
    settings = Settings()
    temp = Path(tempfile.mkdtemp())
    shutil.copy(ROOT / "memory" / "profile.json", temp / "profile.json") if (ROOT / "memory" / "profile.json").exists() else None
    bench_settings = Settings(database_path=temp / "bench.db", workspace_path=temp / "work")
    from nova.store import Store

    store = Store(bench_settings.database_path)
    gateway = Gateway(bench_settings, store)
    research = PublicResearch(store)
    runtime = Runtime(bench_settings, store, gateway, research)
    agent = Agent(runtime, Commands(runtime))
    bench = Bench(settings)
    registry = SkillRegistry(sqlite3.connect(":memory:"))
    out.mkdir(parents=True, exist_ok=True)
    brief = lead = page = photos = None
    if not skip_site:
        lead = await research.audit(Candidate(name="all kind studio", url="https://allkind.studio/"))
        page = await research.read_page("https://allkind.studio/")
        photos = await research.images("https://allkind.studio/")
        brief = sitegen.brief_text(lead, page) + f"\nPhotos available from their site: {len(photos)}."
    site_system = ("You are the creative director and senior copywriter of a top web design studio. A design system renders "
                   "your plan, so focus on direction, structure and words.\n\n" + skill_guidance(registry) + "\n\n" + PLAN_SCHEMA_HINT)
    previous = out / "results.json"
    results = json.loads(previous.read_text()) if previous.is_file() else {}
    for model in models:
        row = results[model] = {}
        print(f"== {model}", flush=True)
        cases = []
        for prompt, expected, needle in TOOL_CASES:
            try:
                cases.append(await bench.tool_case(model, agent.system_prompt(None, None, prompt), prompt, expected, needle))
            except httpx.HTTPError as exc:
                cases.append({"ok": False, "seconds": None, "error": "timeout >90s" if isinstance(exc, httpx.TimeoutException) else type(exc).__name__})
            if sum(1 for case in cases if "timeout" in str(case.get("error", ""))) >= 2:
                print("   too slow for interactive use; skipping remaining cases", flush=True)
                break
        timed = [case["seconds"] for case in cases if case.get("seconds")]
        row["tools"] = {"correct": sum(case["ok"] for case in cases), "of": len(cases),
                        "median_s": round(sorted(timed)[len(timed) // 2], 2) if timed else None, "cases": cases}
        print(f"   tools {row['tools']['correct']}/{len(cases)} · median {row['tools']['median_s']}s · {[c.get('tools') or c.get('error') for c in cases]}", flush=True)
        try:
            row["chat"] = await bench.chat_case(model)
        except httpx.HTTPError as exc:
            row["chat"] = {"ok": False, "error": type(exc).__name__}
        chat = row["chat"]
        print(f"   chat ttft {chat.get('ttft') and round(chat['ttft'], 2)}s · total {chat.get('seconds') and round(chat['seconds'], 2)}s", flush=True)
        if not skip_site:
            started = time.perf_counter()
            try:
                result = await bench.long_completion([{"role": "system", "content": site_system}, {"role": "user", "content": brief}], model=model)
                plan = parse_plan(result["text"])
                seconds = time.perf_counter() - started
                files = render(plan, images=photos, source_url=lead["url"], concept_by="Bench")
                report = await score_variant(gateway, files, out / model.replace("/", "_"), log=print)
                (out / model.replace("/", "_") / "plan.json").write_text(plan.model_dump_json(indent=2))
                row["site"] = {"ok": True, "seconds": round(seconds, 1), "technical": report["score"], "design": report["design_score"],
                               "combined": report["combined"], "theme": plan.theme, "headline": plan.hero_headline}
            except (NovaError, ValueError, httpx.HTTPError) as exc:
                row["site"] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
            print(f"   site {row['site']}", flush=True)
        (out / "results.json").write_text(json.dumps(results, indent=2, default=str))
    await gateway.close()
    await research.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--out", type=Path, default=ROOT / "output" / "model-bench")
    parser.add_argument("--skip-site", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.models, args.out, args.skip_site))
