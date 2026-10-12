"""In-memory booking store — same role as examples/04-contract-first's
app/store.py. Ch21's point is the sync-REST + background-event pairing, not
persistence. uvicorn runs this app single-process/single-worker, so a plain
module-level dict needs no locking.
"""
from __future__ import annotations

from app.models import Booking

_bookings: dict[str, Booking] = {}


def put(booking: Booking) -> None:
    _bookings[booking.id] = booking


def get(booking_id: str) -> Booking | None:
    return _bookings.get(booking_id)
