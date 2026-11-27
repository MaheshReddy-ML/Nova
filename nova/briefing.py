"""Spoken status briefings: what happened since the owner last checked in. Deterministic, no model calls."""
import json
import time
from datetime import datetime

KEY = "last_briefing"


def last_briefing(store):
    row = store.db.execute("SELECT value FROM settings WHERE key=?", (KEY,)).fetchone()
    try:
        return float(json.loads(row["value"])) if row else time.time() - 86400
    except (TypeError, ValueError):
        return time.time() - 86400


def mark_briefed(store, when=None):
    with store.db:
        store.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (KEY, json.dumps(when or time.time())))


def greeting(settings, now=None):
    hour = (now or datetime.now()).hour
    part = "Good morning" if 5 <= hour < 12 else "Good afternoon" if hour < 17 else "Good evening" if hour < 22 else "Working late, I see"
    address = (settings.owner_address or settings.owner_name.split(" ")[0] if settings.owner_name else settings.owner_address).strip()
    return f"{part}{', ' + address if address else ''}."


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def join(items):
    items = [item for item in items if item]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def collect(runtime, since):
    db = runtime.store.db
    tasks = runtime.store.tasks()
    done = [task for task in tasks if task["state"] == "completed" and task["updated"] > since]
    failed = [task for task in tasks if task["state"] == "failed" and task["updated"] > since]
    active = [task for task in tasks if task["state"] not in {"completed", "failed", "cancelled", "paused"}]
    outbox = runtime.outbox.list(50)
    sent = [item for item in outbox if item["status"] == "sent" and item["updated"] > since and item["purpose"] != "owner_report"]
    waiting = [item for item in outbox if item["status"] == "awaiting_confirmation"]
    unaddressed = [item for item in outbox if item["status"] == "needs_recipient"]
    approvals = db.execute("SELECT COUNT(*) FROM approvals WHERE state='pending'").fetchone()[0]
    leads = db.execute("SELECT COUNT(DISTINCT l.url) FROM leads l JOIN tasks t ON t.id=l.task_id WHERE l.score>0 AND t.updated>?",
                       (since,)).fetchone()[0]
    ledger = runtime.business.ledger()
    schedules = [entry for entry in runtime.schedules.list() if entry["enabled"]]
    upcoming = min(schedules, key=lambda entry: entry["next_due"], default=None)
    return {"done": done, "failed": failed, "active": active, "sent": sent, "waiting": waiting, "unaddressed": unaddressed,
            "approvals": approvals, "leads": leads, "outstanding": ledger["outstanding_paise"] / 100, "upcoming": upcoming}


def outcome(runtime, task):
    checkpoints = runtime.store.checkpoints(task["id"])
    build = checkpoints.get("build", {})
    proposal = checkpoints.get("proposal", {}).get("draft")
    if proposal:
        quality = f", scoring {round(build['score'])} out of 100" if build.get("builder") == "model" and build.get("score") else ""
        return f"the {proposal['business']} concept site is built and verified{quality}, with a proposal of {proposal['proposed_price_inr']:,} rupees"
    return task["title"].split(": ", 1)[-1]


def briefing(runtime, *, since=None, wake=False):
    settings = runtime.settings
    since = last_briefing(runtime.store) if since is None else since
    data = collect(runtime, since)
    away = time.time() - since
    lines = [greeting(settings)]
    news = []
    if data["done"]:
        lead = "; ".join(outcome(runtime, task) for task in data["done"][:3])
        extra = f", plus {len(data['done']) - 3} more" if len(data["done"]) > 3 else ""
        news.append(f"{plural(len(data['done']), 'mission')} completed: {lead}{extra}.")
    if data["failed"]:
        count = len(data["failed"])
        news.append(f"{plural(count, 'mission')} {'needs' if count == 1 else 'need'} your attention, including "
                    f"{join([task['title'].split(': ', 1)[-1] for task in data['failed'][:2]])}.")
    if data["sent"]:
        news.append(f"I sent {plural(len(data['sent']), 'email')}, to {join([item['recipient'] for item in data['sent'][:3]])}.")
    if data["leads"]:
        news.append(f"I qualified {plural(data['leads'], 'new lead')}.")
    pending = []
    if data["active"]:
        pending.append(f"{plural(len(data['active']), 'mission')} still running")
    if data["approvals"]:
        pending.append(f"{plural(data['approvals'], 'proposal')} awaiting your review")
    if data["unaddressed"]:
        pending.append(f"{plural(len(data['unaddressed']), 'drafted message')} that need a recipient")
    if data["outstanding"] > 0:
        pending.append(f"{data['outstanding']:,.0f} rupees outstanding in invoices")
    if not news and not pending and not data["waiting"]:
        lines.append("All quiet since we last spoke. No new results, and nothing is waiting on you." if away > 120
                     else "Everything is up to date.")
    else:
        if news:
            lines.append(("Since we last spoke, " if away > 120 else "") + " ".join(news))
        if pending:
            lines.append(f"Currently there {'is' if pending[0].startswith('1 ') else 'are'} {join(pending)}.")
    if data["upcoming"]:
        minutes = max(0, round((data["upcoming"]["next_due"] - time.time()) / 60))
        when = f"in {minutes} minutes" if minutes < 120 else f"in about {round(minutes / 60)} hours"
        lines.append(f"Next scheduled: {data['upcoming']['name']}, {when}.")
    if data["waiting"]:
        first = data["waiting"][0]
        lines.append(f"Your email to {first['recipient']} is ready. Say send it when you'd like it to go.")
    else:
        lines.append("What shall we work on?" if wake else "")
    return " ".join(line for line in lines if line), data


ACKS = ("Yes?", "At your service.", "I'm listening.", "Go ahead.")


def acknowledgement(count):
    return ACKS[count % len(ACKS)]
