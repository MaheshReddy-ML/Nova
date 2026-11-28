"""Agent tools for scholarly search, saved documents and outreach follow-up reminders.

- Papers come from Semantic Scholar (abstracts, citation counts) with arXiv as the fallback. Every request is recorded
  in the provenance ledger like any other fetch, so paper titles in an answer are checked against real results.
- Documents are Markdown or Word files in <workspace>/documents, for deliverables too long to speak.
- Follow-ups are reminders only. They surface in briefings and workspace status; nothing is ever sent automatically.
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx

from .domain import NovaError
from .provenance import record_fetch

S2_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
ARXIV_URL = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
DOCUMENT = re.compile(r"[a-z0-9][a-z0-9-]{0,70}\.(?:md|docx)")
FOLLOW_UP_SCHEMA = """
CREATE TABLE IF NOT EXISTS follow_ups (
 id TEXT PRIMARY KEY, business TEXT NOT NULL, recipient TEXT NOT NULL, message_id TEXT, note TEXT NOT NULL,
 due REAL NOT NULL, status TEXT NOT NULL, created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS follow_ups_due ON follow_ups(status,due);
"""


def squash(value, limit):
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[:limit].rsplit(" ", 1)[0] + "…"


# ---------- papers ----------

async def search_papers(client: httpx.AsyncClient, store, query, *, limit=6, since_year=None, api_key=""):
    query = " ".join(str(query).split())[:200]
    if len(query) < 3:
        raise NovaError("tool_input", "Give a paper search query.")
    limit = max(1, min(int(limit or 6), 10))
    key = f"papers:v1:{query.casefold()}:{limit}:{since_year}"
    if (cached := store.cached(key)) is not None:
        record_fetch(f"papers:{query}", "cache", json.dumps(cached), cached.get("provider", "paper cache"))
        return cached
    papers, provider = [], None
    try:
        papers = await semantic_scholar(client, query, limit, since_year, api_key)
        provider = "Semantic Scholar"
    except NovaError:
        papers = []
    if not papers:
        papers = await arxiv(client, query, limit, since_year)
        provider = "arXiv"
    result = {"query": query, "provider": provider, "papers": papers,
              "note": "Cite only these papers; abstracts are summaries, read the paper before relying on details."}
    if papers:
        store.cache(key, result, 6 * 3600)
    return result


async def semantic_scholar(client, query, limit, since_year, api_key=""):
    params = {"query": query, "limit": limit,
              "fields": "title,year,authors,abstract,citationCount,venue,url,externalIds,openAccessPdf"}
    if since_year:
        params["year"] = f"{int(since_year)}-"
    try:
        headers = {"User-Agent": "NOVA-Research/2.0"}
        if api_key:
            headers["x-api-key"] = api_key  # Free key; without it the shared pool often answers 429 and arXiv is used.
        response = await client.get(S2_URL, params=params, headers=headers, timeout=12)
    except httpx.HTTPError as exc:
        raise NovaError("papers_network", "Semantic Scholar did not respond.", transient=True) from exc
    record_fetch(str(response.url), response.status_code, response.content, "Semantic Scholar")
    if response.status_code != 200:  # 429 is common on the shared unauthenticated pool.
        raise NovaError("papers_provider", f"Semantic Scholar returned HTTP {response.status_code}.", transient=True)
    papers = []
    for item in response.json().get("data") or []:
        if not item.get("title"):
            continue
        ids = item.get("externalIds") or {}
        papers.append({
            "title": squash(item["title"], 220), "year": item.get("year"),
            "authors": [author.get("name") for author in (item.get("authors") or [])[:4] if author.get("name")],
            "venue": squash(item.get("venue"), 80) or None, "citations": item.get("citationCount"),
            "abstract": squash(item.get("abstract"), 600) or None,
            "url": (f"https://arxiv.org/abs/{ids['ArXiv']}" if ids.get("ArXiv") else item.get("url")),
            "doi": ids.get("DOI"), "pdf": (item.get("openAccessPdf") or {}).get("url"),
        })
    return papers


async def arxiv(client, query, limit, since_year):
    terms = " AND ".join(f"all:{word}" for word in re.findall(r"[\w-]{2,}", query)[:8])
    try:
        response = await client.get(ARXIV_URL, params={"search_query": terms or f"all:{query}", "max_results": limit * 2,
                                                       "sortBy": "relevance"},
                                    headers={"User-Agent": "NOVA-Research/2.0"}, timeout=15)
    except httpx.HTTPError as exc:
        raise NovaError("papers_network", "arXiv did not respond.", transient=True) from exc
    record_fetch(str(response.url), response.status_code, response.content, "arXiv")
    if response.status_code != 200:
        raise NovaError("papers_provider", f"Paper search is unavailable (arXiv HTTP {response.status_code}).", transient=True)
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise NovaError("papers_provider", "arXiv returned an unreadable response.") from exc
    papers = []
    for entry in root.findall("a:entry", ATOM):
        year = int((entry.findtext("a:published", "", ATOM) or "0")[:4] or 0) or None
        if since_year and year and year < int(since_year):
            continue
        link = entry.findtext("a:id", "", ATOM).strip().replace("http://", "https://")
        papers.append({
            "title": squash(entry.findtext("a:title", "", ATOM), 220), "year": year,
            "authors": [squash(node.findtext("a:name", "", ATOM), 60) for node in entry.findall("a:author", ATOM)[:4]],
            "venue": "arXiv preprint", "citations": None,
            "abstract": squash(entry.findtext("a:summary", "", ATOM), 600) or None,
            "url": re.sub(r"v\d+$", "", link), "doi": None, "pdf": re.sub(r"/abs/", "/pdf/", link) if link else None,
        })
    return papers[:limit]


# ---------- documents ----------

def slug(title):
    value = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:48].strip("-")
    return value or "document"


def save_document(workspace: Path, title, content, fmt="md"):
    title = squash(title, 120)
    content = str(content or "").replace("\r\n", "\n").strip()
    if len(title) < 3 or len(content) < 40:
        raise NovaError("tool_input", "A document needs a title and real content.")
    if len(content) > 60_000:
        raise NovaError("tool_input", "That document is too long; split it into parts.")
    fmt = "docx" if str(fmt).lower() in {"docx", "word"} else "md"
    folder = workspace / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now():%Y%m%d-%H%M}-{slug(title)}.{fmt}"
    path = folder / name
    if not content.lstrip().startswith("# "):
        content = f"# {title}\n\n{content}"
    if fmt == "md":
        path.write_text(content + "\n", encoding="utf-8")
    else:
        markdown_to_docx(content, path)
    return {"file": name, "url": f"/documents/{name}", "format": fmt, "characters": len(content),
            "say": f"I saved {title} to your documents as a {'Word' if fmt == 'docx' else 'Markdown'} file."}


def markdown_to_docx(markdown, path):
    from docx import Document

    doc = Document()
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if heading := re.match(r"(#{1,4})\s+(.*)", line):
            doc.add_heading(inline_text(heading.group(2)), level=len(heading.group(1)) - 1)  # "#" is the title, "##" Heading 1
        elif bullet := re.match(r"\s*[-*+]\s+(.*)", line):
            add_runs(doc.add_paragraph(style="List Bullet"), bullet.group(1))
        elif number := re.match(r"\s*\d+[.)]\s+(.*)", line):
            add_runs(doc.add_paragraph(style="List Number"), number.group(1))
        else:
            add_runs(doc.add_paragraph(), line.strip())
    doc.save(path)


def inline_text(text):
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text).replace("**", "").replace("`", "")


def add_runs(paragraph, text):
    """Bold (**x**) survives; links become 'label (url)'."""
    for index, part in enumerate(re.split(r"\*\*", inline_text_keep_bold(text))):
        if part:
            paragraph.add_run(part).bold = index % 2 == 1


def inline_text_keep_bold(text):
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text).replace("`", "")


def list_documents(workspace: Path, limit=30):
    folder = workspace / "documents"
    if not folder.is_dir():
        return []
    files = [path for path in folder.iterdir() if path.is_file() and not path.is_symlink() and DOCUMENT.fullmatch(path.name)]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [{"file": path.name, "url": f"/documents/{path.name}", "bytes": path.stat().st_size,
             "modified": path.stat().st_mtime} for path in files[:limit]]


def document_path(workspace: Path, name):
    folder = (workspace / "documents").resolve()
    path = folder / name
    if not DOCUMENT.fullmatch(name) or folder.is_symlink() or path.is_symlink() or not path.is_file():
        raise NovaError("document_missing", "That document does not exist.")
    return path


# ---------- follow-ups ----------

class FollowUps:
    def __init__(self, store):
        self.store = store
        self.db = store.db
        self.db.executescript(FOLLOW_UP_SCHEMA)

    def schedule(self, business, *, days=3, recipient="", message_id=None, note=""):
        business = squash(business, 140)
        if len(business) < 2:
            raise NovaError("tool_input", "Say who to follow up with.")
        days = float(days) if isinstance(days, (int, float)) else 3.0
        if not 0 < days <= 60:
            raise NovaError("tool_input", "Follow-ups can be set between a few hours and 60 days ahead.")
        if message_id:
            row = self.db.execute("SELECT recipient,business FROM outbox WHERE id=?", (message_id,)).fetchone()
            if row is None:
                message_id = None
            else:
                recipient = recipient or row["recipient"]
        key = uuid4().hex[:12]
        now = time.time()
        with self.db:
            self.db.execute("INSERT INTO follow_ups VALUES(?,?,?,?,?,?,'open',?)",
                            (key, business, squash(recipient, 160), message_id, squash(note, 400), now + days * 86400, now))
            self.store.event("outreach", f"Follow-up with {business} set for {days:g} days from now", follow_up_id=key)
        when = datetime.fromtimestamp(now + days * 86400)
        return {"follow_up_id": key, "business": business, "due": when.isoformat(timespec="minutes"),
                "say": f"Done. I'll remind you to follow up with {business} on {when:%A %-d %B}."}

    def due(self, now=None):
        now = time.time() if now is None else now
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM follow_ups WHERE status='open' AND due<=? ORDER BY due LIMIT 20", (now,))]

    def upcoming(self, limit=10):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM follow_ups WHERE status='open' ORDER BY due LIMIT ?", (limit,))]

    def complete(self, target):
        """Mark the open follow-up matching an id or business name as done."""
        target = str(target).strip()
        rows = self.upcoming(50)
        match = next((row for row in rows if row["id"] == target), None) or next(
            (row for row in rows if target.casefold() in row["business"].casefold()), None)
        if match is None:
            raise NovaError("follow_up_missing", f"No open follow-up matches “{target}”.")
        with self.db:
            self.db.execute("UPDATE follow_ups SET status='done' WHERE id=?", (match["id"],))
        return {"say": f"Marked the follow-up with {match['business']} as done."}
