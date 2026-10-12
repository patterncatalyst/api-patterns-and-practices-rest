"""Deterministic cargo-status event sequence streamed by the Ch16-style
NDJSON manifest export (`GET /bookings/{id}/manifest/export`). A fixed
BookingStatus progression stands in for the kind of state-transition feed a
real tracking system would publish; only `occurredAt` varies between
calls. Mirrors ../quarkus/.../ManifestEventGenerator.java.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models import BookingStatus

# Number of lines the manifest export emits per request.
LINE_COUNT = 6

# Delay between successive lines (seconds) — keeps a full export under ~1.5s.
INTERVAL_SECONDS = 0.25

_SEQUENCE = [
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.CONFIRMED,
    BookingStatus.IN_TRANSIT,
    BookingStatus.IN_TRANSIT,
    BookingStatus.DELIVERED,
]


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_for(booking_id: str, index: int) -> dict:
    """The index-th event (0-based) for booking_id, cycling through _SEQUENCE."""
    status = _SEQUENCE[index % len(_SEQUENCE)]
    previous = None if index == 0 else _SEQUENCE[(index - 1) % len(_SEQUENCE)]
    return {
        "bookingId": booking_id,
        "status": status.value,
        **({"previousStatus": previous.value} if previous is not None else {}),
        "occurredAt": _now_utc(),
    }
