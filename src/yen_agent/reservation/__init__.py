"""Reservation backend abstraction.

The agent's tools depend only on :class:`ReservationService` (see ``base.py``).
``MockReservationService`` and ``LibroReservationService`` are interchangeable
implementations, so moving from the POC mock to real Libro is a one-line
dependency-injection change.
"""

from .base import ReservationService
from .errors import (
    BookingNotFoundError,
    ModificationRestrictedError,
    NotCancelableError,
    PartySizeOutOfRangeError,
    ReservationError,
    SlotUnavailableError,
)
from .models import Availability, Booking, PaymentIntent, Person, TimeSlot

__all__ = [
    "ReservationService",
    "Availability",
    "Booking",
    "PaymentIntent",
    "Person",
    "TimeSlot",
    "ReservationError",
    "SlotUnavailableError",
    "PartySizeOutOfRangeError",
    "NotCancelableError",
    "ModificationRestrictedError",
    "BookingNotFoundError",
]


def build_service(settings=None):
    """Construct the configured reservation backend.

    This is the single place where the mock/real swap happens. ``settings`` is a
    :class:`yen_agent.config.Settings`; if omitted it is loaded from the
    environment.
    """

    from ..config import Settings

    settings = settings or Settings.from_env()
    backend = settings.reservation_backend

    if backend in ("mock", "mock-http"):
        from .mock import MockReservationService

        if backend == "mock-http":
            return MockReservationService.http(
                base_url=settings.mock_base_url,
                restaurant_id=settings.restaurant_id,
            )
        return MockReservationService.in_process(
            db_path=settings.mock_db_path,
            restaurant_id=settings.restaurant_id,
        )

    if backend == "libro":
        from .libro import LibroReservationService

        return LibroReservationService(
            base_url=settings.libro_base_url,
            client_id=settings.libro_client_id,
            client_secret=settings.libro_client_secret,
            restaurant_id=settings.libro_restaurant_id,
        )

    raise ValueError(f"Unknown reservation backend: {backend!r}")
