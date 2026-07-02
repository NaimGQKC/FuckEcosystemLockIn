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
        msg = await c.cancel_reservation(phone="+15145550000")  # valid but unknown
        assert "don't see" in msg.lower()
    finally:
        await c.service.aclose()


async def test_natural_language_date_is_resolved():
    import datetime as dt
    from yen_agent.concierge import Concierge
    from yen_agent.reservation.mock import MockReservationService

    # Pin "today" to a Wednesday so "this Friday" is deterministic and open.
    svc = MockReservationService.in_process(db_path=":memory:")
    c = Concierge(svc, today=dt.date(2026, 7, 1))
    try:
        msg = await c.check_availability(date="this Friday", party_size=2, part_of_day="dinner")
        assert "PM" in msg  # resolved to a real date with dinner slots
        assert c.state.last_date == "2026-07-03"
    finally:
        await svc.aclose()


async def test_past_date_is_refused_gracefully():
    import datetime as dt
    from yen_agent.concierge import Concierge
    from yen_agent.reservation.mock import MockReservationService

    svc = MockReservationService.in_process(db_path=":memory:")
    c = Concierge(svc, today=dt.date(2026, 7, 1))
    try:
        msg = await c.check_availability(date="2026-06-01", party_size=2)
        assert "passed" in msg.lower()
    finally:
        await svc.aclose()


async def test_phone_is_normalized_and_remembered():
    c = await make_concierge()
    try:
        date = future_date()
        # Give the phone in messy human format at booking.
        await c.book_reservation(
            time=slot_time(date, "19:00"), party_size=2,
            first_name="Riley", phone="(514) 555-7788",
        )
        assert c.state.phone == "+15145557788"
        # Cancel later WITHOUT repeating the number — state carries it.
        msg = await c.cancel_reservation()
        assert "cancelled" in msg.lower()
    finally:
        await c.service.aclose()


async def test_booking_without_any_phone_asks_for_it():
    c = await make_concierge()
    try:
        date = future_date()
        msg = await c.book_reservation(
            time=slot_time(date, "19:00"), party_size=2, first_name="NoPhone", phone="",
        )
        assert "phone number" in msg.lower()
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


async def test_large_party_is_spoken_as_escalation():
    c = await make_concierge()
    try:
        msg = await c.check_availability(date=future_date(), party_size=40)
        # Should surface the friendly "we'll arrange with the team" message, not raise.
        assert "team" in msg.lower() and "raise" not in msg.lower()
        assert "name" in msg.lower() or "message" in msg.lower()
    finally:
        await c.service.aclose()


async def test_merge_is_mentioned_for_large_party():
    c = await make_concierge()
    try:
        msg = await c.check_availability(date=future_date(), party_size=8)
        assert "combined table" in msg.lower()
    finally:
        await c.service.aclose()


async def test_booking_merged_table_is_announced():
    c = await make_concierge()
    try:
        date = future_date()
        msg = await c.book_reservation(
            time=slot_time(date, "19:00"), party_size=8,
            first_name="Group", phone="+15145552000",
        )
        assert "combine" in msg.lower()
    finally:
        await c.service.aclose()


async def test_faq_known_and_unknown():
    c = await make_concierge()
    try:
        assert "lunch" in c.answer_faq(topic="hours").lower()
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
