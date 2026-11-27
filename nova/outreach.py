import asyncio
import base64
from pathlib import Path
import hashlib
import re
import smtplib
import ssl
import time
from contextlib import suppress
from email import policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape
from urllib.parse import urlsplit

from .domain import NovaError
from .store import encoded

ADDRESS = re.compile(r"[A-Za-z0-9][A-Za-z0-9.!#$%&'*+/=?^_{}|~-]{0,63}@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", re.ASCII)


def valid_address(value):
    return bool(ADDRESS.fullmatch(value) and ".." not in value and len(value) <= 254)


URL_TEXT = re.compile(r"https?://[^\s<>()]+")


def _inline(text):
    parts = []
    offset = 0
    for match in URL_TEXT.finditer(text):
        parts.append(escape(text[offset:match.start()]))
        url = match.group().rstrip(".,;:!?")
        safe = escape(url, quote=True)
        parts.append(f'<a href="{safe}" style="color:#254ca3;text-decoration:underline">{safe}</a>')
        parts.append(escape(match.group()[len(url):]))
        offset = match.end()
    parts.append(escape(text[offset:]))
    return "".join(parts)


LETTER_WAVE = Path(__file__).with_name("static") / "letter-wave.gif"
NOVA_LOCKUP = Path(__file__).with_name("static") / "brand" / "lockup-light.png"


def uses_nova_brand(settings):
    """The Nova lockup appears when the sender's business is Nova itself; other businesses keep their own name."""
    name = (settings.business_name or settings.owner_name or "Nova").strip().casefold()
    return name in {"nova", settings.agent_name.strip().casefold()} and NOVA_LOCKUP.is_file()


def render_email_html(subject, body, settings, *, inline_cid=None, logo_cid=None):
    """Render a complete, readable email with inline styles and no remote assets."""
    image_src = f"cid:{inline_cid}" if inline_cid else "data:image/gif;base64," + base64.b64encode(LETTER_WAVE.read_bytes()).decode("ascii")
    if uses_nova_brand(settings):
        logo_src = f"cid:{logo_cid}" if logo_cid else "data:image/png;base64," + base64.b64encode(NOVA_LOCKUP.read_bytes()).decode("ascii")
        masthead = (f'<img src="{logo_src}" width="118" height="40" alt="Nova" '
                    'style="display:block;width:118px;height:40px;border:0;outline:none">')
    else:
        masthead = None
    color = settings.brand_color
    name = settings.business_name or settings.owner_name or "NOVA"
    brand = escape(name)
    masthead = masthead or brand
    heading = escape(subject)
    blocks = [block.strip() for block in re.split(r"\n\s*\n", body.replace("\r\n", "\n")) if block.strip()]
    preheader = escape(" ".join(blocks[0].split())[:140] if blocks else subject)
    paragraphs = "".join(
        f'<p style="margin:0 0 18px;font-size:16px;line-height:1.65;overflow-wrap:anywhere">'
        f'{_inline(block).replace(chr(10), "<br>")}</p>' for block in blocks
    )
    footer = f"{brand} &middot; Reply to this email if you’d prefer future emails to stop."
    signature = settings.signature
    contact = ""
    if signature != "Best regards":
        if blocks and blocks[-1] == signature:
            paragraphs = paragraphs.rsplit('<p style=', 1)[0]
        lines = signature.splitlines()
        details = "<br>".join(_inline(line) for line in lines[1:])
        contact = f'<div style="border-left:3px solid {color};padding-left:16px;margin:24px 0"><strong>{escape(lines[0])}</strong><br>{details}</div>'
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{heading}</title></head>
<body style="margin:0;padding:0;background:#e6e3d8">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#e6e3d8">
<tr><td align="center" style="padding:26px 12px">
<!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0"><tr><td><![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;font-family:Arial,Helvetica,sans-serif">
<tr><td bgcolor="#183c33" style="padding:21px 30px;color:#fff7df;font:bold 20px Georgia,serif;letter-spacing:1px">{masthead}</td></tr>
<tr><td bgcolor="#183c33"><img src="{image_src}" width="600" alt="" style="display:block;width:100%;max-width:600px;height:auto;border:0"></td></tr>
<tr><td bgcolor="#faf6e9" style="padding:34px 30px 26px;border-bottom:1px solid #d6d1bf">
<div style="width:42px;height:4px;background:{color};line-height:4px">&nbsp;</div>
<h1 style="margin:18px 0 0;font:normal 38px/1.12 Georgia,serif;color:#183c33;overflow-wrap:anywhere">{heading}</h1>
</td></tr>
<tr><td bgcolor="#fffdf6" style="padding:28px 30px 12px;color:#283830">{paragraphs}{contact}</td></tr>
<tr><td bgcolor="#eae7da" style="padding:15px 30px;color:#4c574d;font-size:12px;line-height:1.6">{footer}</td></tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr></table>
</body></html>"""


class Outreach:
    def __init__(self, store, business, settings):
        self.store, self.business, self.settings = store, business, settings
        store.db.execute("""
            CREATE TABLE IF NOT EXISTS email_delivery (
                digest TEXT PRIMARY KEY, draft_id TEXT NOT NULL REFERENCES business_drafts(id),
                recipient TEXT NOT NULL, state TEXT NOT NULL, updated REAL NOT NULL
            )
        """)
        store.db.execute("CREATE TABLE IF NOT EXISTS contact_requests (task_id TEXT PRIMARY KEY REFERENCES tasks(id))")
        store.db.execute("UPDATE email_delivery SET state='unconfirmed' WHERE state='sending'")
        store.db.commit()
        self.send_lock = asyncio.Lock()

    def request_contact(self, task_id):
        with self.store.db:
            if self.store.db.execute("INSERT OR IGNORE INTO contact_requests VALUES (?)", (task_id,)).rowcount:
                self.store.event("outreach", "Owner requested a draft after research", task_id)

    def contact_requested(self, task_id):
        return self.store.db.execute("SELECT 1 FROM contact_requests WHERE task_id=?", (task_id,)).fetchone() is not None

    def channels(self, task_id):
        checkpoints = self.store.checkpoints(task_id)
        proposal = checkpoints.get("proposal", {}).get("draft")
        sources = [item for item in checkpoints.get("report", {}).get("sources", []) if "score" in item]
        url = proposal["source"] if proposal else (sources[0]["url"] if len(sources) == 1 else None)
        for key, result in self.store.checkpoints(task_id).items():
            if key.startswith("audit_") and url and result.get("url") == url:
                return {"source": url,
                        "emails": [item for item in result.get("public_emails", []) if valid_address(item)],
                        "contact_page": result.get("contact_page")}
        return {"source": url, "emails": [], "contact_page": None}

    def configured(self):
        settings = self.settings
        return bool(settings.smtp_host and valid_address(settings.smtp_from)
                    and bool(settings.smtp_username) == bool(settings.smtp_password.get_secret_value()))

    def preview(self, draft_id, recipient):
        if not valid_address(recipient):
            raise NovaError("recipient", "Enter one valid email address.")
        draft = self.business.draft(draft_id)
        if draft["status"] == "rejected":
            raise NovaError("review_changed", "Edit the rejected draft before preparing delivery.")
        digest = hashlib.sha256(encoded([draft_id, draft["digest"], recipient, self.settings.smtp_from]).encode()).hexdigest()
        prior = self.store.db.execute("SELECT state FROM email_delivery WHERE digest=?", (digest,)).fetchone()
        return {"draft_id": draft_id, "digest": digest, "recipient": recipient, "from": self.settings.smtp_from,
                "subject": draft["subject"], "body": draft["body"], "configured": self.configured(),
                "state": prior["state"] if prior else "ready"}

    def deliver_message(self, preview):
        settings = self.settings
        message = EmailMessage(policy=policy.SMTP)
        display = (settings.business_name or settings.owner_name or "").strip()
        message["From"] = formataddr((display, preview["from"])) if display else preview["from"]
        message["To"] = preview["recipient"]
        message["Subject"] = preview["subject"]
        message["Date"] = formatdate(localtime=True)
        if settings.owner_emails and settings.owner_emails[0] != preview["from"] and preview["recipient"] not in settings.owner_emails:
            message["Reply-To"] = settings.owner_emails[0]
        message["Message-ID"] = make_msgid(domain=preview["from"].split("@")[-1])
        message.set_content(preview["body"])
        if preview.get("html", True):
            cid, logo = make_msgid(), make_msgid()
            branded = uses_nova_brand(settings)
            html = render_email_html(preview["subject"], preview["body"], settings, inline_cid=cid[1:-1],
                                     logo_cid=logo[1:-1] if branded else None)
            message.add_alternative(html, subtype="html")
            message.get_payload()[-1].add_related(LETTER_WAVE.read_bytes(), maintype="image", subtype="gif", cid=cid, disposition="inline")
            if branded:
                message.get_payload()[-1].add_related(NOVA_LOCKUP.read_bytes(), maintype="image", subtype="png", cid=logo,
                                                      disposition="inline")
        tls = ssl.create_default_context()
        if settings.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=tls)
        else:
            smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
        try:
            if settings.smtp_security == "starttls":
                smtp.starttls(context=tls)
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message, from_addr=preview["from"], to_addrs=[preview["recipient"]])
        finally:
            # A later QUIT or socket failure must not change an accepted DATA result.
            with suppress(OSError):
                smtp.close()

    async def send(self, draft_id, recipient, digest):
        async with self.send_lock:
            preview = self.preview(draft_id, recipient)
            if preview["digest"] != digest:
                raise NovaError("review_changed", "The recipient or draft changed. Review the current message.")
            if self.store.stopped():
                raise NovaError("stopped", "Emergency stop is active.")
            if not preview["configured"]:
                raise NovaError("smtp_config", "Configure the sender’s SMTP settings before sending.")
            if preview["state"] != "ready":
                raise NovaError("duplicate_delivery", "An attempt for this exact message already exists.")
            draft = self.business.draft(draft_id)
            task_id = draft["task_id"]
            with self.store.db:
                self.store.db.execute("INSERT INTO email_delivery VALUES(?,?,?,?,?)",
                                      (digest, draft_id, recipient, "sending", time.time()))
                self.store.event("outreach", "Owner authorized one email delivery", task_id)
            state = "unconfirmed"
            try:
                await asyncio.to_thread(self.deliver_message, preview)
                state = "accepted"
            except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError,
                    smtplib.SMTPAuthenticationError, smtplib.SMTPNotSupportedError, ValueError):
                state = "rejected"
            except (OSError, smtplib.SMTPException):
                pass
            finally:
                with self.store.db:
                    self.store.db.execute("UPDATE email_delivery SET state=?,updated=? WHERE digest=?", (state, time.time(), digest))
                    self.store.event("outreach", "Email delivery status updated", task_id, state=state)
            return {"state": state}


OUTBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
 id TEXT PRIMARY KEY, recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
 business TEXT NOT NULL DEFAULT '', channel TEXT NOT NULL DEFAULT 'email', purpose TEXT NOT NULL DEFAULT 'outreach',
 status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, error TEXT,
 source TEXT NOT NULL DEFAULT '', task_id TEXT
);
CREATE INDEX IF NOT EXISTS outbox_updated ON outbox(updated);
"""


class Outbox:
    """Agent-composed messages. Business outreach waits for an explicit owner confirmation;
    reports addressed to the owner's own ADMIN_EMAILS may be sent directly."""

    def __init__(self, store, outreach, settings):
        self.store, self.outreach, self.settings = store, outreach, settings
        store.db.executescript(OUTBOX_SCHEMA)
        store.db.execute("UPDATE outbox SET status='unconfirmed' WHERE status='sending'")
        store.db.commit()

    def view(self, row):
        return dict(row) if row else None

    def get(self, message_id):
        row = self.store.db.execute("SELECT * FROM outbox WHERE id=?", (message_id,)).fetchone()
        if row is None:
            raise NovaError("message_missing", "That outbox message does not exist.")
        return self.view(row)

    def list(self, limit=50):
        return [self.view(row) for row in self.store.db.execute(
            "SELECT * FROM outbox ORDER BY updated DESC LIMIT ?", (limit,))]

    def draft(self, recipient, subject, body, *, business="", purpose="outreach", source="", task_id=None):
        recipient = (recipient or "").strip().strip("<>").lower()
        if recipient and not valid_address(recipient):
            raise NovaError("recipient", f"“{recipient}” is not a valid email address.")
        subject = re.sub(r"[\r\n\x00]+", " ", subject).strip()[:160]
        body = body.replace("\r\n", "\n").strip()[:8000]
        if len(subject) < 3 or len(body) < 12:
            raise NovaError("draft_short", "The email needs a subject and a message body.")
        now = time.time()
        key = hashlib.sha256(encoded([recipient, subject, body, now]).encode()).hexdigest()[:12]
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO outbox(id,recipient,subject,body,business,purpose,status,created,updated,source,task_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (key, recipient, subject, body, business[:140], purpose,
                 "awaiting_confirmation" if recipient else "needs_recipient", now, now, source[:500], task_id))
            self.store.event("outreach", f"Email to {recipient} is waiting for your confirmation" if recipient else
                             f"Message for {business or 'a business'} saved; it needs a recipient", task_id,
                             message_id=key, business=business[:140])
        return self.get(key)

    def edit(self, message_id, subject, body, recipient=None):
        message = self.get(message_id)
        if message["status"] not in {"awaiting_confirmation", "needs_recipient", "discarded", "failed", "unconfirmed"}:
            raise NovaError("message_state", "Only unsent messages can be edited.")
        recipient = (message["recipient"] if recipient is None else recipient).strip().lower()
        if recipient and not valid_address(recipient):
            raise NovaError("recipient", f"“{recipient}” is not a valid email address.")
        subject = re.sub(r"[\r\n\x00]+", " ", subject).strip()[:160]
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET recipient=?,subject=?,body=?,status=?,error=NULL,updated=? WHERE id=?",
                                  (recipient, subject, body.strip()[:8000],
                                   "awaiting_confirmation" if recipient else "needs_recipient", time.time(), message_id))
        return self.get(message_id)

    def discard(self, message_id):
        message = self.get(message_id)
        if message["status"] in {"sent", "sending"}:
            raise NovaError("message_state", "That message was already sent.")
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET status='discarded',updated=? WHERE id=?", (time.time(), message_id))
            self.store.event("outreach", "Owner discarded an outbox email", message["task_id"], message_id=message_id)
        return self.get(message_id)

    def pending(self):
        row = self.store.db.execute(
            "SELECT * FROM outbox WHERE status='awaiting_confirmation' ORDER BY updated DESC LIMIT 1").fetchone()
        return self.view(row)

    def sent_last_hour(self):
        return self.store.db.execute("SELECT COUNT(*) FROM outbox WHERE status IN ('sent','sending') AND updated>?",
                                     (time.time() - 3600,)).fetchone()[0]

    async def send(self, message_id, *, owner_report=False):
        async with self.outreach.send_lock:
            message = self.get(message_id)
            if self.store.stopped():
                raise NovaError("stopped", "Emergency stop is active.")
            if not self.outreach.configured():
                raise NovaError("smtp_config", "Email isn't configured. Set EMAIL_HOST, EMAIL_USER and EMAIL_PASS in .env and restart NOVA.")
            if message["status"] == "sent":
                raise NovaError("duplicate_delivery", "That email was already sent.")
            if not message["recipient"]:
                raise NovaError("recipient", "Add a recipient address before sending.")
            if message["status"] not in {"awaiting_confirmation", "failed", "unconfirmed"} and not owner_report:
                raise NovaError("message_state", "That message is not waiting to be sent.")
            if self.sent_last_hour() >= self.settings.max_emails_hour:
                raise NovaError("email_budget", "The hourly email limit has been reached. Try again later.")
            with self.store.db:
                self.store.db.execute("UPDATE outbox SET status='sending',updated=? WHERE id=?", (time.time(), message_id))
            preview = {"from": self.settings.smtp_from, "recipient": message["recipient"],
                       "subject": message["subject"], "body": message["body"]}
            status, error = "unconfirmed", None
            try:
                await asyncio.to_thread(self.outreach.deliver_message, preview)
                status = "sent"
            except smtplib.SMTPAuthenticationError:
                status, error = "failed", "The mail server rejected the login. Check EMAIL_USER and EMAIL_PASS (Gmail needs an app password)."
            except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError,
                    smtplib.SMTPNotSupportedError, ValueError) as exc:
                status, error = "failed", f"The mail server refused the message ({type(exc).__name__})."
            except (OSError, smtplib.SMTPException) as exc:
                error = f"Delivery status is unknown ({type(exc).__name__})."
            finally:
                with self.store.db:
                    self.store.db.execute("UPDATE outbox SET status=?,error=?,updated=? WHERE id=?",
                                          (status, error, time.time(), message_id))
                    label = {"sent": f"Email sent to {message['recipient']}",
                             "failed": f"Email to {message['recipient']} failed"}.get(status, "Email delivery is unconfirmed")
                    self.store.event("notification" if status == "sent" else "outreach", label, message["task_id"],
                                     message_id=message_id, state=status)
            if status != "sent":
                raise NovaError("delivery_failed", error or "The email could not be confirmed as sent.")
            return self.get(message_id)

    async def email_owner(self, subject, body):
        recipients = self.settings.owner_emails
        if not recipients:
            raise NovaError("owner_email", "Add your address to ADMIN_EMAILS in .env so I can email you.")
        message = self.draft(recipients[0], subject, body, business="Owner", purpose="owner_report")
        return await self.send(message["id"], owner_report=True)
