"""In-memory booking store backing every capability this example exercises:
plain CRUD (Ch4), ascending-by-id listing for keyset pagination (Ch8), a
PENDING->CONFIRMED transition driven by the async operation worker (Ch10),
and soft delete + GDPR purge with a separate audit trail (Ch13). uvicorn
runs this app single-process/single-worker, so plain module-level dicts
need no locking.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models import Booking, BookingStatus, DeletionAudit

_bookings: dict[str, Booking] = {}
_audit_trail: dict[str, DeletionAudit] = {}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def put(booking: Booking) -> None:
    _bookings[booking.id] = booking


def get(booking_id: str) -> Booking | None:
    """Raw lookup — returns a cancelled (soft-deleted) booking too. Internal/audit use only."""
    return _bookings.get(booking_id)


def get_visible(booking_id: str) -> Booking | None:
    """Lookup for normal client traffic: a cancelled booking is "gone"."""
    booking = _bookings.get(booking_id)
    if booking is None or booking.status == BookingStatus.CANCELLED:
        return None
    return booking


def list_visible() -> list[Booking]:
    """Bookings visible in the default collection view (cancelled hidden),
    sorted ascending by id — ULIDs are 48-bit-timestamp-prefixed, so sorting
    by id is equivalent to sorting by creation time; this is the stable
    sort key keyset pagination is built on."""
    visible = [b for b in _bookings.values() if b.status != BookingStatus.CANCELLED]
    return sorted(visible, key=lambda b: b.id)


def confirm(booking_id: str) -> Booking | None:
    """Ch10: flips a PENDING booking to CONFIRMED (no-op if already past
    PENDING). Returns the current booking."""
    existing = _bookings.get(booking_id)
    if existing is None or existing.status != BookingStatus.PENDING:
        return existing
    confirmed = existing.model_copy(update={"status": BookingStatus.CONFIRMED, "updatedAt": _now_utc()})
    _bookings[booking_id] = confirmed
    return confirmed


def soft_delete(booking_id: str, reason: str) -> None:
    """Soft delete: cancel the booking in place and record why/when."""
    existing = _bookings.get(booking_id)
    if existing is None:
        return
    now = _now_utc()
    cancelled = existing.model_copy(update={"status": BookingStatus.CANCELLED, "updatedAt": now})
    _bookings[booking_id] = cancelled
    _audit_trail[booking_id] = DeletionAudit(deletedAt=now, reason=reason)


def get_audit(booking_id: str) -> DeletionAudit | None:
    return _audit_trail.get(booking_id)


def purge(booking_id: str) -> bool:
    """GDPR purge: hard-delete the booking AND its audit trail. Returns
    True if a booking existed to purge."""
    existed = _bookings.pop(booking_id, None) is not None
    _audit_trail.pop(booking_id, None)
    return existed
