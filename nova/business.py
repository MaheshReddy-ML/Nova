import hashlib
import json
import re
import time
from datetime import date
from html import escape
from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator

from .domain import NovaError, StrictModel
from .store import encoded

DRAFT_KINDS = Literal["introduction", "follow_up", "delivery", "progress", "quotation", "maintenance",
                      "reminder", "support", "apology", "negotiation", "meeting_summary"]
CRM_STAGES = (
    "researched", "qualified", "awaiting_approval", "proposal_reviewed", "contacted", "negotiating",
    "won", "lost", "delivered", "archived",
)
BUSINESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS business_drafts (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), kind TEXT NOT NULL,
 business TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, facts TEXT NOT NULL,
 status TEXT NOT NULL, digest TEXT NOT NULL, origin TEXT NOT NULL, updated REAL NOT NULL,
 UNIQUE(task_id, kind)
);
CREATE TABLE IF NOT EXISTS ledger (
 id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id), kind TEXT NOT NULL,
 reference TEXT NOT NULL, amount_paise INTEGER NOT NULL CHECK(amount_paise > 0),
 occurred_on TEXT NOT NULL, invoice_reference TEXT, note TEXT NOT NULL,
 UNIQUE(kind, reference)
);
CREATE TABLE IF NOT EXISTS outcome_feedback (
 task_id TEXT PRIMARY KEY REFERENCES tasks(id), rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
 note TEXT NOT NULL, updated REAL NOT NULL
);
"""


class DraftInput(StrictModel):
    task_id: str = Field(pattern=r"^[a-f0-9]{12}$")
    kind: DRAFT_KINDS = "introduction"


class DraftEdit(StrictModel):
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=12, max_length=8000)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("subject")
    @classmethod
    def single_line(cls, value):
        if re.search(r"[\r\n\x00]", value):
            raise ValueError("The subject must be one line.")
        return value


class LeadChange(StrictModel):
    url: str = Field(max_length=500)
    stage: Literal["qualified", "contacted", "negotiating", "won", "lost", "delivered", "archived"]
    note: str = Field(default="", max_length=600)


class EntryInput(StrictModel):
    task_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{12}$")
    kind: Literal["invoice", "payment", "expense"]
    reference: str = Field(min_length=2, max_length=90)
    amount_paise: int = Field(gt=0, le=1_000_000_000, strict=True)
    occurred_on: date
    invoice_reference: str | None = Field(default=None, min_length=2, max_length=90)
    note: str = Field(default="", max_length=500)


class FeedbackInput(StrictModel):
    rating: int = Field(ge=1, le=5, strict=True)
    note: str = Field(default="", max_length=800)


class Business:
    def __init__(self, store):
        self.store = store
        self.db = store.db
        self.db.executescript(BUSINESS_SCHEMA)

    @staticmethod
    def compose(proposal, kind, invoice=None):
        business = proposal["business"]
        if proposal.get("research_only"):
            return (f"Website question for {business}"[:160],
                    f"Hello {business} team,\n\nI reviewed your public website for my owner. "
                    "Who would be the best person to speak with about the site?\n\nNOVA\nAI business assistant")
        changes = proposal.get("scope", [])[:2]
        detail = " ".join(changes)
        quote = f"INR {proposal['proposed_price_inr']:,} based on {proposal['effort_hours']} hours"
        subjects = {
            "introduction": f"A website improvement idea for {business}",
            "follow_up": f"Website improvement concept for {business}",
            "delivery": f"Website concept and review notes for {business}",
            "progress": f"Website concept progress for {business}",
            "quotation": f"Draft website project estimate for {business}",
            "maintenance": f"Website maintenance discussion for {business}",
            "reminder": f"Invoice {invoice['reference'] if invoice else ''} for {business}",
            "support": f"Website support questions for {business}",
            "apology": f"Website project feedback for {business}",
            "negotiation": f"Website project scope and estimate for {business}",
            "meeting_summary": f"Website discussion notes for {business}",
        }
        opened = "I reviewed your public website and prepared a private concept for a small set of improvements."
        if kind == "introduction":
            observation = (proposal.get("observations") or ["There are opportunities to make the page easier to act on."])[0]
            paragraphs = [opened, observation, f"The concept shows how we could {changes[0][0].lower() + changes[0][1:]}" if changes else None,
                          "If that would be helpful, may I share the concept and a short scope for your review?"]
        elif kind == "follow_up":
            paragraphs = [opened, detail, "If this is a current priority, would a short walkthrough be useful?"]
        elif kind in {"delivery", "progress"}:
            verified = ", ".join(proposal.get("verification", []))
            paragraphs = ["The private website concept is ready for review.", detail,
                          f"The recorded preview checks covered {verified}." if verified else None,
                          "Please confirm which changes you would like included in the next draft."]
        elif kind in {"quotation", "negotiation"}:
            paragraphs = ["I put together an initial scope for the website work.", detail,
                          f"The working estimate is {quote}. It is subject to confirming the scope and delivery requirements.",
                          "Could your team review the scope and flag anything missing before we firm up the estimate?"]
        elif kind == "maintenance":
            paragraphs = [opened, "If you are considering ongoing support, we can discuss who owns content updates, how often changes are needed, and how issues should be reported.",
                          "Would you like to outline the updates you expect over the next few months?"]
        elif kind == "reminder":
            if invoice is None:
                raise NovaError("invoice_missing", "This project has no recorded invoice with an outstanding balance.")
            balance = f"INR {invoice['balance_paise'] // 100:,}.{invoice['balance_paise'] % 100:02}"
            paragraphs = [
                f"Our local records show an outstanding balance of {balance} on invoice {invoice['reference']}.",
                "Could you confirm whether the invoice reached the right person? If your records differ, please let us know so we can reconcile them.",
            ]
        elif kind == "support":
            paragraphs = ["Could you share the page address, what you expected to happen, and the device or browser you used?",
                          "That will help us narrow down the issue and give you a more specific answer."]
        elif kind == "apology":
            paragraphs = ["I’m sorry the experience raised concerns. Could you point us to the page or interaction that caused the issue?",
                          "We can use that information to investigate and follow up with what we find."]
        else:
            paragraphs = ["I prepared the notes below from the public-site review, for discussion.", detail,
                          "Please confirm the priorities and any decisions you would like recorded."]
        return subjects[kind][:160], "\n\n".join(
            [f"Hello {business} team,", *(paragraph for paragraph in paragraphs if paragraph), "NOVA\nAI business assistant"]
        )

    def proposal_for(self, task_id):
        task = self.store.get(task_id)
        draft = self.store.checkpoints(task_id).get("proposal", {}).get("draft")
        if task["state"] != "completed" or not draft:
            raise NovaError("proposal_missing", "A verified project proposal is needed to draft this message.")
        return draft

    @staticmethod
    def digest(subject, body, facts):
        return hashlib.sha256(encoded([subject, body, facts]).encode()).hexdigest()

    def initial_draft(self, task_id, proposal, kind="introduction"):
        invoice = self.outstanding_invoice(task_id) if kind == "reminder" else None
        subject, body = self.compose(proposal, kind, invoice)
        facts = {
            "source": proposal["source"], "observations": proposal.get("observations", []),
            "scope": proposal.get("scope", []), "verification": proposal.get("verification", []),
            "estimate_inr": proposal.get("proposed_price_inr"), "effort_hours": proposal.get("effort_hours"),
        }
        if invoice:
            facts["invoice"] = {"reference": invoice["reference"], "balance_paise": invoice["balance_paise"]}
        cursor = self.db.execute(
            "INSERT OR IGNORE INTO business_drafts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (uuid4().hex[:12], task_id, kind, proposal["business"], subject, body, encoded(facts), "pending",
             self.digest(subject, body, facts), "verified_project", time.time()),
        )
        if cursor.rowcount:
            self.store.event("draft", "Email draft ready for owner review", task_id, kind_name=kind)
        return self.view(self.db.execute("SELECT * FROM business_drafts WHERE task_id=? AND kind=?", (task_id, kind)).fetchone())

    @staticmethod
    def view(row):
        result = dict(row)
        result["facts"] = json.loads(result["facts"])
        return result

    def list(self, task_id=None):
        if task_id:
            rows = self.db.execute("SELECT * FROM business_drafts WHERE task_id=? ORDER BY updated DESC LIMIT 100", (task_id,))
        else:
            rows = self.db.execute("SELECT * FROM business_drafts ORDER BY updated DESC LIMIT 100")
        return [self.view(row) for row in rows]

    def draft(self, draft_id):
        row = self.db.execute("SELECT * FROM business_drafts WHERE id=?", (draft_id,)).fetchone()
        if row is None:
            raise NovaError("draft_missing", "That draft does not exist.")
        return self.view(row)

    def create(self, task_id, kind):
        proposal = self.proposal_for(task_id)
        with self.db:
            return self.initial_draft(task_id, proposal, kind)

    def contact_draft(self, task_id):
        checkpoints = self.store.checkpoints(task_id)
        if "proposal" in checkpoints:
            return self.create(task_id, "introduction")
        sources = [record for record in checkpoints.get("report", {}).get("sources", []) if "score" in record]
        if self.store.get(task_id)["state"] != "completed" or len(sources) != 1:
            raise NovaError("contact_target", "Choose a completed project or a review of one business before drafting outreach.")
        source = sources[0]
        with self.db:
            return self.initial_draft(task_id, {"business": source["name"], "source": source["url"],
                                      "observations": [item["observation"] for item in source["findings"]],
                                      "research_only": True})

    def edit(self, draft_id, edit):
        with self.db:
            draft = self.draft(draft_id)
            if draft["digest"] != edit.digest:
                raise NovaError("review_changed", "This draft has changed. Refresh it before editing.")
            digest = self.digest(edit.subject, edit.body, draft["facts"])
            if digest != draft["digest"]:
                self.db.execute(
                    "UPDATE business_drafts SET subject=?,body=?,digest=?,status='pending',origin='owner_edited',updated=? WHERE id=?",
                    (edit.subject, edit.body, digest, time.time(), draft_id),
                )
                self.store.event("draft", "Edited email is ready for a new review", draft["task_id"])
        return self.draft(draft_id)

    def review(self, draft_id, digest, approved):
        with self.db:
            draft = self.draft(draft_id)
            changed = self.db.execute(
                "UPDATE business_drafts SET status=?,updated=? WHERE id=? AND digest=? AND status='pending'",
                ("approved" if approved else "rejected", time.time(), draft_id, digest),
            )
            if not changed.rowcount:
                raise NovaError("review_changed", "Review the latest pending email draft.")
            self.store.event("draft", "Owner recorded a draft review", draft["task_id"], approved=approved)
        return self.draft(draft_id)

    def change_lead(self, task_id, change):
        transitions = {
            "researched": {"qualified", "archived"}, "qualified": {"contacted", "lost", "archived"},
            "awaiting_approval": {"qualified", "archived"}, "proposal_reviewed": {"contacted", "lost", "archived"},
            "contacted": {"negotiating", "lost", "archived"}, "negotiating": {"won", "lost", "archived"},
            "won": {"delivered", "archived"}, "lost": {"archived"}, "delivered": {"archived"},
        }
        with self.db:
            row = self.db.execute("SELECT stage FROM leads WHERE task_id=? AND url=?", (task_id, change.url)).fetchone()
            if row is None or change.stage not in transitions.get(row["stage"], set()):
                raise NovaError("lead_transition", "The requested CRM stage does not follow the lead’s current stage.")
            self.db.execute("UPDATE leads SET stage=? WHERE task_id=? AND url=?", (change.stage, task_id, change.url))
            self.store.event("crm", "Owner recorded a lead stage", task_id, stage=change.stage, note=change.note)
        return {"task_id": task_id, "url": change.url, "stage": change.stage}

    def add_entry(self, entry):
        if entry.task_id:
            self.store.get(entry.task_id)
        if (entry.kind == "payment") != bool(entry.invoice_reference):
            raise NovaError("invoice_reference", "Payments require the reference of a recorded invoice.")
        ref = entry.reference.casefold()
        invoice_ref = entry.invoice_reference.casefold() if entry.invoice_reference else None
        with self.db:
            previous = self.db.execute("SELECT * FROM ledger WHERE kind=? AND reference=?", (entry.kind, ref)).fetchone()
            fields = (entry.task_id, entry.amount_paise, entry.occurred_on.isoformat(), invoice_ref, entry.note)
            if previous:
                if fields != tuple(previous[column] for column in ("task_id", "amount_paise", "occurred_on", "invoice_reference", "note")):
                    raise NovaError("duplicate_entry", "The ledger reference already belongs to a different entry.")
                return dict(previous)
            if invoice_ref:
                invoice = self.db.execute("SELECT task_id,amount_paise FROM ledger WHERE kind='invoice' AND reference=?", (invoice_ref,)).fetchone()
                paid = self.db.execute("SELECT COALESCE(SUM(amount_paise), 0) FROM ledger WHERE invoice_reference=?", (invoice_ref,)).fetchone()[0]
                if invoice is None or invoice["task_id"] != entry.task_id or paid + entry.amount_paise > invoice["amount_paise"]:
                    raise NovaError("payment_amount", "Match the invoice project and stay within its outstanding balance.")
            key = uuid4().hex[:12]
            self.db.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)", (
                key, entry.task_id, entry.kind, ref, entry.amount_paise, entry.occurred_on.isoformat(), invoice_ref, entry.note,
            ))
            self.store.event("finance", "Owner recorded a ledger entry", entry.task_id, entry_kind=entry.kind)
            return dict(self.db.execute("SELECT * FROM ledger WHERE id=?", (key,)).fetchone())

    def outstanding_invoice(self, task_id):
        row = self.db.execute(
            "SELECT reference, amount_paise-COALESCE((SELECT SUM(amount_paise) FROM ledger p "
            "WHERE p.invoice_reference=i.reference),0) AS balance_paise FROM ledger i "
            "WHERE kind='invoice' AND task_id=? AND balance_paise>0 ORDER BY occurred_on,reference LIMIT 1",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None

    def ledger(self):
        totals = {"invoice": 0, "payment": 0, "expense": 0}
        totals.update({row["kind"]: row["total"] for row in self.db.execute(
            "SELECT kind,SUM(amount_paise) total FROM ledger GROUP BY kind"
        )})
        return {
            "currency": "INR", "invoiced_paise": totals["invoice"], "received_paise": totals["payment"],
            "expense_paise": totals["expense"], "outstanding_paise": totals["invoice"] - totals["payment"],
            "net_cash_paise": totals["payment"] - totals["expense"],
            "entries": [dict(row) for row in self.db.execute("SELECT * FROM ledger ORDER BY occurred_on DESC,rowid DESC LIMIT 250")],
        }

    def feedback(self, task_id, data):
        if self.store.get(task_id)["state"] != "completed":
            raise NovaError("task_state", "Wait until the mission completes to record verified outcome feedback.")
        now = time.time()
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO outcome_feedback VALUES(?,?,?,?)", (task_id, data.rating, data.note, now))
            self.store.event("feedback", "Owner recorded feedback on a verified mission", task_id, rating=data.rating)
        return {"task_id": task_id, "rating": data.rating, "note": data.note, "updated": now}

    @staticmethod
    def email_export(draft, format_name):
        if format_name == "txt":
            return f"{draft['subject']}\n\n{draft['body']}\n"
        content = "".join(f"<p>{escape(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in draft["body"].split("\n\n"))
        return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                f'<title>{escape(draft["subject"])}</title><body style="margin:0;background:#eef1f5">'
                '<table role="presentation" style="width:100%;max-width:600px;margin:24px auto;background:#fff">'
                '<tr><td style="padding:32px;font:16px/1.55 system-ui,sans-serif;color:#172837">'
                f'<h1 style="font-size:22px">{escape(draft["subject"])}</h1>{content}</td></tr></table></body></html>')
