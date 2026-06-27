"""Concierge: provider-agnostic reservation orchestration.

This is the brain behind the agent's tools, kept free of any LiveKit imports so
it is fully unit-testable. Each method returns a short string suitable for the
voice agent to speak, and converts backend errors into graceful spoken
responses. ``tools.py`` is a thin LiveKit wrapper over these methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import faq
from .reservation import (
    Booking,
    ModificationRestrictedError,
    ReservationError,
    ReservationService,
)


@dataclass
class Message:
    """A message taken for the restaurant team (escalation / overflow)."""

    name: str
    phone: str
    body: str


def _booking_summary(b: Booking, *, locale: str = "en") -> str:
    when = _spoken_time(b.time)
    exp = f" ({b.experience_name})" if b.experience_name else ""
    if locale == "fr":
        return f"une réservation pour {b.size} le {when}{exp}"
    return f"a reservation for {b.size} on {when}{exp}"


def _spoken_time(iso_time: str) -> str:
    """Render '2026-06-28T18:30:00-04:00' as 'June 28 at 6:30 PM'."""
    months = [
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
    ]
    try:
        year, month, day = int(iso_time[0:4]), int(iso_time[5:7]), int(iso_time[8:10])
        hour, minute = int(iso_time[11:13]), iso_time[14:16]
    except (ValueError, IndexError):
        return iso_time
    suffix = "AM" if hour < 12 else "PM"
    return f"{months[month - 1]} {day} at {hour % 12 or 12}:{minute} {suffix}"


class Concierge:
    def __init__(self, service: ReservationService, *, locale: str = "en"):
        self.service = service
        self.locale = locale
        self.messages: list[Message] = []

    # -- availability ------------------------------------------------------
    async def check_availability(self, *, date: str, party_size: int) -> str:
        try:
            availability = await self.service.check_availability(date, party_size)
        except ReservationError as exc:
            return exc.spoken_message

        if not availability.is_available:
            return (
                f"I'm sorry, I don't see any open tables for {party_size} on "
                f"{_spoken_time(date + 'T00:00:00')[:-9].strip()}. "
                "Would another day work?"
            )

        labels = [s.label for s in availability.slots]
        # Offer a manageable spoken set rather than reading a long list.
        shown = labels[:5]
        remaining = len(labels) - len(shown)
        if remaining > 0:
            listed = ", ".join(shown) + f", plus {remaining} more times"
        elif len(shown) > 1:
            listed = ", ".join(shown[:-1]) + f", and {shown[-1]}"
        else:
            listed = shown[0]
        more = ""
        pay = any(s.payment_required for s in availability.slots)
        pay_note = (
            " Some seatings, like the tasting menu, may need a card to hold the table."
            if pay else ""
        )
        return (
            f"For {party_size}, I have {listed}{more}. "
            f"Which time would you like?{pay_note}"
        )

    # -- booking -----------------------------------------------------------
    async def book_reservation(
        self,
        *,
        time: str,
        party_size: int,
        first_name: str,
        phone: str,
        last_name: str = "",
        email: str = "",
        note: str = "",
    ) -> str:
        try:
            booking = await self.service.create_booking(
                time=time,
                party_size=party_size,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                note=note,
                locale=self.locale,
            )
        except ReservationError as exc:
            return exc.spoken_message

        confirm = (
            f"You're all set — {_booking_summary(booking, locale=self.locale)}, "
            f"under {first_name}. Is there anything else I can help with?"
        )
        return confirm

    # -- lookup ------------------------------------------------------------
    async def lookup_reservations(self, *, phone: str) -> str:
        try:
            bookings = await self.service.list_bookings(phone=phone)
        except ReservationError as exc:
            return exc.spoken_message

        active = [b for b in bookings if not b.is_cancelled]
        if not active:
            return (
                "I don't see any active reservations under that number. "
                "Would you like to make one?"
            )
        if len(active) == 1:
            return f"I found {_booking_summary(active[0])}. How can I help with it?"
        summaries = "; ".join(_booking_summary(b) for b in active[:3])
        return f"I found a few: {summaries}. Which one did you mean?"

    # -- cancel ------------------------------------------------------------
    async def cancel_reservation(self, *, booking_id: str = "", phone: str = "") -> str:
        booking = await self._resolve_single(booking_id=booking_id, phone=phone)
        if isinstance(booking, str):  # an error/clarification message
            return booking
        if booking.modification_restricted:
            return ModificationRestrictedError().spoken_message
        try:
            cancelled = await self.service.cancel_booking(booking.id)
        except ReservationError as exc:
            return exc.spoken_message
        return (
            f"Done — I've cancelled {_booking_summary(cancelled)}. "
            "Is there anything else?"
        )

    # -- reschedule --------------------------------------------------------
    async def reschedule_reservation(
        self, *, new_time: str, booking_id: str = "", phone: str = ""
    ) -> str:
        booking = await self._resolve_single(booking_id=booking_id, phone=phone)
        if isinstance(booking, str):
            return booking
        if booking.modification_restricted:
            return ModificationRestrictedError().spoken_message
        try:
            updated = await self.service.reschedule_booking(
                booking.id, new_time=new_time
            )
        except ReservationError as exc:
            return exc.spoken_message
        return (
            f"All changed — your reservation is now {_spoken_time(updated.time)}. "
            "Anything else?"
        )

    # -- FAQ ---------------------------------------------------------------
    def answer_faq(self, *, topic: str) -> str:
        ans = faq.answer(topic, locale=self.locale)
        if ans:
            return ans
        return (
            "I'm not sure about that one, but I'd be happy to take a message so "
            "the team can get back to you."
        )

    # -- message taking ----------------------------------------------------
    def take_message(self, *, name: str, phone: str, message: str) -> str:
        self.messages.append(Message(name=name, phone=phone, body=message))
        return (
            f"Got it, {name} — I've passed your message to the team and they'll "
            "get back to you. Is there anything else?"
        )

    # -- helpers -----------------------------------------------------------
    async def _resolve_single(self, *, booking_id: str = "", phone: str = ""):
        """Return a single Booking, or a spoken clarification/error string."""
        if booking_id:
            try:
                return await self.service.get_booking(booking_id)
            except ReservationError as exc:
                return exc.spoken_message
        if phone:
            try:
                bookings = [
                    b for b in await self.service.list_bookings(phone=phone)
                    if not b.is_cancelled
                ]
            except ReservationError as exc:
                return exc.spoken_message
            if not bookings:
                return "I don't see an active reservation under that number."
            if len(bookings) > 1:
                summaries = "; ".join(_booking_summary(b) for b in bookings[:3])
                return (
                    f"You have more than one: {summaries}. "
                    "Which one would you like to change?"
                )
            return bookings[0]
        return "Could you give me the phone number the reservation is under?"
