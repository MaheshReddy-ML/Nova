"""Provenance: proof that tool calls really ran and data really came from where NOVA says.

Every outbound fetch made while a tool runs is captured (URL, HTTP status, bytes, SHA-256 prefix, time) through a
context variable, stored with the tool call in the `tool_calls` ledger, and used to check the final answer: any website
named in the answer must have been fetched or returned by a tool in the same turn.
"""
import contextvars
import hashlib
import json
import re
import time

FETCHES: contextvars.ContextVar[list | None] = contextvars.ContextVar("nova_fetches", default=None)
SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_calls (
 id INTEGER PRIMARY KEY AUTOINCREMENT, turn TEXT NOT NULL, tool TEXT NOT NULL, args TEXT NOT NULL,
 started REAL NOT NULL, ms INTEGER NOT NULL, status TEXT NOT NULL, fetches TEXT NOT NULL,
 result_sha TEXT NOT NULL, result_preview TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tool_calls_turn ON tool_calls(turn);
"""
TLDS = ("com|in|org|net|io|ai|co|edu|gov|studio|dev|app|info|uk|us|de|ca|au|me|biz|xyz|site|online|store|tech|cafe|shop|"
        "design|agency|space|life|world|club|blog|live|art|health|fit|travel|org\\.in|co\\.in|example")
DOMAIN = re.compile(rf"\b((?:[a-z0-9-]+\.)+(?:{TLDS}))(?![a-z0-9-])", re.I)


def record_fetch(url, status, data=b"", provider=""):
    """Called by network code; a no-op outside a tool call."""
    log = FETCHES.get()
    if log is None:
        return
    payload = data if isinstance(data, bytes) else str(data).encode("utf-8", "replace")
    log.append({"url": str(url)[:400], "status": status, "bytes": len(payload),
                "sha": hashlib.sha256(payload).hexdigest()[:12], "provider": provider, "at": round(time.time(), 3)})


def begin():
    """Start capturing fetches for the current tool call; returns the token and the list."""
    log = []
    return FETCHES.set(log), log


def end(token):
    FETCHES.reset(token)


def ensure(db):
    db.executescript(SCHEMA)


def store(db, turn, tool, args, started, ms, status, fetches, result):
    text = json.dumps(result, ensure_ascii=False, default=str)
    with db:
        db.execute("INSERT INTO tool_calls(turn,tool,args,started,ms,status,fetches,result_sha,result_preview) VALUES(?,?,?,?,?,?,?,?,?)",
                   (turn, tool, json.dumps(args, ensure_ascii=False, default=str)[:2000], started, ms, status,
                    json.dumps(fetches), hashlib.sha256(text.encode()).hexdigest()[:16], text[:600]))


def domains(text):
    return {match.lower().removeprefix("www.") for match in DOMAIN.findall(text or "")}


def verify_answer(answer, evidence_texts, fetches):
    """Websites named in the answer must appear in fetched URLs or tool results from this turn."""
    seen = set()
    for fetch in fetches:
        seen |= domains(fetch["url"])
    for text in evidence_texts:
        seen |= domains(text)
    named = domains(answer)
    unverified = sorted(name for name in named if not any(name == item or name.endswith("." + item) or item.endswith("." + name)
                                                         for item in seen))
    return {"named_sites": sorted(named), "unverified_sites": unverified,
            "fetched": len(fetches), "ok_fetches": sum(1 for fetch in fetches if fetch_ok(fetch.get("status")))}


def fetch_ok(status):
    """HTTP 2xx, or a cache hit (status "cache") of content that was fetched successfully earlier."""
    if status == "cache":
        return True
    try:
        return 200 <= int(status or 0) < 300
    except (TypeError, ValueError):
        return False
