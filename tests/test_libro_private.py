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


def test_parse_booking_tolerates_key_variants():
    svc = _svc()
    # dash-case with nested person
    b1 = svc._parse_booking({
        "id": 555, "slots": 4, "status": "confirmed",
        "started-at": "2026-08-15T19:00:00-04:00",
        "person": {"id": 99}, "note": "window",
    })
    assert (b1.id, b1.size, b1.status, b1.person_id) == ("555", 4, "confirmed", "99")
    assert b1.time.startswith("2026-08-15")

    # camelCase with canceled status normalized to cancelled
    b2 = svc._parse_booking({"booking": {
        "id": 7, "slots": 2, "status": "canceled", "startedAt": "2026-08-15T18:00:00-04:00",
        "person-id": "42",
    }})
    assert b2.status == "cancelled" and b2.is_cancelled and b2.person_id == "42"


def test_parse_person_tolerates_key_variants():
    svc = _svc()
    p = svc._parse_person({"firstName": "Alex", "last_name": "Kim",
                           "formattedPhone": "(514) 555-1234", "email": "a@b.co", "id": 3})
    assert p.first_name == "Alex" and p.last_name == "Kim"
    assert p.phone == "(514) 555-1234" and p.id == "3"


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
