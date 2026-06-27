"""Structured reservation errors mapped from Libro's error codes.

Libro returns JSON:API ``errors`` objects with stable numeric ``code`` values.
We translate them into typed exceptions so the agent can respond gracefully and
deterministically rather than parsing prose. Each error carries a
``spoken_message`` suitable for the voice agent to say to a caller.

Code references (from the Libro partner schema mirrored by the mock):
  2001  slot unavailable
  2005  party size out of range
  4001  booking not cancelable
The ``modification-restricted`` booking flag is surfaced as
``ModificationRestrictedError`` (no numeric code; it is an attribute, not an
API error) so changes that require restaurant staff degrade to "take a message".
"""

from __future__ import annotations


class ReservationError(Exception):
    """Base class for all reservation backend failures."""

    #: Libro numeric code, when one applies.
    code: str | None = None
    #: A caller-friendly line the voice agent can speak.
    spoken_message: str = (
        "I'm sorry, something went wrong on our reservation system. "
        "Let me take a message and have the team follow up."
    )

    def __init__(self, message: str | None = None, *, code: str | None = None,
                 detail: str | None = None, spoken_message: str | None = None):
        super().__init__(message or self.spoken_message)
        if code is not None:
            self.code = code
        self.detail = detail
        if spoken_message is not None:
            self.spoken_message = spoken_message


class SlotUnavailableError(ReservationError):
    code = "2001"
    spoken_message = (
        "That time isn't available anymore. I can check the closest open times "
        "if you'd like."
    )


class PartySizeOutOfRangeError(ReservationError):
    code = "2005"
    spoken_message = (
        "I can book tables for parties up to our online limit. For a larger "
        "group I'll take a message so the team can arrange it for you."
    )


class NotCancelableError(ReservationError):
    code = "4001"
    spoken_message = (
        "I'm not able to cancel that reservation online. Let me take a message "
        "so the restaurant can take care of it."
    )


class ModificationRestrictedError(ReservationError):
    code = None
    spoken_message = (
        "That reservation can only be changed by our team directly. I'll take a "
        "message and they'll follow up with you."
    )


class BookingNotFoundError(ReservationError):
    code = "404"
    spoken_message = (
        "I couldn't find a reservation under that information. Could you confirm "
        "the phone number or name it's under?"
    )


# Map Libro numeric codes -> exception classes.
_CODE_REGISTRY: dict[str, type[ReservationError]] = {
    cls.code: cls
    for cls in (
        SlotUnavailableError,
        PartySizeOutOfRangeError,
        NotCancelableError,
        BookingNotFoundError,
    )
    if cls.code is not None
}


def error_from_jsonapi(status_code: int, payload: dict | None) -> ReservationError:
    """Build a typed :class:`ReservationError` from a JSON:API error response."""

    errors = (payload or {}).get("errors") or []
    first = errors[0] if errors else {}
    code = str(first.get("code")) if first.get("code") is not None else None
    detail = first.get("detail") or first.get("title")

    if code and code in _CODE_REGISTRY:
        return _CODE_REGISTRY[code](detail, detail=detail)
    if status_code == 404:
        return BookingNotFoundError(detail, detail=detail)
    return ReservationError(detail or f"Reservation API error (HTTP {status_code})",
                            code=code, detail=detail)
