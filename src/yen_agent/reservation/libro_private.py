"""LibroPrivateReservationService — the real Libro dashboard API (id 8169).

Wire format confirmed from live dashboard traffic (24 Jul 2026), not guesses:

  Base:    https://api.libroreserve.com
  Accept:  application/vnd.libro-private-v1+json  (JSON:API endpoints)
           application/vnd.libro-private-v2+json  (/availabilities only)
  Content-Type on writes: application/vnd.api+json
  Auth:    Authorization: Token token="<TOKEN>", email="<EMAIL>"

  GET  /availabilities/{YYYY-MM-DD}?restaurant-id=8169     bookable slots (nested map)
  GET  /services?restaurant-id=8169&started-on={date}      shifts + capacity (JSON:API)
  GET  /people/query?query={text}                          guest autocomplete
  GET/POST /people                                         guest CRUD (JSON:API)
  POST /bookings                                            create reservation (JSON:API)
  GET/PATCH /bookings/{id}                                 read / update / cancel

Availability response is a bare map, e.g.:
  { "2026-07-24T19:30:00-04:00": { "1": {"": 17}, "4": {"": 5}, "6": {} }, ... }
  time -> party-size(str) -> { seatingArea: count }.  Empty {} = full for that size.

A booking's datetime is the `time` attribute (matches the availability keys),
party size is `slots`, and it references a `person` and a `service` (shift) by
relationship. Keys are dash-cased JSON:API.

The exact required-field set / status enum for POST /bookings is the one piece
still derived rather than observed — kept minimal here (time, slots, source,
person, service) and confirmed by a single controlled test booking.

Security: the token is a master credential (env only, never logged/committed).
This is an undocumented internal API and may change without notice.
"""

from __future__ import annotations

import datetime as dt

import httpx

from .base import ReservationService
from .errors import (
    BookingNotFoundError,
    LargePartyError,
    ReservationError,
    SlotUnavailableError,
)
from .models import Availability, Booking, PaymentIntent, Person, TimeSlot

# The API is versioned per-endpoint via the Accept header (confirmed from the
# dashboard's own request headers): availabilities use v2, every JSON:API
# endpoint (people/services/notes/bookings/...) uses v1, and writes send the
# standard JSON:API content type.
ACCEPT_V1 = "application/vnd.libro-private-v1+json"   # default (JSON:API endpoints)
ACCEPT_V2 = "application/vnd.libro-private-v2+json"   # /availabilities only
WRITE_CONTENT_TYPE = "application/vnd.api+json"
#: The services/availability data caps party size at 6 (max-slots); larger = staff.
MAX_ONLINE_PARTY = 6
#: Table turn length. The dashboard conveys the reservation via `expected-leave-at`
#: (start + turn); the server derives the start time from it. 90 min matches the
#: observed avg-seated-time and a live booking (start 19:45Z, leave 21:15Z).
DEFAULT_TURN_MIN = 90

#: Attributes the dashboard sends on a booking PATCH (everything else — `time`,
#: `size`, `source`, lifecycle timestamps — is server-derived/read-only).
_WRITABLE_BOOKING_ATTRS = frozenset({
    "slots", "status", "status-tags", "seating-status", "booking-type",
    "table-number", "note", "private-note", "children", "edit-url", "tags",
    "reduced-mobility", "expected-leave-at", "booking-experience-id",
    "group-number", "group-name", "group-size", "classification-counts",
    "answers", "do-not-move", "deposit-amount", "deposit-charged",
    "deposit-token", "no-show-fee-status", "no-show-fee-status-waived",
    "offer-request-status", "payment-data", "quoted-wait-time",
    "quoted-wait-time-overridden-at",
})


def _slot_label(iso_time: str) -> str:
    try:
        hour, minute = int(iso_time[11:13]), iso_time[14:16]
    except (ValueError, IndexError):
        return iso_time
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour % 12 or 12}:{minute} {suffix}"


def _get(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
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
                "Accept": ACCEPT_V1,  # default; availabilities override to v2
                "Authorization": f'Token token="{token}", email="{email}"',
            },
        )

    # -- low-level ---------------------------------------------------------
    async def _request(self, method: str, path: str, *, json: dict | None = None,
                       params: dict | None = None, accept: str | None = None):
        # restaurant-id is NOT auto-injected: the dashboard only sends it on
        # /availabilities, /services, /notes — adding it elsewhere can 404.
        headers: dict = {}
        if accept:
            headers["Accept"] = accept
        if json is not None:
            headers["Content-Type"] = WRITE_CONTENT_TYPE
        resp = await self._client.request(method, path, json=json, params=params,
                                          headers=headers)
        try:
            body = resp.json()
        except ValueError:
            body = None
        if resp.status_code >= 400:
            where = f"{method} {path}"
            snippet = str(body)[:180].replace("\n", " ")
            if resp.status_code == 404:
                raise BookingNotFoundError(f"404 Not Found at {where}", detail=snippet)
            if resp.status_code in (409, 422):
                # A slot can fill between the availability check and the create.
                raise SlotUnavailableError(f"HTTP {resp.status_code} at {where}",
                                           detail=snippet)
            raise ReservationError(f"HTTP {resp.status_code} at {where}", detail=snippet)
        return body if body is not None else {}

    # -- parsing -----------------------------------------------------------
    def _parse_booking(self, raw) -> Booking:
        r = raw.get("data", raw) if isinstance(raw, dict) else {}
        attrs = r.get("attributes", {}) or {}
        rel = r.get("relationships", {}) or {}

        def _rel_id(name: str) -> str:
            data = (rel.get(name) or {}).get("data") or {}
            return str(data.get("id", "")) if isinstance(data, dict) else ""

        status = str(attrs.get("status", "") or "").lower()
        table = attrs.get("table-number") or ""
        return Booking(
            id=str(r.get("id", "")),
            size=int(attrs.get("slots", 0) or 0),
            status="cancelled" if status in ("canceled", "cancelled") else (status or "confirmed"),
            time=str(attrs.get("time", "") or ""),
            restaurant_id=self._restaurant_id,
            person_id=_rel_id("person"),
            experience_id=_rel_id("service"),
            note=str(attrs.get("note", "") or ""),
            locale=str(attrs.get("locale", "en") or "en"),
            tables=tuple(t for t in str(table).split(",") if t),
        )

    @staticmethod
    def _parse_person(raw) -> Person:
        r = raw.get("data", raw) if isinstance(raw, dict) else {}
        attrs = r.get("attributes", {}) or {}
        return Person(
            id=str(r.get("id", "")),
            first_name=str(attrs.get("first-name", "") or ""),
            last_name=str(attrs.get("last-name", "") or ""),
            phone=str(attrs.get("phone", "") or ""),
            email=str(attrs.get("email", "") or ""),
        )

    # -- availability ------------------------------------------------------
    async def check_availability(self, date: str, party_size: int) -> Availability:
        if party_size > MAX_ONLINE_PARTY:
            raise LargePartyError()
        body = await self._request("GET", f"/availabilities/{date}",
                                   params={"restaurant-id": self._restaurant_id},
                                   accept=ACCEPT_V2)
        slots: list[TimeSlot] = []
        if isinstance(body, dict):
            for ts, size_map in body.items():
                if not isinstance(size_map, dict):
                    continue
                area = size_map.get(str(party_size))
                count = 0
                if isinstance(area, dict):
                    count = sum(int(v) for v in area.values() if isinstance(v, (int, float)))
                if count > 0:
                    slots.append(TimeSlot(
                        time=ts, label=_slot_label(ts),
                        experience_id="", experience_name="", seats=party_size,
                    ))
        slots.sort(key=lambda s: s.time)
        return Availability(date=date, party_size=party_size, slots=slots)

    async def _service_id_for_time(self, date: str, time: str) -> str:
        """Return the service whose start EXACTLY matches ``time``.

        Ground truth (from a captured 201 create): a "service" is one 15-minute
        seating slot, not a shift — the day returns ~39 of them. The booking's
        datetime is derived from the referenced service's ``started-at`` (a live
        booking at 19:45Z referenced the service started-at 19:45Z, and `time` is
        never sent). Referencing the wrong one yields 422 code 1006
        "You must select a date & time".

        Status is deliberately NOT filtered: that live booking used a service
        marked "closed" (staff may book outside online hours).

        ``date`` is the restaurant-local date; slots may cross into the next UTC
        day, which the API handles.
        """
        want = _parse_dt(time)
        if want is None:
            return ""
        try:
            body = await self._request("GET", "/services", params={
                "restaurant-id": self._restaurant_id, "started-on": date,
                "only-services": "true",
            })
        except ReservationError:
            return ""
        for s in (body.get("data", []) if isinstance(body, dict) else []):
            started = _parse_dt((s.get("attributes") or {}).get("started-at", ""))
            if started is not None and started == want:
                return str(s.get("id", ""))
        return ""

    # -- guest -------------------------------------------------------------
    async def _find_or_create_person(self, *, first_name, last_name, phone, email,
                                     locale="en") -> str:
        if phone:
            res = await self._request("GET", "/people/query", params={"query": phone})
            people = res.get("data", []) if isinstance(res, dict) else (res or [])
            for p in people:
                pid = p.get("id") if isinstance(p, dict) else None
                if pid:
                    return str(pid)
        payload = {"data": {"type": "people", "attributes": {
            "first-name": first_name, "last-name": last_name,
            "phone": phone, "phone-country": "CA", "phone-type": "mobile",
            "email": email, "locale": locale,
        }}}
        body = await self._request("POST", "/people", json=payload)
        return self._parse_person(body).id

    # -- bookings ----------------------------------------------------------
    async def create_booking(
        self, *, time: str, party_size: int, first_name: str, last_name: str = "",
        phone: str = "", email: str = "", note: str = "", locale: str = "en",
        experience_id: str = "",
    ) -> Booking:
        if party_size > MAX_ONLINE_PARTY:
            raise LargePartyError()
        person_id = await self._find_or_create_person(
            first_name=first_name, last_name=last_name, phone=phone,
            email=email, locale=locale,
        )
        service_id = experience_id or await self._service_id_for_time(time[:10], time)
        if not service_id:
            # The service *is* the slot; without it the server has no date/time.
            raise SlotUnavailableError(
                f"No seating slot (service) at {time}",
                detail="No service record matches that exact start time.",
            )
        start = _parse_dt(time)
        leave_iso = (
            (start + dt.timedelta(minutes=DEFAULT_TURN_MIN)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if start else time
        )
        # Mirror the dashboard's captured create payload field-for-field. `time`
        # is server-derived (from the service) and must not be sent.
        attributes = {
            "slots": party_size,
            "status": "approved",
            "status-tags": "",
            "seating-status": "",
            "booking-type": "reservation",
            "table-number": "",
            "note": note or "",
            "private-note": "",
            "children": False,
            "edit-url": None,
            "tags": [],
            "reduced-mobility": False,
            "expected-leave-at": leave_iso,
            "booking-experience-id": None,
            "group-number": None,
            "group-name": None,
            "group-size": None,
            "answers": [],
            "do-not-move": False,
            "deposit-amount": 0,
            "deposit-charged": False,
            "deposit-token": None,
            "no-show-fee-status": "",
            "no-show-fee-status-waived": "false",
            "offer-request-status": None,
            "payment-data": None,
            "quoted-wait-time": 900,
            "quoted-wait-time-overridden-at": None,
        }
        payload = {"data": {
            "type": "bookings",
            "attributes": attributes,
            "relationships": {
                "service": {"data": {"type": "services", "id": service_id}},
                "person": {"data": {"type": "people", "id": person_id}},
                "restaurant": {"data": {"type": "restaurants",
                                        "id": self._restaurant_id}},
            },
        }}
        body = await self._request("POST", "/bookings", json=payload)
        return self._parse_booking(body)

    async def get_booking(self, booking_id: str) -> Booking:
        return self._parse_booking(await self._request("GET", f"/bookings/{booking_id}"))

    async def list_bookings(self, *, phone: str = "", person_id: str = "") -> list[Booking]:
        """Best-effort: the dashboard capture didn't include a list-by-guest call,
        so resolve the person and read their included bookings; empty on failure."""
        if not person_id and phone:
            res = await self._request("GET", "/people/query", params={"query": phone})
            people = res.get("data", []) if isinstance(res, dict) else (res or [])
            person_id = str(people[0].get("id", "")) if people else ""
        if not person_id:
            return []
        try:
            body = await self._request("GET", f"/people/{person_id}",
                                       params={"include": "bookings"})
        except ReservationError:
            return []
        included = body.get("included", []) if isinstance(body, dict) else []
        return [self._parse_booking({"data": r}) for r in included
                if isinstance(r, dict) and r.get("type") == "bookings"]

    async def update_booking(self, booking_id: str, *, party_size: int | None = None,
                             note: str | None = None) -> Booking:
        attrs: dict = {}
        if party_size is not None:
            attrs["slots"] = party_size
        if note is not None:
            attrs["note"] = note
        return await self._patch_booking(booking_id, attrs=attrs)

    async def _patch_booking(self, booking_id: str, *, attrs: dict,
                             relationships: dict | None = None) -> Booking:
        """Echo the booking back with changes applied, as the dashboard does.

        The dashboard PATCHes the record's full attribute set, so we read the
        current booking and resend the writable fields with our changes merged —
        avoiding any chance of blanking server-side state with a partial update.
        """
        current: dict = {}
        try:
            got = await self._request("GET", f"/bookings/{booking_id}")
            current = (got.get("data", {}) or {}) if isinstance(got, dict) else {}
        except ReservationError:
            current = {}
        merged = {k: v for k, v in (current.get("attributes") or {}).items()
                  if k in _WRITABLE_BOOKING_ATTRS}
        merged.update(attrs)

        rels = {k: v for k, v in (current.get("relationships") or {}).items()
                if k in ("service", "person", "restaurant")}
        rels.update(relationships or {})
        rels.setdefault("restaurant", {"data": {"type": "restaurants",
                                                "id": self._restaurant_id}})

        payload = {"data": {"type": "bookings", "id": str(booking_id),
                            "attributes": merged, "relationships": rels}}
        return self._parse_booking(
            await self._request("PATCH", f"/bookings/{booking_id}", json=payload))

    async def cancel_booking(self, booking_id: str) -> Booking:
        return await self._patch_booking(booking_id, attrs={"status": "canceled"})

    async def reschedule_booking(self, booking_id: str, *, new_time: str) -> Booking:
        # The service *is* the slot, so moving a booking means swapping services.
        service_id = await self._service_id_for_time(new_time[:10], new_time)
        if not service_id:
            raise SlotUnavailableError(f"No seating slot (service) at {new_time}")
        start = _parse_dt(new_time)
        attrs = {}
        if start:
            attrs["expected-leave-at"] = (
                start + dt.timedelta(minutes=DEFAULT_TURN_MIN)
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return await self._patch_booking(
            booking_id, attrs=attrs,
            relationships={"service": {"data": {"type": "services", "id": service_id}}},
        )

    # -- people ------------------------------------------------------------
    async def get_person(self, person_id: str) -> Person:
        return self._parse_person(await self._request("GET", f"/people/{person_id}"))

    async def update_person(self, person_id: str, *, first_name=None, last_name=None,
                            phone=None, email=None) -> Person:
        attrs = {}
        if first_name is not None:
            attrs["first-name"] = first_name
        if last_name is not None:
            attrs["last-name"] = last_name
        if phone is not None:
            attrs["phone"] = phone
        if email is not None:
            attrs["email"] = email
        payload = {"data": {"type": "people", "id": str(person_id), "attributes": attrs}}
        return self._parse_person(
            await self._request("PATCH", f"/people/{person_id}", json=payload))

    async def init_payment_intent(self, *, booking_id: str, amount: int,
                                  currency: str = "CAD") -> PaymentIntent:
        raise ReservationError(
            "Deposits are not supported via the private API adapter yet.",
            spoken_message=(
                "I can't set up a deposit over the phone yet — I'll note it and "
                "the team will follow up if one is needed."
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _parse_dt(value: str) -> dt.datetime | None:
    """Parse an ISO-8601 timestamp (handles the trailing 'Z') into aware UTC."""
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)
