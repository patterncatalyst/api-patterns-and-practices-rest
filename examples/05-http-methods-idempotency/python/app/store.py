"""In-memory booking store. Deterministic and fast on purpose — this
chapter's job is proving request/response shapes against the contract, not
persistence (Ch4 is contract-first; Postgres shows up once the example
needs it). uvicorn runs this app single-process/single-worker, so a plain
module-level dict needs no locking.
"""
from __future__ import annotations

from app.models import Booking, BookingStatus

_bookings: dict[str, Booking] = {}


def put(booking: Booking) -> None:
    _bookings[booking.id] = booking


def get(booking_id: str) -> Booking | None:
    return _bookings.get(booking_id)


def get_active(booking_id: str) -> Booking | None:
    """A booking that is still "live" from the API consumer's point of
    view: exists AND has not been (soft-)deleted. DELETE here is a
    soft-delete (status -> CANCELLED, record retained for audit) but every
    single-item read/write treats a cancelled booking as gone — GET, PUT,
    PATCH, DELETE and the cargo sub-resource all 404 once a booking is
    cancelled, matching the "second DELETE -> 404" assertion in verify.sh.
    Only the raw `get` above can still see a cancelled record, which is
    what a real audit/undo path would use.
    """
    booking = _bookings.get(booking_id)
    if booking is None or booking.status == BookingStatus.CANCELLED:
        return None
    return booking


def list_visible() -> list[Booking]:
    """Bookings visible in the default collection view (cancelled hidden)."""
    return [b for b in _bookings.values() if b.status != BookingStatus.CANCELLED]


def reset() -> None:
    """Test/dev helper — not used by the running app."""
    _bookings.clear()
