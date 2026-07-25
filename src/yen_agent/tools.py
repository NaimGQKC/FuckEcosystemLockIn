"""LiveKit Agent + function tools.

This is a thin wrapper: every tool delegates to :class:`Concierge`, which holds
all the reservation logic and is independently unit-tested. Importing this
module requires ``livekit-agents`` (install with ``pip install -e ".[agent]"``).
"""

from __future__ import annotations

import functools
import logging

from livekit.agents import Agent, function_tool

from .concierge import Concierge

logger = logging.getLogger("yen-agent.tools")

_FALLBACK = (
    "Sorry, I had trouble looking that up just now. Let me take a message and "
    "the team will get right back to you."
)


def _safe(fn):
    """Never let a tool exception kill the call — speak a graceful line instead."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - a live call must not crash
            logger.exception("tool %s failed", getattr(fn, "__name__", "?"))
            return _FALLBACK

    return wrapper


class ReservationAgent(Agent):
    """The Yen reservations agent. Tools call the injected concierge."""

    def __init__(self, concierge: Concierge, *, instructions: str):
        super().__init__(instructions=instructions)
        self.concierge = concierge

    @function_tool
    @_safe
    async def check_availability(
        self, date: str, party_size: int, part_of_day: str = "",
        preferred_time: str = "",
    ) -> str:
        """Check open reservation times at Yen.

        Always pass `preferred_time` when the caller named one — the system then
        confirms that exact time, or offers the closest alternatives, or another
        day, or captures them for a callback. Never tell a caller we're full
        without calling this first.

        Args:
            date: The date the caller wants. Pass their words ("this Friday",
                "tomorrow", "July 5") or an absolute YYYY-MM-DD — the system
                resolves it relative to today either way.
            party_size: Number of guests.
            part_of_day: Optional — "lunch" or "dinner" (or "evening"/"tonight"/
                "noon"; they're understood). Leave empty for all seatings that day.
            preferred_time: The time the caller asked for, in their words ("7",
                "7:30", "half past eight"). An hour of 1-8 is treated as PM.
        """
        return await self.concierge.check_availability(
            date=date, party_size=party_size, part_of_day=part_of_day,
            preferred_time=preferred_time,
        )

    @function_tool
    @_safe
    async def join_waitlist(
        self, name: str, phone: str, date: str = "", party_size: int = 0,
        preferred_time: str = "",
    ) -> str:
        """Add the caller to the waitlist when we're fully booked.

        Use this INSTEAD of taking a generic message when the reason we can't help
        is that there's no table — we'll text them if one opens up. Only fall back
        to `take_message` if they'd rather speak to a person.

        Args:
            name: Caller's name.
            phone: Their callback number, any format.
            date: The date they wanted (their words are fine).
            party_size: Number of guests.
            preferred_time: The time they originally asked for.
        """
        return self.concierge.join_waitlist(
            name=name, phone=phone, date=date, party_size=party_size,
            preferred_time=preferred_time,
        )

    @function_tool
    @_safe
    async def book_reservation(
        self,
        time: str,
        party_size: int,
        first_name: str,
        phone: str,
        last_name: str = "",
        email: str = "",
        note: str = "",
    ) -> str:
        """Create a reservation. Confirm details with the caller first.

        Args:
            time: The exact seating time in ISO-8601, taken from an availability
                result (e.g. "2026-06-28T18:30:00-04:00").
            party_size: Number of guests.
            first_name: Guest's first name.
            phone: Callback phone number in any format (e.g. "514-555-1234"); it
                is normalized automatically. Omit only if already given earlier.
            last_name: Guest's last name, if given.
            email: Guest's email, if given.
            note: Any special request or dietary note.
        """
        return await self.concierge.book_reservation(
            time=time,
            party_size=party_size,
            first_name=first_name,
            phone=phone,
            last_name=last_name,
            email=email,
            note=note,
        )

    @function_tool
    @_safe
    async def lookup_reservation(self, phone: str) -> str:
        """Look up the caller's existing reservations by phone number.

        Args:
            phone: The phone number the reservation is under.
        """
        return await self.concierge.lookup_reservations(phone=phone)

    @function_tool
    @_safe
    async def cancel_reservation(self, phone: str = "", booking_id: str = "") -> str:
        """Cancel a reservation, identified by phone number or booking id.

        Args:
            phone: The phone number the reservation is under.
            booking_id: The reservation id, if known.
        """
        return await self.concierge.cancel_reservation(phone=phone, booking_id=booking_id)

    @function_tool
    @_safe
    async def reschedule_reservation(
        self, new_time: str, phone: str = "", booking_id: str = ""
    ) -> str:
        """Move a reservation to a new time.

        Args:
            new_time: The new seating time in ISO-8601, from an availability result.
            phone: The phone number the reservation is under.
            booking_id: The reservation id, if known.
        """
        return await self.concierge.reschedule_reservation(
            new_time=new_time, phone=phone, booking_id=booking_id
        )

    @function_tool
    @_safe
    async def answer_faq(self, topic: str) -> str:
        """Answer a common question about Yen.

        Args:
            topic: One of: hours, location, parking, menu, dietary,
                reservations, payment.
        """
        return self.concierge.answer_faq(topic=topic)

    @function_tool
    @_safe
    async def take_message(self, name: str, phone: str, message: str) -> str:
        """Take a message for the restaurant team (large groups, special
        requests, complaints, or anything you can't handle directly).

        Args:
            name: Caller's name.
            phone: Caller's callback number.
            message: What the team should know / call back about.
        """
        return self.concierge.take_message(name=name, phone=phone, message=message)

    @function_tool
    @_safe
    async def handle_takeout(self, name: str = "", phone: str = "",
                             order: str = "", wants_callback: bool = True) -> str:
        """Handle a caller who wants takeout, delivery, or to order food.

        Use this the moment a caller mentions ordering food to pick up or have
        delivered — do NOT try to book them a table, and do NOT just tell them to
        use the website and leave it there.

        Offer them the choice first: "You can order on our website, or I can have
        someone call you right back to take it by phone — which would you prefer?"

        Args:
            name: Caller's name, if given.
            phone: Callback number.
            order: What they want to order, in their own words. Rough is fine.
            wants_callback: True if they want a callback, False if they're happy
                to order online themselves.
        """
        return self.concierge.handle_takeout(
            name=name, phone=phone, order=order, wants_callback=wants_callback
        )
