"""LibroPrivateReservationService — the real Libro dashboard API (id 8169).

Wire format confirmed from live dashboard traffic (24 Jul 2026), not guesses:

  Base:    https://api.libroreserve.com
  Accept:  application/vnd.libro-private-v2+json
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

# /availabilities requires this custom media type (plain vnd.api+json 404s it).
# The JSON:API endpoints work with it too, as long as restaurant-id isn't sent
# where the dashboard doesn't send it (that was the real cause of the /people
# 404s, not the Accept header).
ACCEPT = "application/vnd.libro-private-v2+json"
#: The services/availability data caps party size at 6 (max-slots); larger = staff.
MAX_ONLINE_PARTY = 6


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
                "Accept": ACCEPT,
                "Authorization": f'Token token="{token}", email="{email}"',
            },
        )

    # -- low-level ---------------------------------------------------------
    async def _request(self, method: str, path: str, *, json: dict | None = None,
                       params: dict | None = None):
        # restaurant-id is NOT auto-injected: the dashboard only sends it on
        # /availabilities, /services, /notes — adding it elsewhere can 404.
        headers = {"Content-Type": ACCEPT} if json is not None else None
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
                                   params={"restaurant-id": self._restaurant_id})
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
        """Find the shift (service) covering ``time`` — a required booking relationship.

        Services expose ``started-at`` (UTC) but ``expired-at`` is null, so we pick
        the opened service with the latest start at/before the requested time
        (i.e. the shift the slot falls into). Non-fatal: "" on any failure.
        """
        try:
            body = await self._request("GET", "/services", params={
                "restaurant-id": self._restaurant_id, "started-on": date,
                "only-services": "true",
            })
        except ReservationError:
            return ""
        services = body.get("data", []) if isinstance(body, dict) else []
        opened = [s for s in services
                  if str((s.get("attributes") or {}).get("status", "")).lower() == "opened"]
        pool = opened or services

        want = _parse_dt(time)
        best_id, best_start = "", None
        for s in pool:
            start = _parse_dt((s.get("attributes") or {}).get("started-at", ""))
            if start is None:
                continue
            if want is not None and start > want:
                continue  # shift starts after the reservation time
            if best_start is None or start > best_start:
                best_start, best_id = start, str(s.get("id", ""))
        if best_id:
            return best_id
        return str(pool[0].get("id", "")) if pool else ""

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
        # Mirror the fields the dashboard sends on a create (confirmed via HAR).
        attributes = {
            "time": time,
            "slots": party_size,
            "status": "approved",
            "booking-type": "reservation",
        }
        if note:
            attributes["note"] = note
        relationships = {"person": {"data": {"type": "people", "id": person_id}}}
        if service_id:
            relationships["service"] = {"data": {"type": "services", "id": service_id}}
        payload = {"data": {"type": "bookings", "attributes": attributes,
                            "relationships": relationships}}
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
        payload = {"data": {"type": "bookings", "id": str(booking_id), "attributes": attrs}}
        return self._parse_booking(
            await self._request("PATCH", f"/bookings/{booking_id}", json=payload))

    async def cancel_booking(self, booking_id: str) -> Booking:
        payload = {"data": {"type": "bookings", "id": str(booking_id),
                            "attributes": {"status": "canceled"}}}
        return self._parse_booking(
            await self._request("PATCH", f"/bookings/{booking_id}", json=payload))

    async def reschedule_booking(self, booking_id: str, *, new_time: str) -> Booking:
        service_id = await self._service_id_for_time(new_time[:10], new_time)
        attributes = {"time": new_time}
        payload: dict = {"data": {"type": "bookings", "id": str(booking_id),
                                  "attributes": attributes}}
        if service_id:
            payload["data"]["relationships"] = {
                "service": {"data": {"type": "services", "id": service_id}}}
        return self._parse_booking(
            await self._request("PATCH", f"/bookings/{booking_id}", json=payload))

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
