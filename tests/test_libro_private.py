"""Offline tests for the Libro private (dashboard API) adapter.

The live wire shapes are unconfirmed (see scripts/probe_libro_private.py), so
these cover what we can verify without the network: construction/auth, that the
class fully implements the ReservationService interface, and that the tolerant
parsers handle the plausible key spellings (dash-case / underscore / camelCase).
"""

from __future__ import annotations

import pytest

from yen_agent.reservation.base import ReservationService
from yen_agent.reservation.libro_private import LibroPrivateReservationService


def _svc() -> LibroPrivateReservationService:
    return LibroPrivateReservationService(
        token="fake-token", email="owner@example.com", restaurant_id="8169"
    )


def test_requires_token_and_email():
    with pytest.raises(ValueError):
        LibroPrivateReservationService(token="", email="", restaurant_id="8169")


def test_is_a_concrete_reservation_service():
    svc = _svc()
    assert isinstance(svc, ReservationService)  # all abstract methods implemented


def test_auth_header_format():
    svc = _svc()
    auth = svc._client.headers["Authorization"]
    assert auth == 'Token token="fake-token", email="owner@example.com"'
    assert svc._client.headers["Accept"] == "application/vnd.libro-private-v2+json"


def test_parse_booking_jsonapi():
    svc = _svc()
    # JSON:API envelope as returned by the real dashboard API.
    b = svc._parse_booking({"data": {
        "type": "bookings", "id": "555",
        "attributes": {"slots": 4, "status": "approved",
                       "time": "2026-08-15T19:00:00-04:00", "table-number": "12",
                       "note": "window"},
        "relationships": {
            "person": {"data": {"type": "people", "id": "99"}},
            "service": {"data": {"type": "services", "id": "7"}},
        },
    }})
    assert (b.id, b.size, b.status, b.person_id) == ("555", 4, "approved", "99")
    assert b.experience_id == "7"  # the service (shift) id
    assert b.tables == ("12",)
    assert b.time.startswith("2026-08-15")


def test_parse_booking_normalizes_canceled():
    svc = _svc()
    b = svc._parse_booking({"data": {
        "type": "bookings", "id": "7",
        "attributes": {"slots": 2, "status": "canceled",
                       "time": "2026-08-15T18:00:00-04:00"},
    }})
    assert b.status == "cancelled" and b.is_cancelled


def test_parse_person_jsonapi():
    svc = _svc()
    p = svc._parse_person({"data": {
        "type": "people", "id": "3",
        "attributes": {"first-name": "Alex", "last-name": "Kim",
                       "phone": "+15145551234", "email": "a@b.co"},
    }})
    assert p.first_name == "Alex" and p.last_name == "Kim"
    assert p.phone == "+15145551234" and p.id == "3"


async def test_availability_parses_nested_map(monkeypatch):
    """The real /availabilities/{date} returns time -> party-size -> {area: count}."""
    svc = _svc()

    async def fake_request(method, path, *, json=None, params=None):
        assert method == "GET" and path == "/availabilities/2026-07-24"
        return {
            "2026-07-24T17:15:00-04:00": {"2": {"": 17}, "4": {"": 5}, "6": {"": 1}},
            "2026-07-24T17:45:00-04:00": {"2": {"": 14}, "4": {"": 4}, "6": {}},
        }

    monkeypatch.setattr(svc, "_request", fake_request)
    avail = await svc.check_availability("2026-07-24", 6)
    # Party of 6 is open at 17:15 (count 1) but full at 17:45 (empty {}).
    times = [s.time for s in avail.slots]
    assert times == ["2026-07-24T17:15:00-04:00"]
    assert avail.slots[0].label == "5:15 PM"
    await svc.aclose()


async def test_service_lookup_is_non_fatal(monkeypatch):
    """If /services fails, booking still proceeds (server infers the shift)."""
    from yen_agent.reservation.errors import BookingNotFoundError

    svc = _svc()

    async def boom(method, path, *, json=None, params=None):
        raise BookingNotFoundError()

    monkeypatch.setattr(svc, "_request", boom)
    assert await svc._service_id_for_time("2026-07-24", "2026-07-24T19:30:00-04:00") == ""
    await svc.aclose()


async def test_availability_large_party_escalates():
    from yen_agent.reservation.errors import LargePartyError

    svc = _svc()
    with pytest.raises(LargePartyError):
        await svc.check_availability("2026-07-24", 8)  # >6 = staff
    await svc.aclose()


def test_build_service_selects_private_backend(monkeypatch):
    from yen_agent.config import Settings
    from yen_agent.reservation import build_service

    s = Settings(
        reservation_backend="libro-private",
        libro_private_token="fake", libro_private_email="owner@example.com",
        libro_private_restaurant_id="8169",
    )
    svc = build_service(s)
    assert isinstance(svc, LibroPrivateReservationService)


def test_build_service_private_without_token_errors():
    from yen_agent.config import Settings
    from yen_agent.reservation import build_service

    s = Settings(reservation_backend="libro-private", libro_private_token="",
                 libro_private_email="")
    with pytest.raises(ValueError):
        build_service(s)
