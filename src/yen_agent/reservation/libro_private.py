"""LibroPrivateReservationService — the *private* dashboard API dialect.

Based on a network analysis of dashboard.libroreserve.com (July 2026):

  Base:    https://api.libroreserve.com
  Accept:  application/vnd.libro-private-v2+json
  Auth:    Authorization: Token token="<TOKEN>", email="<EMAIL>"   (static, long-lived)

  GET  /ping                          liveness
  GET  /availabilities?restaurant-id=&started-on=YYYY-MM-DD&slots=N
  GET  /people/query?query=<text>     guest search (name or phone)
  POST /people                        create guest
  POST /bookings                      create reservation ("booking", party size = `slots`)
  GET  /bookings/:id
  PATCH /bookings/:id                 update (incl. status -> canceled)

IMPORTANT — payload shapes for POST /bookings and the /availabilities response
were NOT captured live (doing so would have written to the production floor).
The mappings below are best-effort from the app's Ember Data models and are
concentrated in the _parse_* / _booking_payload helpers so that one capture
pass (see scripts/probe_libro_private.py, read-only) plus one controlled test
booking can finalize them without touching the agent above this layer.

Security: the token is a de-facto master credential for the restaurant's
reservations. Load it from the environment only; never log it, never commit it.
This is also an undocumented internal API — it may change without notice
(especially during the OpenTable migration), and official partner access
remains the better long-term path.
"""

from __future__ import annotations

import httpx

from .base import ReservationService
from .errors import (
    BookingNotFoundError,
    ReservationError,
    SlotUnavailableError,
)
from .models import Availability, Booking, PaymentIntent, Person, TimeSlot

ACCEPT = "application/vnd.libro-private-v2+json"
#: Tag phone-agent bookings so staff can see where they came from.
BOOKING_SOURCE = "phone-agent"


def _slot_label(iso_time: str) -> str:
    try:
        hour = int(iso_time[11:13])
        minute = iso_time[14:16]
    except (ValueError, IndexError):
        return iso_time
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour % 12 or 12}:{minute} {suffix}"


def _get(d: dict, *keys, default=None):
    """Fetch the first present key — tolerates dash-case/underscore/camelCase."""
    for k in keys:
        if k in d:
            return d[k]
    return default


class LibroPrivateReservationService(ReservationService):
    def __init__(
        self,
        *,
        token: str,
        email: str,
        restaurant_id: str,
        base_url: str = "https://api.libroreserve.com",
        timeout: float = 15.0,
    ):
        if not token or not email:
            raise ValueError(
                "LIBRO_PRIVATE_TOKEN and LIBRO_PRIVATE_EMAIL must be set for the "
                "libro-private backend."
            )
        self._restaurant_id = str(restaurant_id)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Accept": ACCEPT,
                "Authorization": f'Token token="{token}", email="{email}"',
            },
        )

    # -- low-level ---------------------------------------------------------
    async def _request(self, method: str, path: str, *, json: dict | None = None,
                       params: dict | None = None) -> dict | list:
        resp = await self._client.request(method, path, json=json, params=params)
        body: dict | list | None
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code == 404:
            raise BookingNotFoundError(detail=str(body)[:200])
        if resp.status_code == 422:
            # Over-capacity / invalid slot — the concurrency case from the
            # analysis: a walk-in may take the table between check and create.
            raise SlotUnavailableError(detail=str(body)[:200])
        if resp.status_code >= 400:
            raise ReservationError(
                f"Libro private API error (HTTP {resp.status_code})",
                detail=str(body)[:200],
            )
        return body if body is not None else {}

    # -- parsing (tolerant; finalize after the capture pass) ---------------
    def _parse_booking(self, raw: dict) -> Booking:
        b = raw.get("booking", raw) if isinstance(raw, dict) else {}
        person = _get(b, "person", default={}) or {}
        person_id = person.get("id", "") if isinstance(person, dict) else str(person)
        status = str(_get(b, "status", default="")).lower()
        return Booking(
            id=str(_get(b, "id", default="")),
            size=int(_get(b, "slots", "party-size", "party_size", default=0) or 0),
            status="cancelled" if status in ("canceled", "cancelled") else (status or "confirmed"),
            time=str(_get(b, "started-at", "started_at", "startedAt", "time", default="")),
            restaurant_id=self._restaurant_id,
            person_id=str(person_id or _get(b, "person-id", "person_id", default="")),
            note=str(_get(b, "note", default="") or ""),
            locale=str(_get(b, "locale", default="en") or "en"),
            tables=tuple(
                str(t) for t in (_get(b, "table-number", "table_number", "tableNumber",
                                      default="") or "").split(",") if t
            ),
        )

    @staticmethod
    def _parse_person(raw: dict) -> Person:
        p = raw.get("person", raw) if isinstance(raw, dict) else {}
        return Person(
            id=str(_get(p, "id", default="")),
            first_name=str(_get(p, "first-name", "first_name", "firstName", default="") or ""),
            last_name=str(_get(p, "last-name", "last_name", "lastName", default="") or ""),
            phone=str(_get(p, "phone", "formatted-phone", "formattedPhone", default="") or ""),
            email=str(_get(p, "email", default="") or ""),
        )

    # -- ReservationService API -------------------------------------------
    async def check_availability(self, date: str, party_size: int) -> Availability:
        body = await self._request(
            "GET", "/availabilities",
            params={
                "restaurant-id": self._restaurant_id,
                "started-on": date,
                "slots": party_size,
            },
        )
        # Tolerate the plausible envelope shapes until the capture pass:
        # {"availabilities": [...]}, {"data": [...]}, or a bare list of slots.
        if isinstance(body, dict):
            raw_slots = _get(body, "availabilities", "data", default=[]) or []
        else:
            raw_slots = body or []
        slots: list[TimeSlot] = []
        for s in raw_slots:
            if not isinstance(s, dict):
                continue
            time = str(_get(s, "started-at", "started_at", "startedAt", "time", default=""))
            if not time:
                continue
            slots.append(
                TimeSlot(
                    time=time,
                    label=_slot_label(time),
                    experience_id=str(_get(s, "service-id", "service_id", default="")),
                    experience_name=str(_get(s, "service-name", "service_name",
                                             "service", default="") or ""),
                )
            )
        return Availability(date=date, party_size=party_size, slots=slots)

    async def _find_or_create_person(
        self, *, first_name: str, last_name: str, phone: str, email: str
    ) -> str:
        """Return a person id, matching by phone first to avoid duplicates."""
        if phone:
            found = await self._request("GET", "/people/query", params={"query": phone})
            people = found if isinstance(found, list) else \
                _get(found, "people", "data", default=[]) or []
            for p in people:
                if isinstance(p, dict) and p.get("id"):
                    return str(p["id"])
        created = await self._request(
            "POST", "/people",
            json={"person": {
                "first-name": first_name,
                "last-name": last_name,
                "phone": phone,
                "email": email,
            }},
        )
        return self._parse_person(created if isinstance(created, dict) else {}).id

    async def create_booking(
        self, *, time: str, party_size: int, first_name: str, last_name: str = "",
        phone: str = "", email: str = "", note: str = "", locale: str = "en",
        experience_id: str = "",
    ) -> Booking:
        person_id = await self._find_or_create_person(
            first_name=first_name, last_name=last_name, phone=phone, email=email
        )
        payload = {
            "booking": {
                "restaurant-id": self._restaurant_id,
                "started-at": time,
                "slots": party_size,
                "person-id": person_id,
                "note": note,
                "source": BOOKING_SOURCE,
                "locale": locale,
            }
        }
        if experience_id:
            payload["booking"]["service-id"] = experience_id
        body = await self._request("POST", "/bookings", json=payload)
        return self._parse_booking(body if isinstance(body, dict) else {})

    async def get_booking(self, booking_id: str) -> Booking:
        body = await self._request("GET", f"/bookings/{booking_id}")
        return self._parse_booking(body if isinstance(body, dict) else {})

    async def list_bookings(self, *, phone: str = "", person_id: str = "") -> list[Booking]:
        params: dict = {"restaurant-id": self._restaurant_id}
        if person_id:
            params["person-id"] = person_id
        elif phone:
            # Resolve the guest first, then their bookings.
            found = await self._request("GET", "/people/query", params={"query": phone})
            people = found if isinstance(found, list) else \
                _get(found, "people", "data", default=[]) or []
            if not people:
                return []
            params["person-id"] = str(people[0].get("id", ""))
        body = await self._request("GET", "/bookings", params=params)
        raw = body if isinstance(body, list) else _get(body, "bookings", "data", default=[]) or []
        return [self._parse_booking(b) for b in raw if isinstance(b, dict)]

    async def update_booking(
        self, booking_id: str, *, party_size: int | None = None, note: str | None = None
    ) -> Booking:
        attrs: dict = {}
        if party_size is not None:
            attrs["slots"] = party_size
        if note is not None:
            attrs["note"] = note
        body = await self._request(
            "PATCH", f"/bookings/{booking_id}", json={"booking": attrs}
        )
        return self._parse_booking(body if isinstance(body, dict) else {})

    async def cancel_booking(self, booking_id: str) -> Booking:
        body = await self._request(
            "PATCH", f"/bookings/{booking_id}", json={"booking": {"status": "canceled"}}
        )
        return self._parse_booking(body if isinstance(body, dict) else {})

    async def reschedule_booking(self, booking_id: str, *, new_time: str) -> Booking:
        body = await self._request(
            "PATCH", f"/bookings/{booking_id}", json={"booking": {"started-at": new_time}}
        )
        return self._parse_booking(body if isinstance(body, dict) else {})

    async def get_person(self, person_id: str) -> Person:
        body = await self._request("GET", f"/people/{person_id}")
        return self._parse_person(body if isinstance(body, dict) else {})

    async def update_person(
        self, person_id: str, *, first_name: str | None = None,
        last_name: str | None = None, phone: str | None = None, email: str | None = None,
    ) -> Person:
        attrs: dict = {}
        if first_name is not None:
            attrs["first-name"] = first_name
        if last_name is not None:
            attrs["last-name"] = last_name
        if phone is not None:
            attrs["phone"] = phone
        if email is not None:
            attrs["email"] = email
        body = await self._request("PATCH", f"/people/{person_id}", json={"person": attrs})
        return self._parse_person(body if isinstance(body, dict) else {})

    async def init_payment_intent(
        self, *, booking_id: str, amount: int, currency: str = "CAD"
    ) -> PaymentIntent:
        # Deposits go through Moneris in the private dialect; not needed for the
        # phone-agent MVP. Surface a clear error rather than guessing.
        raise ReservationError(
            "Deposits are not supported via the private API adapter yet.",
            spoken_message=(
                "I can't set up a deposit over the phone yet — I'll note it and "
                "the team will follow up if one is needed."
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
