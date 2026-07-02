"""Concierge: provider-agnostic reservation orchestration.

This is the brain behind the agent's tools, kept free of any LiveKit imports so
it is fully unit-testable. Each method returns a short string suitable for the
voice agent to speak, and converts backend errors into graceful spoken
responses. ``tools.py`` is a thin LiveKit wrapper over these methods.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import datetime_resolve, faq
from .phone import normalize_phone
from .reservation import (
    Availability,
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


@dataclass
class CallState:
    """What we've learned during this call, so the agent doesn't re-ask.

    Mirrors LiveKit's UserData pattern: collected fields persist across tool
    calls within a single conversation.
    """

    name: str = ""
    phone: str = ""  # normalized E.164
    party_size: int = 0
    last_date: str = ""  # YYYY-MM-DD


def _booking_summary(b: Booking, *, locale: str = "en") -> str:
    when = _spoken_time(b.time)
    exp = f" ({b.experience_name})" if b.experience_name else ""
    if locale == "fr":
        return f"une réservation pour {b.size} le {when}{exp}"
    return f"a reservation for {b.size} on {when}{exp}"


_MONTHS = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]


def _spoken_date(iso_date: str) -> str:
    """Render '2026-06-28' as 'June 28'."""
    try:
        month, day = int(iso_date[5:7]), int(iso_date[8:10])
    except (ValueError, IndexError):
        return iso_date
    return f"{_MONTHS[month - 1]} {day}"


def _spoken_time(iso_time: str) -> str:
    """Render '2026-06-28T18:30:00-04:00' as 'June 28 at 6:30 PM'."""
    try:
        hour, minute = int(iso_time[11:13]), iso_time[14:16]
    except (ValueError, IndexError):
        return iso_time
    suffix = "AM" if hour < 12 else "PM"
    return f"{_spoken_date(iso_time)} at {hour % 12 or 12}:{minute} {suffix}"


class Concierge:
    def __init__(
        self,
        service: ReservationService,
        *,
        locale: str = "en",
        today: dt.date | None = None,
    ):
        self.service = service
        self.locale = locale
        self.today = today or dt.date.today()
        self.messages: list[Message] = []
        self.state = CallState()

    # -- availability ------------------------------------------------------
    async def check_availability(
        self, *, date: str, party_size: int, part_of_day: str = ""
    ) -> str:
        resolved = datetime_resolve.resolve_date(date, today=self.today)
        if resolved is None:
            return (
                "I want to get the date right — what day were you thinking? "
                "You can say something like 'this Friday' or a date."
            )
        horizon = datetime_resolve.validate_horizon(resolved, today=self.today)
        if horizon == "past":
            return "That date has already passed — what upcoming day works for you?"
        if horizon == "too_far":
            return "That's further out than we take reservations. Could you pick a nearer date?"

        iso_date = resolved.isoformat()
        if not part_of_day:
            part_of_day = datetime_resolve.infer_part_of_day(date)
        self.state.party_size = party_size or self.state.party_size
        self.state.last_date = iso_date

        try:
            availability = await self.service.check_availability(iso_date, party_size)
        except ReservationError as exc:
            return exc.spoken_message

        slots = list(availability.slots)
        want = part_of_day.strip().lower()
        if want in ("lunch", "dinner"):
            filtered = [s for s in slots if s.experience_name.lower() == want]
            # Only narrow if it leaves something; otherwise fall back to all.
            if filtered:
                slots = filtered
        availability = Availability(
            date=availability.date, party_size=availability.party_size, slots=slots
        )

        if not availability.is_available:
            return (
                f"I'm sorry, I don't see any open tables for {party_size} on "
                f"{_spoken_date(iso_date)}. Would another day work?"
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
        merged = any(s.is_merged for s in availability.slots)
        merge_note = (
            f" For a party of {party_size} we'd set up a combined table."
            if merged else ""
        )
        return (
            f"For {party_size}, I have {listed}{more}.{merge_note} "
            "Which time would you like?"
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
        normalized = normalize_phone(phone) or self.state.phone
        if not normalized:
            return (
                "I'll just need a phone number for the reservation — what's the "
                "best number to reach you?"
            )
        try:
            booking = await self.service.create_booking(
                time=time,
                party_size=party_size,
                first_name=first_name,
                last_name=last_name,
                phone=normalized,
                email=email,
                note=note,
                locale=self.locale,
            )
        except ReservationError as exc:
            return exc.spoken_message

        # Remember for the rest of the call.
        self.state.name = first_name or self.state.name
        self.state.phone = normalized
        self.state.party_size = party_size
        self.state.last_date = booking.time[:10] or self.state.last_date

        combined = (
            " We'll combine a couple of tables for your group." if booking.is_merged else ""
        )
        return (
            f"You're all set — {_booking_summary(booking, locale=self.locale)}, "
            f"under {first_name}.{combined} Is there anything else I can help with?"
        )

    # -- lookup ------------------------------------------------------------
    async def lookup_reservations(self, *, phone: str) -> str:
        normalized = normalize_phone(phone) or self.state.phone
        if not normalized:
            return "What's the phone number the reservation is under?"
        self.state.phone = normalized
        try:
            bookings = await self.service.list_bookings(phone=normalized)
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
        normalized = normalize_phone(phone) or self.state.phone
        if normalized:
            self.state.phone = normalized
            try:
                bookings = [
                    b for b in await self.service.list_bookings(phone=normalized)
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
