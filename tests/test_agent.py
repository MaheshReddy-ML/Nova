import json
from types import SimpleNamespace

import pytest

from nova.agent import Agent, needs_tool
from nova.commands import Commands
from nova.config import Settings
from nova.conversation import CONFIRM_SEND, DECLINE_SEND, Session
from nova.domain import NovaError
from nova.runtime import Runtime
from nova.sitegen import parse_site, score
from nova.store import Store


class ScriptedGateway:
    """Returns pre-baked assistant messages in order and records the tools offered."""

    def __init__(self, *messages):
        self.messages = list(messages)
        self.calls = []

    async def agent_chat(self, messages, tools, *, require_tool=False, max_output=700, fast=False):
        self.calls.append({"tools": bool(tools), "require_tool": require_tool, "fast": fast, "system": messages[0]["content"]})
        return {"usage": {"total_tokens": 100}, **self.messages.pop(0)}


def call(name, **args):
    return {"id": name, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class FakeResearch:
    async def contacts(self, url):
        return {"url": "https://elm.example/", "title": "Elm Studio", "visited": [url], "contact_page": None,
                "emails": ["hello@elm.example"], "phones": ["919000000000"], "whatsapp": [], "social": []}

    async def web_search(self, query, limit=6):
        return {"query": query, "results": []}


@pytest.fixture
def runtime(tmp_path):
    settings = Settings(_env_file=None, database_path=tmp_path / "nova.db", workspace_path=tmp_path / "work",
                        smtp_host="smtp.example.com", smtp_username="me@example.com", smtp_password="secret",
                        admin_emails="owner@example.com")
    store = Store(settings.database_path)
    yield Runtime(settings, store, None, FakeResearch())
    store.db.close()


def test_email_aliases_and_derived_sender(monkeypatch, tmp_path):
    for key, value in {"EMAIL_HOST": "smtp.gmail.com", "EMAIL_PORT": "465", "EMAIL_USER": "me@gmail.com",
                       "EMAIL_PASS": "abcd efgh ijkl mnop", "ADMIN_EMAILS": "a@x.com, b@x.com"}.items():
        monkeypatch.setenv(key, value)
    settings = Settings(_env_file=None, database_path=tmp_path / "x.db")
    assert settings.smtp_host == "smtp.gmail.com" and settings.smtp_security == "ssl"
    assert settings.smtp_from == "me@gmail.com"
    assert settings.smtp_password.get_secret_value() == "abcdefghijklmnop"
    assert settings.owner_emails == ["a@x.com", "b@x.com"]


async def test_agent_drafts_only_to_observed_addresses(runtime):
    agent = Agent(runtime, Commands(runtime))
    runtime.gateway = ScriptedGateway(
        {"content": "", "tool_calls": [call("find_contacts", website_or_name="elm.example")]},
        {"content": "", "tool_calls": [call("draft_email", to="hello@elm.example", subject="Hello Elm",
                                            body="Hello team, a short note about your website.")]},
    )
    reply = await agent.run("Email elm.example about their site", history=[])
    message = runtime.outbox.get(reply.message_id)
    assert message["recipient"] == "hello@elm.example" and message["status"] == "awaiting_confirmation"
    assert "send it" in reply.text
    assert runtime.gateway.calls[0]["require_tool"] is True


async def test_agent_never_uses_a_guessed_address(runtime):
    agent = Agent(runtime, Commands(runtime))
    runtime.gateway = ScriptedGateway(
        {"content": "", "tool_calls": [call("draft_email", to="info@guess.example", subject="Hello there",
                                            body="Hello team, a short note about your website.")]},
    )
    reply = await agent.run("Email guess.example", history=[])
    message = runtime.outbox.get(reply.message_id)
    assert message["recipient"] == "" and message["status"] == "needs_recipient"


async def test_owner_email_tool_requires_an_owner_request(runtime):
    agent = Agent(runtime, Commands(runtime))
    runtime.gateway = ScriptedGateway(
        {"content": "", "tool_calls": [call("email_owner", subject="Report", body="Details")]},
        {"content": "Here are the contact details.", "tool_calls": []},
    )
    reply = await agent.run("Find the contact details for elm.example", history=[])
    assert reply.text == "Here are the contact details."
    assert runtime.outbox.list() == []


async def test_outbox_send_respects_state_and_limits(runtime, monkeypatch):
    sent = []
    monkeypatch.setattr(runtime.outreach, "deliver_message", lambda preview: sent.append(preview))
    draft = runtime.outbox.draft("hello@elm.example", "Subject line", "Body text that is long enough.")
    result = await runtime.outbox.send(draft["id"])
    assert result["status"] == "sent" and sent[0]["recipient"] == "hello@elm.example"
    with pytest.raises(NovaError):
        await runtime.outbox.send(draft["id"])
    unaddressed = runtime.outbox.draft("", "Subject line", "Body text that is long enough.")
    with pytest.raises(NovaError):
        await runtime.outbox.send(unaddressed["id"])
    fixed = runtime.outbox.edit(unaddressed["id"], "Subject line", "Body text that is long enough.", "b@elm.example")
    assert fixed["status"] == "awaiting_confirmation"


async def test_spoken_confirmation_sends_only_after_an_explicit_prompt(runtime, monkeypatch):
    monkeypatch.setattr(runtime.outreach, "deliver_message", lambda preview: None)
    session = Session(SimpleNamespace(), runtime)
    draft = runtime.outbox.draft("hello@elm.example", "Subject line", "Body text that is long enough.")
    session.pending_email = draft["id"]
    session.remember("ask", "Something unrelated?")
    assert await session.confirm_email("yes") is None
    session.remember("email them", "I drafted an email. Say send it to send.")
    assert "Sent" in await session.confirm_email("yes, send it")
    assert runtime.outbox.get(draft["id"])["status"] == "sent"


def test_confirmation_phrases():
    assert all(CONFIRM_SEND.fullmatch(text) for text in ("send it", "yes send it", "go ahead", "confirm"))
    assert all(DECLINE_SEND.fullmatch(text) for text in ("no", "don't send", "discard it"))
    assert not CONFIRM_SEND.fullmatch("send it to someone@else.com")
    assert needs_tool("search the latest news") and not needs_tool("hi nova, how are you?")


def test_generated_site_parsing_moves_inline_styles_and_strips_scripts():
    files = parse_site("```html\n<html><head><style>body{color:red}</style></head><body><script>x()</script></body></html>\n```"
                       "\n```css\nh1{font-size:2rem}\n```")
    assert "<style" not in files["index.html"] and "<script" not in files["index.html"]
    assert "body{color:red}" in files["style.css"] and 'href="style.css"' in files["index.html"]


def test_site_score_penalizes_overflow_and_unlabelled_forms():
    base = {"overflow_px": 0, "h1_count": 1, "landmarks": 4, "has_form": True, "fields": 2, "labelled_fields": 2,
            "small_targets": 0, "css_rules": 80, "sections": 4, "description": True, "viewport": True, "lang": "en",
            "errors": [], "blocked": [], "axe": []}
    assert score({"profiles": {"desktop": base, "mobile": base}})["score"] == 100
    bad = {**base, "overflow_px": 40, "labelled_fields": 1}
    result = score({"profiles": {"desktop": bad, "mobile": bad}})
    assert result["score"] == 77 and len(result["issues"]) == 2


def test_introduction_draft_handles_a_site_with_no_findings():
    from nova.business import Business

    subject, body = Business.compose({"business": "Regal Muse", "source": "https://regalmuse.example/", "observations": [],
                                      "scope": [], "proposed_price_inr": 7200, "effort_hours": 6}, "introduction")
    assert "Regal Muse" in subject and "Hello Regal Muse team" in body



async def test_small_talk_skips_tools_and_uses_the_fast_model(runtime):
    agent = Agent(runtime, Commands(runtime))
    runtime.gateway = ScriptedGateway({"content": "All systems nominal.", "tool_calls": []})
    reply = await agent.run("hey nova, how are you?", history=[])
    assert reply.text == "All systems nominal."
    assert runtime.gateway.calls == [{"tools": False, "require_tool": False, "fast": True,
                                      "system": runtime.gateway.calls[0]["system"]}]
    assert reply.metrics["calls"] == 1 and reply.metrics["tokens"] == 100


async def test_read_only_tools_run_concurrently(runtime):
    import asyncio
    import time as clock

    active = {"now": 0, "peak": 0}

    class SlowResearch(FakeResearch):
        async def web_search(self, query, limit=6):
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
            await asyncio.sleep(0.05)
            active["now"] -= 1
            return {"query": query, "results": [{"title": query, "url": "https://x.example/", "snippet": ""}]}

    runtime.research = SlowResearch()
    agent = Agent(runtime, Commands(runtime))
    runtime.gateway = ScriptedGateway(
        {"content": "", "tool_calls": [call("web_search", query="alpha labs"), call("web_search", query="beta labs"), call("web_search", query="gamma labs")]},
        {"content": "Done.", "tool_calls": []},
    )
    started = clock.perf_counter()
    reply = await agent.run("search the web for a, b and c", history=[])
    assert reply.text == "Done." and active["peak"] == 3
    assert clock.perf_counter() - started < 0.14


async def test_prompt_sections_are_conditional(runtime):
    agent = Agent(runtime, Commands(runtime))
    plain = agent.system_prompt(None, None, "summarise the latest LLM evaluation research")
    outreach = agent.system_prompt(None, None, "email elm.example about their website")
    assert "Signature:" not in plain and "Signature:" in outreach
    assert len(plain) < len(outreach)


async def test_agent_loads_a_skill_playbook(runtime):
    from nova.skills import SkillRegistry

    runtime.skills = SkillRegistry(runtime.store.db)
    agent = Agent(runtime, Commands(runtime))
    runtime.gateway = ScriptedGateway(
        {"content": "", "tool_calls": [call("load_skill", skill_id="copy-editing")]},
        {"content": "Edited.", "tool_calls": []},
    )
    reply = await agent.run("polish this paragraph for me", history=[])
    assert reply.metrics["skills"] == ["copy-editing"] and reply.text == "Edited."
    assert runtime.skills.observed(None) is not None


def test_history_compaction_keeps_facts():
    from nova.agent import compact_history

    long = "x" * 2000 + "\n[facts: Contacts for https://elm.example/: {\"phones\": [\"919\"]}]"
    trimmed = compact_history([{"role": "assistant", "content": long}])[0]["content"]
    assert len(trimmed) < 800 and "Contacts for https://elm.example/" in trimmed


async def test_tool_calls_are_ledgered_with_real_fetch_evidence(runtime):
    from nova import provenance

    class TracedResearch(FakeResearch):
        async def web_search(self, query, limit=6):
            provenance.record_fetch("https://api.search.brave.com/?q=" + query, 200, b"payload", "Brave Search")
            return {"query": query, "results": [{"title": "Elm", "url": "https://elm.example/", "snippet": "Elm studio"}]}

    runtime.research = TracedResearch()
    agent = Agent(runtime, Commands(runtime))
    runtime.gateway = ScriptedGateway(
        {"content": "", "tool_calls": [call("web_search", query="elm studio hyderabad")]},
        {"content": "Elm Studio is listed at elm.example, and ghost.example says otherwise.", "tool_calls": []},
    )
    reply = await agent.run("search the web for elm studio", history=[])
    row = runtime.store.db.execute("SELECT * FROM tool_calls WHERE turn=?", (reply.turn,)).fetchone()
    fetches = json.loads(row["fetches"])
    assert row["tool"] == "web_search" and row["status"] == "done"
    assert fetches[0]["status"] == 200 and fetches[0]["provider"] == "Brave Search" and len(fetches[0]["sha"]) == 12
    assert reply.verification["unverified_sites"] == ["ghost.example"]
    assert "couldn't verify ghost.example" in reply.text
