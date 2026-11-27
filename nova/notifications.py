import hashlib
import re
import time

import httpx

from .domain import NovaError
from .store import encoded

SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_deliveries (
 event_id INTEGER PRIMARY KEY REFERENCES events(id), digest TEXT NOT NULL,
 status TEXT NOT NULL, attempted_at REAL NOT NULL
);
"""


class TelegramDelivery:
    def __init__(self, settings, store, transport=None):
        self.settings = settings
        self.store = store
        self.transport = transport
        store.db.executescript(SCHEMA)

    def credentials(self):
        token = self.settings.telegram_bot_token.get_secret_value()
        recipient = self.settings.telegram_owner_chat_id
        if not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{20,100}", token) or not re.fullmatch(r"[1-9]\d{4,15}", recipient):
            raise NovaError("telegram_config", "Configure a Telegram bot token and a private owner chat ID.")
        return token, recipient

    def preview(self, event_id):
        token, target = self.credentials()
        row = self.store.db.execute(
            "SELECT message,task_id FROM events WHERE kind='notification' AND id=?", (event_id,),
        ).fetchone()
        if row is None:
            raise NovaError("notification_missing", "That notification could not be found.")
        text = f"NOVA · {row['message'][:500]}"
        digest = hashlib.sha256(encoded([event_id, target, text, hashlib.sha256(token.encode()).hexdigest()]).encode()).hexdigest()
        previous = self.store.db.execute("SELECT status FROM telegram_deliveries WHERE event_id=?", (event_id,)).fetchone()
        return {"text": text, "recipient": "Private owner Telegram chat ending " + target[-4:], "digest": digest,
                "status": previous["status"] if previous else "pending"}

    async def deliver(self, event_id, digest):
        preview = self.preview(event_id)
        if preview["digest"] != digest:
            raise NovaError("review_changed", "Review this notification for the configured destination before sending.")
        if self.store.stopped():
            raise NovaError("stopped", "Emergency stop is active.")
        token, recipient = self.credentials()
        with self.store.db:
            inserted = self.store.db.execute(
                "INSERT OR IGNORE INTO telegram_deliveries VALUES(?,?,?,?)", (event_id, digest, "attempted", time.time()),
            )
            if not inserted.rowcount:
                raise NovaError("duplicate_delivery", "A delivery attempt already exists for this notification.")
            self.store.event("notification_delivery", "Owner authorized Telegram delivery", event_id=event_id)
        state = "unconfirmed"
        try:
            async with httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=10) as client:
                response = await client.post("https://api.telegram.org/bot" + token + "/sendMessage",
                                             json={"chat_id": recipient, "text": preview["text"], "protect_content": True})
                result = response.json()
            if response.is_success and result.get("ok") is True:
                state = "sent"
            elif response.status_code < 500 and result.get("ok") is False:
                state = "rejected"
        except (httpx.HTTPError, AttributeError, ValueError):
            pass
        finally:
            with self.store.db:
                self.store.db.execute("UPDATE telegram_deliveries SET status=? WHERE event_id=?", (state, event_id))
                self.store.event("notification_delivery", "Telegram delivery status recorded", event_id=event_id, status=state)
        return {"status": state}
