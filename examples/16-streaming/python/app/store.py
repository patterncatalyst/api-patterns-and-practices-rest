"""In-memory booking store. Ch16 only needs put/get — just enough to mint a
booking id for the streaming tests below and to tell a known booking from an
unknown one (the SSE endpoint's 404 case). Mirrors ../04-contract-first's
app/store.py, trimmed of the list_visible()/soft-delete machinery this
chapter doesn't exercise. uvicorn runs this app single-process/single-worker,
so a plain module-level dict needs no locking.
"""
from __future__ import annotations

from app.models import Booking

_bookings: dict[str, Booking] = {}


def put(booking: Booking) -> None:
    _bookings[booking.id] = booking


def get(booking_id: str) -> Booking | None:
    return _bookings.get(booking_id)
