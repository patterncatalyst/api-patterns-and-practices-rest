"""In-memory booking store. Deterministic and fast on purpose — this
chapter's job is proving pagination/projection shapes against the contract,
not persistence (Postgres shows up once a later chapter needs it). uvicorn
runs this app single-process/single-worker, so a plain module-level dict
needs no locking.
"""
from __future__ import annotations

from app.models import Booking, BookingStatus

_bookings: dict[str, Booking] = {}


def put(booking: Booking) -> None:
    _bookings[booking.id] = booking


def get(booking_id: str) -> Booking | None:
    return _bookings.get(booking_id)


def list_visible() -> list[Booking]:
    """Bookings visible in the default collection view (cancelled hidden),
    sorted ascending by id. ULIDs are 48-bit-timestamp-prefixed, so sorting
    by id is equivalent to sorting by creation time — this is the single
    stable sort key every pagination strategy below is built on."""
    visible = [b for b in _bookings.values() if b.status != BookingStatus.CANCELLED]
    return sorted(visible, key=lambda b: b.id)


def reset() -> None:
    """Test/dev helper — not used by the running app."""
    _bookings.clear()
