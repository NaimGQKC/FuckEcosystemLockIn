"""Tests for the Concierge spoken-response orchestration (no LiveKit needed)."""

from __future__ import annotations

from yen_agent.concierge import Concierge
from yen_agent.reservation.mock import MockReservationService
from tests.conftest import future_date, slot_time


async def make_concierge(locale: str = "en") -> Concierge:
    svc = MockReservationService.in_process(db_path=":memory:")
    return Concierge(svc, locale=locale)


async def test_availability_speech_offers_times():
    c = await make_concierge()
    try:
        msg = await c.check_availability(date=future_date(), party_size=2)
        assert "PM" in msg or "AM" in msg
        assert "Which time" in msg
    finally:
        await c.service.aclose()


async def test_booking_flow_speech():
    c = await make_concierge()
    try:
        date = future_date()
        msg = await c.book_reservation(
            time=slot_time(date, "18:30"), party_size=2,
            first_name="Alex", phone="+15145551234",
        )
        assert "all set" in msg.lower()
        assert "Alex" in msg
    finally:
        await c.service.aclose()


async def test_cancel_without_phone_asks_for_it():
    c = await make_concierge()
    try:
        msg = await c.cancel_reservation()
        assert "phone number" in msg.lower()
    finally:
        await c.service.aclose()


async def test_cancel_unknown_phone_is_graceful():
    c = await make_concierge()
    try:
        msg = await c.cancel_reservation(phone="+15140000000")
        assert "don't see" in msg.lower()
    finally:
        await c.service.aclose()


async def test_lookup_and_cancel_by_phone():
    c = await make_concierge()
    try:
        date = future_date()
        await c.book_reservation(
            time=slot_time(date, "19:00"), party_size=4,
            first_name="Sam", phone="+15145557777",
        )
        found = await c.lookup_reservations(phone="+15145557777")
        assert "reservation for 4" in found
        cancelled = await c.cancel_reservation(phone="+15145557777")
        assert "cancelled" in cancelled.lower()
    finally:
        await c.service.aclose()


async def test_party_size_error_is_spoken_gracefully():
    c = await make_concierge()
    try:
        msg = await c.check_availability(date=future_date(), party_size=40)
        # Should surface the friendly out-of-range message, not raise.
        assert "larger group" in msg.lower() or "message" in msg.lower()
    finally:
        await c.service.aclose()


async def test_faq_known_and_unknown():
    c = await make_concierge()
    try:
        assert "open" in c.answer_faq(topic="hours").lower()
        assert "message" in c.answer_faq(topic="does_not_exist").lower()
    finally:
        await c.service.aclose()


async def test_take_message_records():
    c = await make_concierge()
    try:
        msg = c.take_message(name="Chris", phone="+15145558888", message="party of 20")
        assert "Chris" in msg
        assert len(c.messages) == 1
        assert c.messages[0].body == "party of 20"
    finally:
        await c.service.aclose()


async def test_french_locale_booking_summary():
    c = await make_concierge(locale="fr")
    try:
        date = future_date()
        msg = await c.book_reservation(
            time=slot_time(date, "18:30"), party_size=2,
            first_name="Camille", phone="+15145559090",
        )
        # Concierge stores locale 'fr' on the booking; summary uses FR phrasing.
        assert "réservation pour 2" in msg
    finally:
        await c.service.aclose()
