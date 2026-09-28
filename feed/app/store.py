"""SQLite persistence for timeline events."""

import json
import sqlite3
import threading
from datetime import datetime

from .models import Event, iso, parse_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id      TEXT PRIMARY KEY,
    source  TEXT NOT NULL,
    kind    TEXT NOT NULL,
    title   TEXT NOT NULL,
    url     TEXT,
    detail  TEXT,
    ts      TEXT NOT NULL,          -- ISO-8601 UTC, sortable as text
    meta    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts DESC);
"""


class Store:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def upsert(self, events: list[Event]) -> int:
        """Insert or update events. Returns how many ids were new."""
        if not events:
            return 0
        with self._lock:
            ids = [e.id for e in events]
            placeholders = ",".join("?" * len(ids))
            existing = {
                r["id"] for r in self._conn.execute(f"SELECT id FROM events WHERE id IN ({placeholders})", ids)
            }
            self._conn.executemany(
                """INSERT INTO events (id, source, kind, title, url, detail, ts, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     kind=excluded.kind, title=excluded.title, url=excluded.url,
                     detail=excluded.detail, ts=excluded.ts, meta=excluded.meta""",
                [(e.id, e.source, e.kind, e.title, e.url, e.detail, iso(e.ts), json.dumps(e.meta)) for e in events],
            )
            self._conn.commit()
        return len(set(ids) - existing)

    def has(self, event_id: str) -> bool:
        with self._lock:
            return self._conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone() is not None

    def delete(self, event_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def query(
        self,
        limit: int = 30,
        before: datetime | None = None,
        sources: list[str] | None = None,
    ) -> tuple[list[Event], bool]:
        """Newest-first page of events, plus whether older events exist."""
        sql = "SELECT * FROM events WHERE 1=1"
        args: list = []
        if before is not None:
            sql += " AND ts < ?"
            args.append(iso(before))
        if sources:
            sql += f" AND source IN ({','.join('?' * len(sources))})"
            args.extend(sources)
        sql += " ORDER BY ts DESC, id DESC LIMIT ?"
        args.append(limit + 1)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        events = [self._row(r) for r in rows[:limit]]
        return events, len(rows) > limit

    @staticmethod
    def _row(r: sqlite3.Row) -> Event:
        return Event(
            id=r["id"],
            source=r["source"],
            kind=r["kind"],
            title=r["title"],
            url=r["url"],
            detail=r["detail"],
            ts=parse_iso(r["ts"]),
            meta=json.loads(r["meta"] or "{}"),
        )
