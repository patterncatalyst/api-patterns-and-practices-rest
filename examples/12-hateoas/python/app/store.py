"""In-memory booking store. Deterministic and fast on purpose — this
chapter's job is proving request/response shapes against the contract, not
persistence (Ch12 is contract-first; Postgres shows up once the example
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


def list_visible() -> list[Booking]:
    """Bookings visible in the default collection view (cancelled hidden)."""
    return [b for b in _bookings.values() if b.status != BookingStatus.CANCELLED]


def reset() -> None:
    """Test/dev helper — not used by the running app."""
    _bookings.clear()
