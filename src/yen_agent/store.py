"""Durable record of what the agent did on every call.

Why this exists
---------------
Before this module, ``take_message`` appended to a Python list on the Concierge,
and a Concierge is created **per call**. So the agent told callers *"I've passed
your message to the team"* and the message was garbage-collected when they hung
up. Same for ``join_waitlist`` — *"we'll text you the moment a table opens"* went
nowhere. Those are the two paths the agent uses for the calls it *cannot* close
(a party of 14, a fully-booked Saturday), which are the highest-value calls in
the system. They were the only ones guaranteed to be lost.

Two rules follow from that, and they are the whole design:

1. **Never speak a promise you haven't kept.** The confirmation line is returned
   only *after* the row is committed. If the write fails, the agent says
   something honest instead.
2. **Storage and delivery are separate.** Writing to disk is what makes the
   promise true; texting/emailing the restaurant is how they find out quickly.
   Delivery is best-effort and may fail — the record must not depend on it.

Why SQLite
----------
One restaurant, one process, a handful of calls a day, and a mandate to deploy
once and not touch it again. SQLite is a file: no service to run, back up, patch,
or upgrade. WAL mode is on so a reader (the owner running ``scripts/calls.py``)
never blocks the agent mid-call.

⚠️  **Deployment constraint this introduces.** The agent was previously stateless
per call and could run on ephemeral disk. It can't now. ``YEN_DB_PATH`` must
point at a **persistent volume**, or every restart silently loses the messages —
reintroducing exactly the bug this module removes.

⚠️  **This file contains guest PII** (names, phone numbers). Quebec's Law 25
applies. Hence ``purge_older_than`` and a documented retention default; see
``docs/DATA_RETENTION.md``.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Keep guest contact details no longer than this by default (Law 25: keep
#: personal information only as long as the purpose requires).
DEFAULT_RETENTION_DAYS = 90

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id       TEXT    NOT NULL UNIQUE,
    started_at    TEXT    NOT NULL,
    ended_at      TEXT,
    caller_number TEXT    NOT NULL DEFAULT '',
    locale        TEXT    NOT NULL DEFAULT 'en',
    outcome       TEXT    NOT NULL DEFAULT 'in_progress',
    transcript    TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id      TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    kind         TEXT    NOT NULL,           -- 'message' | 'waitlist'
    name         TEXT    NOT NULL DEFAULT '',
    phone        TEXT    NOT NULL DEFAULT '',
    body         TEXT    NOT NULL DEFAULT '',
    party_size   INTEGER NOT NULL DEFAULT 0,
    wanted_date  TEXT    NOT NULL DEFAULT '',
    wanted_time  TEXT    NOT NULL DEFAULT '',
    delivered_at TEXT,                       -- NULL = the team has NOT been told
    delivery_error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS booking_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    ok          INTEGER NOT NULL,            -- 1 = Libro confirmed it
    booking_id  TEXT    NOT NULL DEFAULT '',
    party_size  INTEGER NOT NULL DEFAULT 0,
    wanted_time TEXT    NOT NULL DEFAULT '',
    name        TEXT    NOT NULL DEFAULT '',
    phone       TEXT    NOT NULL DEFAULT '',
    error       TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_messages_undelivered
    ON messages (delivered_at) WHERE delivered_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_attempts_failed
    ON booking_attempts (ok, created_at);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class PendingMessage:
    """A row the restaurant has not been told about yet."""

    id: int
    kind: str
    name: str
    phone: str
    body: str
    party_size: int
    wanted_date: str
    wanted_time: str
    created_at: str


class CallStore:
    """SQLite-backed record of calls, messages, and booking attempts.

    Thread-safe: the agent's tools run on the job worker thread while a CLI
    reader may hold its own connection. One lock around writes is ample at this
    volume and avoids reasoning about SQLite threading modes.
    """

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or os.environ.get("YEN_DB_PATH", "yen_calls.db")
        self._lock = threading.Lock()
        if self.db_path != ":memory:":
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: guarded by self._lock below.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            # WAL lets the owner read the log while a call is in progress.
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # -- calls -------------------------------------------------------------
    def start_call(self, call_id: str, *, caller_number: str = "",
                   locale: str = "en") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO calls (call_id, started_at, caller_number, locale) "
                "VALUES (?, ?, ?, ?)",
                (call_id, _now(), caller_number, locale),
            )
            self._conn.commit()

    def end_call(self, call_id: str, *, outcome: str = "completed",
                 transcript: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE calls SET ended_at = ?, outcome = ?, transcript = ? "
                "WHERE call_id = ?",
                (_now(), outcome, transcript, call_id),
            )
            self._conn.commit()

    # -- messages & waitlist ----------------------------------------------
    def record_message(self, *, call_id: str, kind: str, name: str, phone: str,
                       body: str = "", party_size: int = 0, wanted_date: str = "",
                       wanted_time: str = "") -> int:
        """Commit a message/waitlist row. Returns its id.

        Raises on failure **on purpose** — the caller must not speak a
        confirmation if this didn't land.
        """
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO messages (call_id, created_at, kind, name, phone, body, "
                "party_size, wanted_date, wanted_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (call_id, _now(), kind, name, phone, body, party_size,
                 wanted_date, wanted_time),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def mark_delivered(self, message_id: int, *, error: str = "") -> None:
        """Record whether the restaurant was actually notified."""
        with self._lock:
            if error:
                self._conn.execute(
                    "UPDATE messages SET delivery_error = ? WHERE id = ?",
                    (error, message_id),
                )
            else:
                self._conn.execute(
                    "UPDATE messages SET delivered_at = ?, delivery_error = '' "
                    "WHERE id = ?",
                    (_now(), message_id),
                )
            self._conn.commit()

    def pending_messages(self) -> list[PendingMessage]:
        """Rows the restaurant has never been told about — the retry queue."""
        rows = self._conn.execute(
            "SELECT id, kind, name, phone, body, party_size, wanted_date, "
            "wanted_time, created_at FROM messages WHERE delivered_at IS NULL "
            "ORDER BY id"
        ).fetchall()
        return [PendingMessage(**dict(r)) for r in rows]

    # -- bookings ----------------------------------------------------------
    def record_booking_attempt(self, *, call_id: str, ok: bool, booking_id: str = "",
                               party_size: int = 0, wanted_time: str = "",
                               name: str = "", phone: str = "",
                               error: str = "") -> None:
        """Log every booking attempt, successful or not.

        The failures are the point: this is how the owner finds out a caller
        wanted a table and didn't get one.
        """
        with self._lock:
            self._conn.execute(
                "INSERT INTO booking_attempts (call_id, created_at, ok, booking_id, "
                "party_size, wanted_time, name, phone, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (call_id, _now(), 1 if ok else 0, booking_id, party_size,
                 wanted_time, name, phone, error),
            )
            self._conn.commit()

    def failed_bookings(self, *, since_days: int = 7) -> list[sqlite3.Row]:
        cutoff = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(days=since_days)).isoformat(timespec="seconds")
        return self._conn.execute(
            "SELECT * FROM booking_attempts WHERE ok = 0 AND created_at >= ? "
            "ORDER BY created_at DESC", (cutoff,)
        ).fetchall()

    def recent_calls(self, limit: int = 50) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM calls ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def stats(self, *, since_days: int = 7) -> dict:
        cutoff = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(days=since_days)).isoformat(timespec="seconds")
        q = self._conn.execute
        return {
            "calls": q("SELECT COUNT(*) c FROM calls WHERE started_at >= ?",
                       (cutoff,)).fetchone()["c"],
            "bookings_ok": q("SELECT COUNT(*) c FROM booking_attempts "
                             "WHERE ok = 1 AND created_at >= ?", (cutoff,)).fetchone()["c"],
            "bookings_failed": q("SELECT COUNT(*) c FROM booking_attempts "
                                 "WHERE ok = 0 AND created_at >= ?", (cutoff,)).fetchone()["c"],
            "messages": q("SELECT COUNT(*) c FROM messages WHERE created_at >= ?",
                          (cutoff,)).fetchone()["c"],
            "undelivered": q("SELECT COUNT(*) c FROM messages "
                             "WHERE delivered_at IS NULL").fetchone()["c"],
        }

    # -- retention (Law 25) ------------------------------------------------
    def purge_older_than(self, days: int = DEFAULT_RETENTION_DAYS) -> int:
        """Delete guest contact details past the retention window."""
        cutoff = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(days=days)).isoformat(timespec="seconds")
        with self._lock:
            n = 0
            for table, col in (("messages", "created_at"),
                               ("booking_attempts", "created_at"),
                               ("calls", "started_at")):
                n += self._conn.execute(
                    f"DELETE FROM {table} WHERE {col} < ?", (cutoff,)
                ).rowcount
            self._conn.commit()
            return n

    def close(self) -> None:
        with self._lock:
            self._conn.close()
