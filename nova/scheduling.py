import json
import math
import time
from uuid import uuid4

from pydantic import Field

from .domain import MissionInput, NovaError, StrictModel, TERMINAL
from .store import encoded

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, spec TEXT NOT NULL, every_hours INTEGER NOT NULL,
 next_due REAL NOT NULL, enabled INTEGER NOT NULL, latest_task TEXT REFERENCES tasks(id),
 created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS schedule_queue ON schedules(enabled,next_due);
"""


class RepeatInput(StrictModel):
    mission: MissionInput
    every_hours: int = Field(ge=1, le=24 * 30, strict=True)
    first_at: float | None = Field(default=None, ge=0, le=4102444800, allow_inf_nan=False)


class RepeatControl(StrictModel):
    enabled: bool


class Schedules:
    def __init__(self, store):
        self.store = store
        self.db = store.db
        self.db.executescript(SCHEMA)

    @staticmethod
    def view(row):
        value = dict(row)
        value["spec"] = json.loads(value["spec"])
        value["enabled"] = bool(value["enabled"])
        return value

    def list(self):
        return [self.view(row) for row in self.db.execute("SELECT * FROM schedules ORDER BY created DESC LIMIT 100")]

    def get(self, key):
        row = self.db.execute("SELECT * FROM schedules WHERE id=?", (key,)).fetchone()
        if row is None:
            raise NovaError("schedule_missing", "That schedule could not be found.")
        return row

    def create(self, data):
        mission = data.mission
        payload = mission.model_dump(exclude={"run_at"}, mode="json")
        with self.db:
            if self.store.stopped():
                raise NovaError("stopped", "Emergency stop is active.")
            now = time.time()
            if mission.depends_on:
                self.store.get(mission.depends_on)
            duplicate = self.db.execute(
                "SELECT * FROM schedules WHERE spec=? AND every_hours=? AND enabled=1", (encoded(payload), data.every_hours),
            ).fetchone()
            if duplicate:
                return self.view(duplicate)
            key = uuid4().hex[:12]
            self.db.execute("INSERT INTO schedules VALUES(?,?,?,?,?,1,NULL,?)",
                            (key, mission.title, encoded(payload), data.every_hours, data.first_at or now, now))
            self.store.event("schedule", "Owner created a repeat schedule", schedule_id=key)
        return self.view(self.get(key))

    def change(self, key, enabled):
        with self.db:
            row = self.get(key)
            if enabled and self.store.stopped():
                raise NovaError("stopped", "Reset emergency stop before enabling a schedule.")
            if bool(row["enabled"]) != enabled:
                self.db.execute("UPDATE schedules SET enabled=? WHERE id=?", (int(enabled), key))
                self.store.event("schedule", "Repeat schedule resumed" if enabled else "Repeat schedule paused", schedule_id=key)
        return self.view(self.get(key))

    def next_due(self):
        return self.db.execute("SELECT MIN(next_due) FROM schedules WHERE enabled=1").fetchone()[0]

    def materialize(self, now=None):
        if self.store.stopped():
            return
        now = time.time() if now is None else now
        with self.db:
            due = self.db.execute(
                "SELECT * FROM schedules WHERE enabled=1 AND next_due<=? ORDER BY next_due,id LIMIT 10", (now,),
            ).fetchall()
            for row in due:
                interval = row["every_hours"] * 3600
                ticks = math.floor((now - row["next_due"]) / interval)
                slot = row["next_due"] + ticks * interval
                latest = row["latest_task"]
                if latest is None or self.store.get(latest)["state"] in TERMINAL:
                    mission = MissionInput.model_validate({**json.loads(row["spec"]), "run_at": slot})
                    task, created = self.store.submit_in_transaction(mission)
                    latest = task["id"]
                    if created:
                        self.store.event("schedule", "Repeat schedule queued a mission", latest, schedule_id=row["id"])
                self.db.execute("UPDATE schedules SET next_due=?,latest_task=? WHERE id=?",
                                (slot + interval, latest, row["id"]))
