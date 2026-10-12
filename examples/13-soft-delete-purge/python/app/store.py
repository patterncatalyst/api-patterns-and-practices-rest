"""In-memory booking store. Deterministic and fast on purpose — this
chapter's job is proving request/response shapes against the contract, not
persistence (Ch13 extends the Ch4 anchor; Postgres shows up once an example
needs it). uvicorn runs this app single-process/single-worker, so plain
module-level dicts need no locking.

Soft delete (`DELETE /bookings/{id}`) flips `status` to CANCELLED and
records a `DeletionAudit` entry in `_audit_trail` — the booking AND its
audit entry both stay here, just hidden from the default read paths
(`get_visible`/`list_visible`). Purge (`DELETE /bookings/{id}/purge`) is the
GDPR "right to erasure" escape hatch: it pops the id out of BOTH dicts, so
even the audit view (`get`, called with includeDeleted=true) has nothing
left to find.
"""
from __future__ import annotations

from app.models import Booking, BookingStatus, DeletionAudit

_bookings: dict[str, Booking] = {}
_audit_trail: dict[str, DeletionAudit] = {}


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
    """Bookings visible in the default collection view (cancelled hidden)."""
    return [b for b in _bookings.values() if b.status != BookingStatus.CANCELLED]


def soft_delete(booking_id: str, cancelled: Booking, reason: str, deleted_at: str) -> None:
    """Soft delete: cancel the booking in place and record why/when."""
    _bookings[booking_id] = cancelled
    _audit_trail[booking_id] = DeletionAudit(deletedAt=deleted_at, reason=reason)


def get_audit(booking_id: str) -> DeletionAudit | None:
    return _audit_trail.get(booking_id)


def purge(booking_id: str) -> bool:
    """GDPR purge: hard-delete the booking AND its audit trail.

    Returns True if a booking existed to purge, so the route layer can tell
    a real erasure from a 404.
    """
    existed = _bookings.pop(booking_id, None) is not None
    _audit_trail.pop(booking_id, None)
    return existed


def reset() -> None:
    """Test/dev helper — not used by the running app."""
    _bookings.clear()
    _audit_trail.clear()
