"""End-to-end tests of the ReservationService against the in-process mock.

These exercise the full JSON:API client -> mock -> SQLite path, the same code
that will run against real Libro (only base URL + auth differ).
"""

from __future__ import annotations

import pytest

from yen_agent.reservation.errors import (
    NotCancelableError,
    PartySizeOutOfRangeError,
    SlotUnavailableError,
)
from yen_agent.reservation.models import Availability, Booking
from tests.conftest import future_date, slot_time


async def test_check_availability_returns_slots(service):
    avail = await service.check_availability(future_date(), 2)
    assert isinstance(avail, Availability)
    assert avail.is_available
    assert all(s.time and s.label and s.experience_name for s in avail.slots)
    # Labels are human-spoken, e.g. "6:00 PM".
    assert any(s.label.endswith("PM") for s in avail.slots)


async def test_party_size_out_of_range_raises(service):
    with pytest.raises(PartySizeOutOfRangeError) as exc:
        await service.check_availability(future_date(), 50)
    assert exc.value.code == "2005"


async def test_book_lookup_reschedule_cancel_roundtrip(service):
    date = future_date()
    booking = await service.create_booking(
        time=slot_time(date, "18:30"),
        party_size=2,
        first_name="Jordan",
        phone="+15145551111",
        note="window seat",
    )
    assert isinstance(booking, Booking)
    assert booking.status == "confirmed"
    assert booking.size == 2
    assert booking.experience_name in ("Dinner", "Tasting Menu")

    # Lookup by phone finds it.
    found = await service.list_bookings(phone="+15145551111")
    assert [b.id for b in found] == [booking.id]

    # Reschedule to another open time.
    moved = await service.reschedule_booking(booking.id, new_time=slot_time(date, "20:30"))
    assert moved.time == slot_time(date, "20:30")

    # Cancel it.
    cancelled = await service.cancel_booking(booking.id)
    assert cancelled.is_cancelled

    # Re-cancelling is not allowed.
    with pytest.raises(NotCancelableError):
        await service.cancel_booking(booking.id)


async def test_book_unavailable_time_raises(service):
    with pytest.raises(SlotUnavailableError):
        await service.create_booking(
            time=slot_time(future_date(), "02:00"),  # not a seating
            party_size=2,
            first_name="Pat",
            phone="+15145552222",
        )


async def test_capacity_exhaustion_removes_slot(service):
    """Filling a slot to capacity removes it from availability and blocks booking."""
    date = future_date()
    time = slot_time(date, "17:00")
    # Capacity is 24; fill with two parties of 12.
    for i in range(2):
        await service.create_booking(
            time=time, party_size=12, first_name=f"G{i}", phone=f"+1514000000{i}"
        )
    avail = await service.check_availability(date, 2)
    assert time not in [s.time for s in avail.slots]
    with pytest.raises(SlotUnavailableError):
        await service.create_booking(
            time=time, party_size=2, first_name="Late", phone="+15140009999"
        )


async def test_person_create_and_update(service):
    date = future_date()
    booking = await service.create_booking(
        time=slot_time(date, "19:00"), party_size=2,
        first_name="Robin", phone="+15145553333", email="robin@example.com",
    )
    person = await service.get_person(booking.person_id)
    assert person.phone == "+15145553333"
    updated = await service.update_person(person.id, last_name="Lee")
    assert updated.last_name == "Lee"


async def test_payment_intent(service):
    date = future_date()
    booking = await service.create_booking(
        time=slot_time(date, "18:00"), party_size=2,
        first_name="Max", phone="+15145554444",
    )
    intent = await service.init_payment_intent(booking_id=booking.id, amount=5000)
    assert intent.amount == 5000
    assert intent.currency == "CAD"
    assert intent.payment_url
