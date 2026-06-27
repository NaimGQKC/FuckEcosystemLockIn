"""SQLite storage and seed data for the mock Libro service."""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
import uuid
from pathlib import Path

# Montreal is America/Toronto; fixed at EDT (-04:00) for the mock's purposes.
TZ_OFFSET = "-04:00"

# Seeded identifiers (kept stable so the agent config and tests can rely on them).
RESTAURANT_ID = "rest_yen_mtl"
EXP_DINNER = "exp_dinner_yen"
EXP_LUNCH = "exp_lunch_yen"
EXP_TASTING = "exp_tasting_yen"

# Per-slot seat capacity used by the availability calculation.
SLOT_CAPACITY = 24
# Online party-size limit (outside this range -> Libro code 2005).
MIN_PARTY_SIZE = 1
MAX_PARTY_SIZE = 12

# (experience_id, name, [HH:MM slots], payment_required)
_SEATING_PLAN = [
    (EXP_LUNCH, "Lunch", ["11:30", "12:00", "12:30", "13:00", "13:30", "14:00"], False),
    (
        EXP_DINNER,
        "Dinner",
        ["17:00", "17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30", "21:00"],
        False,
    ),
    (EXP_TASTING, "Tasting Menu", ["18:00", "20:00"], True),
]


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Database:
    """Thin synchronous SQLite wrapper, guarded by a lock for thread-safety.

    A mock service has trivial concurrency needs, so a single connection plus a
    lock is simpler and safer than a pool.
    """

    def __init__(self, path: str = ":memory:", *, seed: bool = True):
        self.path = path
        self._lock = threading.Lock()
        if path != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(Path(path).expanduser()) if path != ":memory:" else ":memory:",
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        if seed:
            self.seed()

    # -- schema / lifecycle -------------------------------------------------
    def _create_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS restaurants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    locality TEXT,
                    timezone TEXT
                );
                CREATE TABLE IF NOT EXISTS experiences (
                    id TEXT PRIMARY KEY,
                    restaurant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    payment_required INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS people (
                    id TEXT PRIMARY KEY,
                    first_name TEXT DEFAULT '',
                    last_name TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    email TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS bookings (
                    id TEXT PRIMARY KEY,
                    restaurant_id TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    experience_id TEXT DEFAULT '',
                    size INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    time TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    locale TEXT DEFAULT 'en',
                    modification_restricted INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            self._conn.commit()

    def seed(self) -> None:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) AS n FROM restaurants")
            if cur.fetchone()["n"]:
                return
            self._conn.execute(
                "INSERT INTO restaurants (id, name, locality, timezone) VALUES (?,?,?,?)",
                (RESTAURANT_ID, "Yen", "Montreal", "America/Toronto"),
            )
            for exp_id, name, _slots, pay in _SEATING_PLAN:
                self._conn.execute(
                    "INSERT INTO experiences (id, restaurant_id, name, payment_required)"
                    " VALUES (?,?,?,?)",
                    (exp_id, RESTAURANT_ID, name, 1 if pay else 0),
                )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- generic helpers ----------------------------------------------------
    def _one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _exec(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    # -- restaurants / experiences -----------------------------------------
    def get_restaurant(self, restaurant_id: str) -> sqlite3.Row | None:
        return self._one("SELECT * FROM restaurants WHERE id = ?", (restaurant_id,))

    def list_restaurants(self) -> list[sqlite3.Row]:
        return self._all("SELECT * FROM restaurants ORDER BY name")

    def get_experience(self, experience_id: str) -> sqlite3.Row | None:
        return self._one("SELECT * FROM experiences WHERE id = ?", (experience_id,))

    # -- people -------------------------------------------------------------
    def get_person(self, person_id: str) -> sqlite3.Row | None:
        return self._one("SELECT * FROM people WHERE id = ?", (person_id,))

    def find_person_by_phone(self, phone: str) -> sqlite3.Row | None:
        if not phone:
            return None
        return self._one("SELECT * FROM people WHERE phone = ?", (phone,))

    def upsert_person(
        self, *, first_name="", last_name="", phone="", email=""
    ) -> sqlite3.Row:
        existing = self.find_person_by_phone(phone) if phone else None
        if existing:
            return existing
        pid = _gen_id("person")
        self._exec(
            "INSERT INTO people (id, first_name, last_name, phone, email)"
            " VALUES (?,?,?,?,?)",
            (pid, first_name, last_name, phone, email),
        )
        return self.get_person(pid)

    def update_person(self, person_id: str, **fields) -> sqlite3.Row | None:
        person = self.get_person(person_id)
        if not person:
            return None
        cols = {k: v for k, v in fields.items() if v is not None}
        if cols:
            assignments = ", ".join(f"{k} = ?" for k in cols)
            self._exec(
                f"UPDATE people SET {assignments} WHERE id = ?",
                (*cols.values(), person_id),
            )
        return self.get_person(person_id)

    # -- bookings -----------------------------------------------------------
    def get_booking(self, booking_id: str) -> sqlite3.Row | None:
        return self._one("SELECT * FROM bookings WHERE id = ?", (booking_id,))

    def list_bookings_for_phone(self, phone: str) -> list[sqlite3.Row]:
        return self._all(
            "SELECT b.* FROM bookings b JOIN people p ON p.id = b.person_id"
            " WHERE p.phone = ? ORDER BY b.time DESC",
            (phone,),
        )

    def seated_count(self, restaurant_id: str, time: str) -> int:
        """Total confirmed party size already booked at a given slot time."""
        row = self._one(
            "SELECT COALESCE(SUM(size), 0) AS n FROM bookings"
            " WHERE restaurant_id = ? AND time = ? AND status = 'confirmed'",
            (restaurant_id, time),
        )
        return int(row["n"]) if row else 0

    def insert_booking(
        self,
        *,
        restaurant_id: str,
        person_id: str,
        experience_id: str,
        size: int,
        time: str,
        note: str = "",
        locale: str = "en",
        modification_restricted: bool = False,
    ) -> sqlite3.Row:
        bid = _gen_id("booking")
        self._exec(
            "INSERT INTO bookings (id, restaurant_id, person_id, experience_id,"
            " size, status, time, note, locale, modification_restricted)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                bid,
                restaurant_id,
                person_id,
                experience_id,
                size,
                "confirmed",
                time,
                note,
                locale,
                1 if modification_restricted else 0,
            ),
        )
        return self.get_booking(bid)

    def update_booking(self, booking_id: str, **fields) -> sqlite3.Row | None:
        booking = self.get_booking(booking_id)
        if not booking:
            return None
        cols = {k: v for k, v in fields.items() if v is not None}
        if cols:
            assignments = ", ".join(f"{k} = ?" for k in cols)
            self._exec(
                f"UPDATE bookings SET {assignments} WHERE id = ?",
                (*cols.values(), booking_id),
            )
        return self.get_booking(booking_id)


# -- availability generation (pure, no DB writes) ---------------------------

def slot_label(iso_time: str) -> str:
    """Render '...T18:30:00-04:00' as '6:30 PM'."""
    hh, mm = iso_time[11:13], iso_time[14:16]
    hour = int(hh)
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{mm} {suffix}"


def generate_slots(date: str) -> list[dict]:
    """All seatings configured for ``date`` (YYYY-MM-DD), before capacity checks."""
    slots: list[dict] = []
    for exp_id, name, times, pay in _SEATING_PLAN:
        for hhmm in times:
            slots.append(
                {
                    "time": f"{date}T{hhmm}:00{TZ_OFFSET}",
                    "experience_id": exp_id,
                    "experience_name": name,
                    "payment_required": pay,
                }
            )
    return slots


def is_past(iso_time: str, *, now: dt.datetime | None = None) -> bool:
    try:
        when = dt.datetime.fromisoformat(iso_time)
    except ValueError:
        return False
    now = now or dt.datetime.now(dt.timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when < now
