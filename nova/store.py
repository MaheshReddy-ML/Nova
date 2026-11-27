import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from .domain import ACTIVE, TERMINAL, MissionInput, NovaError, State

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, title TEXT NOT NULL, spec TEXT NOT NULL,
 state TEXT NOT NULL, priority INTEGER NOT NULL, due REAL NOT NULL, created REAL NOT NULL,
 updated REAL NOT NULL, depends_on TEXT REFERENCES tasks(id), cursor INTEGER NOT NULL DEFAULT 0,
 retries INTEGER NOT NULL DEFAULT 0, error TEXT
);
CREATE INDEX IF NOT EXISTS task_queue ON tasks(state, due, priority);
CREATE TABLE IF NOT EXISTS checkpoints (
 task_id TEXT NOT NULL REFERENCES tasks(id), step INTEGER NOT NULL, name TEXT NOT NULL,
 data TEXT NOT NULL, PRIMARY KEY (task_id, step)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL, kind TEXT NOT NULL,
 task_id TEXT, message TEXT NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
 id INTEGER PRIMARY KEY AUTOINCREMENT, started REAL NOT NULL, task_id TEXT, lane TEXT NOT NULL,
 capability TEXT NOT NULL, model TEXT NOT NULL, reserved INTEGER NOT NULL,
 prompt INTEGER, completion INTEGER, reasoning INTEGER, total INTEGER, latency_ms INTEGER,
 first_ms INTEGER, estimate INTEGER NOT NULL, status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_started ON usage (started);
CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, expires REAL NOT NULL, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS leads (
 task_id TEXT NOT NULL REFERENCES tasks(id), url TEXT NOT NULL, name TEXT NOT NULL,
 score INTEGER NOT NULL, evidence TEXT NOT NULL, stage TEXT NOT NULL, PRIMARY KEY(task_id,url)
);
CREATE TABLE IF NOT EXISTS approvals (
 task_id TEXT PRIMARY KEY REFERENCES tasks(id), action TEXT NOT NULL, payload TEXT NOT NULL,
 digest TEXT NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL UNIQUE, category TEXT NOT NULL,
 headline TEXT NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(headline, body, content='notes', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS notes_insert AFTER INSERT ON notes BEGIN
 INSERT INTO notes_fts(rowid,headline,body) VALUES (new.id,new.headline,new.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_delete AFTER DELETE ON notes BEGIN
 INSERT INTO notes_fts(notes_fts,rowid,headline,body) VALUES ('delete',old.id,old.headline,old.body);
END;
"""


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.touch(mode=0o600, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.on_event = lambda: None
        self.db.executescript("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;" + SCHEMA)

    def event(self, kind, message, task_id=None, **data):
        cursor = self.db.execute("INSERT INTO events(time,kind,task_id,message,data) VALUES (?,?,?,?,?)",
                                 (time.time(), kind, task_id, message, encoded(data)))
        self.on_event()
        return cursor.lastrowid

    def log(self, kind, message, task_id=None, **data):
        with self.db:
            self.event(kind, message, task_id, **data)

    def get(self, task_id):
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise NovaError("task_missing", "That task could not be found.")
        return row

    def view(self, row):
        info = dict(row)
        info["spec"] = json.loads(info["spec"])
        info.pop("fingerprint")
        return info

    def tasks(self):
        return [self.view(row) for row in self.db.execute("SELECT * FROM tasks ORDER BY created DESC LIMIT 100")]

    def submit(self, spec: MissionInput):
        payload = spec.model_dump(mode="json")
        identity = {k: v for k, v in payload.items() if k not in {"title", "priority"}}
        fingerprint = hashlib.sha256(encoded(identity).encode()).hexdigest()
        with self.db:
            if self.stopped():
                raise NovaError("stopped", "Emergency stop is active.")
            if spec.depends_on:
                self.get(spec.depends_on)
            existing = self.db.execute(
                "SELECT id FROM tasks WHERE fingerprint=? AND state NOT IN ('failed','completed','cancelled')",
                (fingerprint,),
            ).fetchone()
            if existing:
                return self.view(self.get(existing["id"])), False
            now = time.time()
            task_id = uuid4().hex[:12]
            self.db.execute(
                "INSERT INTO tasks(id,fingerprint,title,spec,state,priority,due,created,updated,depends_on) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (task_id, fingerprint, spec.title, encoded(payload), State.QUEUED, spec.priority,
                 spec.run_at or now, now, now, spec.depends_on),
            )
            self.event("task", "Mission queued", task_id, state=State.QUEUED)
        return self.view(self.get(task_id)), True

    def stopped(self):
        value = self.db.execute("SELECT value FROM settings WHERE key='stopped'").fetchone()
        return bool(value and value[0] == "1")

    def stop(self, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES ('stopped',?)", ("1" if value else "0",))
            if value:
                for row in self.db.execute("SELECT id,state FROM tasks").fetchall():
                    if row["state"] not in TERMINAL:
                        self.transition(row["id"], State.CANCELLED, "Cancelled by emergency stop")
            self.event("system", "Emergency stop enabled" if value else "Emergency stop reset")

    def transition(self, task_id, state, message, *, error=None, due=None, retry=False):
        self.db.execute(
            "UPDATE tasks SET state=?, updated=?, error=?, due=COALESCE(?,due), retries=retries+? WHERE id=?",
            (state, time.time(), error, due, int(retry), task_id),
        )
        self.event("task", message, task_id, state=state)

    def control(self, task_id, action):
        with self.db:
            row = self.get(task_id)
            current = row["state"]
            if current in TERMINAL or (action == "resume" and current != State.PAUSED):
                raise NovaError("task_state", f"Cannot {action} a task in state {current}.")
            if action == "pause":
                self.transition(task_id, State.PAUSED, "Mission paused")
            elif action == "resume":
                if self.stopped():
                    raise NovaError("stopped", "Emergency stop is active.")
                self.transition(task_id, State.QUEUED, "Mission resumed", due=time.time())
            else:
                self.transition(task_id, State.CANCELLED, "Mission cancelled")
        return self.view(self.get(task_id))

    def recover(self):
        with self.db:
            for row in self.db.execute("SELECT id,state FROM tasks").fetchall():
                if row["state"] in ACTIVE:
                    self.transition(row["id"], State.QUEUED, "Recovered from the last saved checkpoint", due=time.time())
            self.db.execute("UPDATE usage SET status='interrupted' WHERE status='pending'")

    def claim(self, excluded):
        if self.stopped():
            return None
        with self.db:
            rows = self.db.execute(
                "SELECT t.*, parent.state AS parent_state FROM tasks t LEFT JOIN tasks parent ON parent.id=t.depends_on "
                "WHERE t.state IN ('queued','retry_scheduled') AND t.due<=? ORDER BY t.priority DESC, t.due, t.created",
                (time.time(),),
            )
            for row in rows.fetchall():
                if row["id"] in excluded:
                    continue
                if row["parent_state"] in (State.FAILED, State.CANCELLED):
                    self.transition(row["id"], State.FAILED, "Dependency did not complete", error="dependency_failed")
                    continue
                if row["depends_on"] and row["parent_state"] != State.COMPLETE:
                    continue
                self.transition(row["id"], State.PLANNING, "Preparing workflow")
                return self.get(row["id"])
        return None

    def next_due(self, excluded):
        rows = self.db.execute(
            "SELECT t.id,t.due FROM tasks t LEFT JOIN tasks p ON p.id=t.depends_on WHERE "
            "t.state IN ('queued','retry_scheduled') AND (p.state IS NULL OR p.state IN ('completed','failed','cancelled')) "
            "ORDER BY t.due"
        )
        return next((row["due"] for row in rows if row["id"] not in excluded), None)

    def checkpoints(self, task_id):
        return {row["name"]: json.loads(row["data"]) for row in self.db.execute(
            "SELECT name,data FROM checkpoints WHERE task_id=? ORDER BY step", (task_id,)
        )}

    def save(self, task_id, step, name, data, apply=None):
        with self.db:
            row = self.get(task_id)
            if row["state"] not in ACTIVE or row["cursor"] != step:
                raise NovaError("checkpoint_conflict", "Mission state changed before checkpoint commit.")
            if apply:
                apply(self.db)
            self.db.execute("INSERT INTO checkpoints VALUES (?,?,?,?)", (task_id, step, name, encoded(data)))
            self.db.execute("UPDATE tasks SET cursor=cursor+1,retries=0,updated=? WHERE id=?", (time.time(), task_id))
            self.event("checkpoint", name, task_id, step=step + 1)

    def events(self, since, limit=100):
        return [{**dict(row), "data": json.loads(row["data"])} for row in self.db.execute(
            "SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (since, limit)
        )]

    def cached(self, key):
        row = self.db.execute("SELECT value FROM cache WHERE key=? AND expires>?", (key, time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key, data, ttl):
        with self.db:
            self.db.execute("DELETE FROM cache WHERE expires<=?", (time.time(),))
            self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (key, time.time() + ttl, encoded(data)))

    def usage(self, task_id=None):
        where = "WHERE task_id=?" if task_id is not None else ""
        parameters = (task_id,) if task_id is not None else ()
        rows = self.db.execute(
            f"WITH scope AS (SELECT * FROM usage {where}), "
            "ordered AS (SELECT lane,capability,latency_ms, "
            "ROW_NUMBER() OVER (PARTITION BY lane,capability ORDER BY latency_ms) AS rank, "
            "COUNT(*) OVER (PARTITION BY lane,capability) AS n FROM scope WHERE latency_ms IS NOT NULL), "
            "percentiles AS (SELECT lane,capability, "
            "MAX(CASE WHEN rank=(n+1)/2 THEN latency_ms END) p50_ms, "
            "MAX(CASE WHEN rank=(n*95+99)/100 THEN latency_ms END) p95_ms "
            "FROM ordered GROUP BY lane,capability) "
            "SELECT lane,capability,COUNT(*) AS calls,COUNT(total) AS reported_calls,"
            "SUM(prompt) AS input_tokens,SUM(completion) AS output_tokens,SUM(total) AS reported_tokens,"
            "SUM(CASE WHEN total IS NULL AND lane!='speech' THEN estimate END) AS estimated_tokens,"
            "SUM(reasoning) AS reasoning_tokens,ROUND(AVG(latency_ms)) AS mean_ms,ROUND(AVG(first_ms)) AS mean_first_ms,"
            "MAX(p50_ms) p50_ms,MAX(p95_ms) p95_ms,"
            "SUM(status NOT IN ('ok','pending')) AS errors FROM scope "
            "LEFT JOIN percentiles USING(lane,capability) GROUP BY lane,capability", parameters,
        )
        return [dict(row) for row in rows]

    def memory(self, query):
        terms = re.findall(r"\w+", query)[:8]
        if not terms:
            return [dict(row) for row in self.db.execute("SELECT * FROM notes ORDER BY updated DESC LIMIT 30")]
        match = " OR ".join(f'"{term}"' for term in terms)
        return [dict(row) for row in self.db.execute(
            "SELECT notes.* FROM notes_fts JOIN notes ON notes.id=notes_fts.rowid "
            "WHERE notes_fts MATCH ? ORDER BY rank LIMIT 8", (match,)
        )]
