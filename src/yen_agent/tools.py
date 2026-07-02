"""LiveKit Agent + function tools.

This is a thin wrapper: every tool delegates to :class:`Concierge`, which holds
all the reservation logic and is independently unit-tested. Importing this
module requires ``livekit-agents`` (install with ``pip install -e ".[agent]"``).
"""

from __future__ import annotations

from livekit.agents import Agent, function_tool

from .concierge import Concierge


class ReservationAgent(Agent):
    """The Yen reservations agent. Tools call the injected concierge."""

    def __init__(self, concierge: Concierge, *, instructions: str):
        super().__init__(instructions=instructions)
        self.concierge = concierge

    @function_tool
    async def check_availability(
        self, date: str, party_size: int, part_of_day: str = ""
    ) -> str:
        """Check open reservation times at Yen.

        Args:
            date: The date the caller wants. Pass their words ("this Friday",
                "tomorrow", "July 5") or an absolute YYYY-MM-DD — the system
                resolves it relative to today either way.
            party_size: Number of guests.
            part_of_day: Optional — "lunch" or "dinner" to narrow results when the
                caller asks about a specific service (e.g. "this evening" -> "dinner").
                Leave empty to see all seatings that day.
        """
        return await self.concierge.check_availability(
            date=date, party_size=party_size, part_of_day=part_of_day
        )

    @function_tool
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
    async def lookup_reservation(self, phone: str) -> str:
        """Look up the caller's existing reservations by phone number.

        Args:
            phone: The phone number the reservation is under.
        """
        return await self.concierge.lookup_reservations(phone=phone)

    @function_tool
    async def cancel_reservation(self, phone: str = "", booking_id: str = "") -> str:
        """Cancel a reservation, identified by phone number or booking id.

        Args:
            phone: The phone number the reservation is under.
            booking_id: The reservation id, if known.
        """
        return await self.concierge.cancel_reservation(phone=phone, booking_id=booking_id)

    @function_tool
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
    async def answer_faq(self, topic: str) -> str:
        """Answer a common question about Yen.

        Args:
            topic: One of: hours, location, parking, menu, dietary,
                reservations, payment.
        """
        return self.concierge.answer_faq(topic=topic)

    @function_tool
    async def take_message(self, name: str, phone: str, message: str) -> str:
        """Take a message for the restaurant team (large groups, special
        requests, complaints, or anything you can't handle directly).

        Args:
            name: Caller's name.
            phone: Caller's callback number.
            message: What the team should know / call back about.
        """
        return self.concierge.take_message(name=name, phone=phone, message=message)
