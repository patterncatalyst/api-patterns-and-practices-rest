"""Deterministic cargo-status event sequence streamed by the SSE endpoint.
A fixed BookingStatus progression stands in for the kind of state-transition
feed a real tracking system would publish; only `occurredAt` varies between
calls (wall-clock time of emission). Copied from
../../16-streaming/python/app/events.py, trimmed to the SSE constants Ch23
actually uses (no NDJSON/chunked export here — that's Ch16's territory;
Ch23's focus is ASGI depth: streaming + BackgroundTasks + async/threadpool).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models import BookingStatus

# Number of events a single SSE stream emits.
SSE_EVENT_COUNT = 5

# Delay between successive SSE ticks (seconds) — keeps a full stream under
# ~1.5s so CI stays bounded.
SSE_INTERVAL_SECONDS = 0.25

_SEQUENCE = [
    BookingStatus.CONFIRMED,
    BookingStatus.IN_TRANSIT,
    BookingStatus.IN_TRANSIT,
    BookingStatus.IN_TRANSIT,
    BookingStatus.DELIVERED,
]


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_for(booking_id: str, index: int) -> dict:
    """The index-th event (0-based) for booking_id, cycling through _SEQUENCE."""
    status = _SEQUENCE[index % len(_SEQUENCE)]
    previous = BookingStatus.PENDING if index == 0 else _SEQUENCE[(index - 1) % len(_SEQUENCE)]
    return {
        "bookingId": booking_id,
        "status": status.value,
        "previousStatus": previous.value,
        "occurredAt": _now_utc(),
    }
