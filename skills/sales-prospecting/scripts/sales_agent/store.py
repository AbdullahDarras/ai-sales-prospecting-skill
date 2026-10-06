import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .states import InvalidTransition, State, check_transition

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL,
    country TEXT NOT NULL,
    city TEXT NOT NULL,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    stuck_from TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL REFERENCES leads(id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL REFERENCES leads(id),
    field TEXT NOT NULL,
    value TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_class TEXT NOT NULL,
    confidence REAL NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    params TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blocked_contacts (
    contact TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def _normalize_contact(contact: str) -> str:
    return re.sub(r"[\s\-()]", "", contact).lower()


def _lead_id(code: str, country: str, name: str) -> str:
    key = f"{code}|{country}|{_normalize_name(name)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # الواجهة ومهام الخلفية تصل من خيوط مختلفة. WAL ومهلة الانتظار يخففان تعارض الكتابة.
        self._db = sqlite3.connect(str(path), check_same_thread=False, timeout=15)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    def add_lead(self, code: str, country: str, city: str, name: str) -> str:
        lead_id = _lead_id(code, country, name)
        if self._db.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone():
            return lead_id
        now = _now()
        with self._db:
            self._db.execute(
                "INSERT INTO leads (id, code, country, city, name, state, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lead_id, code, country, city, name.strip(), State.DISCOVERED.value, now, now),
            )
            self._log(lead_id, None, State.DISCOVERED, "اكتشاف أولي")
        return lead_id

    def has_lead(self, code: str, country: str, name: str) -> bool:
        lead_id = _lead_id(code, country, name)
        return self._db.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone() is not None

    def get_lead(self, lead_id: str) -> dict:
        row = self._db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if row is None:
            raise KeyError(lead_id)
        lead = dict(row)
        lead["state"] = State(lead["state"])
        return lead

    def leads_in_state(self, state: State, limit: int = 100) -> list[dict]:
        rows = self._db.execute(
            "SELECT id FROM leads WHERE state = ? ORDER BY created_at, id LIMIT ?",
            (state.value, limit),
        ).fetchall()
        return [self.get_lead(r["id"]) for r in rows]

    def transition(self, lead_id: str, new: State, reason: str) -> None:
        lead = self.get_lead(lead_id)
        current = lead["state"]
        check_transition(current, new)
        stuck_from = current.value if new == State.STUCK else None
        with self._db:
            self._db.execute(
                "UPDATE leads SET state = ?, stuck_from = ?, updated_at = ? WHERE id = ?",
                (new.value, stuck_from, _now(), lead_id),
            )
            self._log(lead_id, current, new, reason)

    def resume(self, lead_id: str) -> None:
        lead = self.get_lead(lead_id)
        if lead["state"] != State.STUCK or not lead["stuck_from"]:
            raise InvalidTransition(f"{lead['state'].value} -> resume")
        previous = State(lead["stuck_from"])
        with self._db:
            self._db.execute(
                "UPDATE leads SET state = ?, stuck_from = NULL, updated_at = ? WHERE id = ?",
                (previous.value, _now(), lead_id),
            )
            self._log(lead_id, State.STUCK, previous, "استئناف بعد التعثر")

    def history(self, lead_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM history WHERE lead_id = ? ORDER BY id", (lead_id,)
        ).fetchall()
        out = []
        for r in rows:
            h = dict(r)
            h["to_state"] = State(h["to_state"])
            h["from_state"] = State(h["from_state"]) if h["from_state"] else None
            out.append(h)
        return out

    def set_field(self, lead_id: str, field: str, value: str, source_url: str,
                  source_class: str, confidence: float) -> None:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        self.get_lead(lead_id)
        with self._db:
            self._db.execute(
                "INSERT INTO observations (lead_id, field, value, source_url, source_class,"
                " confidence, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (lead_id, field, value, source_url, source_class, confidence, _now()),
            )

    def get_observations(self, lead_id: str, field: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM observations WHERE lead_id = ? AND field = ? ORDER BY id",
            (lead_id, field),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_fields(self, lead_id: str) -> dict[str, dict]:
        """أحدث ملاحظة لكل حقل."""
        rows = self._db.execute(
            "SELECT o.* FROM observations o JOIN ("
            " SELECT field, MAX(id) AS mid FROM observations WHERE lead_id = ? GROUP BY field"
            ") m ON o.id = m.mid",
            (lead_id,),
        ).fetchall()
        return {r["field"]: dict(r) for r in rows}

    def delete_lead(self, lead_id: str) -> None:
        """للبيانات التجريبية فقط. السجلات الحقيقية لا تُحذف، تُنقل لحالة."""
        with self._db:
            for table in ("observations", "history"):
                self._db.execute(f"DELETE FROM {table} WHERE lead_id = ?", (lead_id,))
            self._db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))

    def count_by_state(self) -> dict[str, int]:
        rows = self._db.execute("SELECT state, COUNT(*) AS n FROM leads GROUP BY state").fetchall()
        return {r["state"]: r["n"] for r in rows}

    def search_leads(self, state: State | None = None, code: str | None = None,
                     country: str | None = None, q: str | None = None,
                     limit: int = 200) -> list[dict]:
        sql, args = "SELECT id FROM leads WHERE 1=1", []
        if state:
            sql += " AND state = ?"
            args.append(state.value)
        if code:
            sql += " AND code = ?"
            args.append(code)
        if country:
            sql += " AND country = ?"
            args.append(country)
        if q:
            sql += " AND name LIKE ?"
            args.append(f"%{q.strip()}%")
        sql += " ORDER BY created_at DESC, id LIMIT ?"
        args.append(limit)
        return [self.get_lead(r["id"]) for r in self._db.execute(sql, args).fetchall()]

    def all_observations(self, lead_id: str) -> dict[str, list[dict]]:
        rows = self._db.execute(
            "SELECT * FROM observations WHERE lead_id = ? ORDER BY id", (lead_id,)
        ).fetchall()
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            grouped.setdefault(r["field"], []).append(dict(r))
        return grouped

    def transitions_today(self, state: State) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return self._db.execute(
            "SELECT COUNT(*) AS n FROM history WHERE to_state = ? AND at >= ?",
            (state.value, today),
        ).fetchone()["n"]

    def get_setting(self, key: str, default: str = "") -> str:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

    def create_run(self, params: dict) -> int:
        with self._db:
            cur = self._db.execute(
                "INSERT INTO runs (params, status, created_at) VALUES (?, 'queued', ?)",
                (json.dumps(params, ensure_ascii=False), _now()))
        return cur.lastrowid

    def update_run(self, run_id: int, status: str | None = None, summary: dict | None = None) -> None:
        with self._db:
            if status:
                finished = _now() if status in ("done", "failed", "cancelled") else None
                self._db.execute("UPDATE runs SET status = ?, finished_at = COALESCE(?, finished_at) WHERE id = ?",
                                 (status, finished, run_id))
            if summary is not None:
                self._db.execute("UPDATE runs SET summary = ? WHERE id = ?",
                                 (json.dumps(summary, ensure_ascii=False), run_id))

    def get_run(self, run_id: int) -> dict:
        row = self._db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        run = dict(row)
        run["params"], run["summary"] = json.loads(run["params"]), json.loads(run["summary"])
        return run

    def list_runs(self, limit: int = 20) -> list[dict]:
        rows = self._db.execute("SELECT id FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self.get_run(r["id"]) for r in rows]

    def add_log(self, run_id: int, message: str, level: str = "info") -> None:
        with self._db:
            self._db.execute("INSERT INTO run_log (run_id, level, message, at) VALUES (?, ?, ?, ?)",
                             (run_id, level, message, _now()))

    def get_logs(self, run_id: int, after_id: int = 0) -> list[dict]:
        rows = self._db.execute("SELECT * FROM run_log WHERE run_id = ? AND id > ? ORDER BY id",
                                (run_id, after_id)).fetchall()
        return [dict(r) for r in rows]

    def block_contact(self, contact: str, reason: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO blocked_contacts (contact, reason, at) VALUES (?, ?, ?)",
                (_normalize_contact(contact), reason, _now()),
            )

    def is_blocked(self, contact: str) -> bool:
        return self._db.execute(
            "SELECT 1 FROM blocked_contacts WHERE contact = ?", (_normalize_contact(contact),)
        ).fetchone() is not None

    def _log(self, lead_id: str, from_state, to_state: State, reason: str) -> None:
        self._db.execute(
            "INSERT INTO history (lead_id, from_state, to_state, reason, at) VALUES (?, ?, ?, ?, ?)",
            (lead_id, from_state.value if from_state else None, to_state.value, reason, _now()),
        )
