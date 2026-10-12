"""Deterministic cargo-status event sequence — the small payload this
chapter streams in all three modes (SSE, NDJSON, chunked). A fixed
BookingStatus progression stands in for the kind of state-transition feed a
real tracking system would publish; only `occurredAt` varies between calls
(wall-clock time of emission). Mirrors
../../quarkus/.../EventGenerator.java conceptually — what matters here is
event SHAPE and DELIVERY TIMING, not a frozen clock.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models import BookingStatus

# Number of events a single SSE stream emits.
SSE_EVENT_COUNT = 5

# Delay between successive SSE ticks (seconds) — keeps a full stream under
# ~1.5s so CI stays bounded.
SSE_INTERVAL_SECONDS = 0.25

# Row count for the NDJSON export endpoint.
EXPORT_EVENT_COUNT = 10

# Line count for the dedicated chunked-transfer demo endpoint.
CHUNKED_LINE_COUNT = 500

# A schema-valid (but never-issued) booking id — all 26 Crockford-Base32
# zero chars — used by the NDJSON export, which isn't scoped to a real
# booking the caller created. '0' is a legal Crockford Base32 digit, so this
# satisfies BookingEvent.bookingId's `^bkg_[0-9A-HJKMNP-TV-Z]{26}$` pattern
# without pretending to be a real booking.
EXPORT_SAMPLE_BOOKING_ID = "bkg_" + "0" * 26

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
