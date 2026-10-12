"""In-memory booking store. This chapter's job is proving the test pyramid
around a known-good booking shape, not persistence — see
examples/04-contract-first/python/app/store.py for the same tradeoff.
uvicorn runs this app single-process/single-worker, so a plain module-level
dict needs no locking.
"""
from __future__ import annotations

from app.models import Booking

_bookings: dict[str, Booking] = {}


def put(booking: Booking) -> None:
    _bookings[booking.id] = booking


def get(booking_id: str) -> Booking | None:
    return _bookings.get(booking_id)


def reset() -> None:
    """Test helper — used by tests/test_bookings.py to isolate test cases."""
    _bookings.clear()
