"""In-memory booking store PLUS the notification log the BackgroundTasks
demo writes to. uvicorn runs this app single-process/single-worker for the
booking dict (mirrors ../../16-streaming's app/store.py), but the
notification log is also written to from a background task running on a
DIFFERENT execution context than the request that queued it (see
app/main.py's `/thread/sync` for the general async-vs-threadpool story), so
it uses a plain `list.append` — atomic under the GIL for this single-process
deployment — rather than anything requiring real locking.
"""
from __future__ import annotations

from app.models import Booking

_bookings: dict[str, Booking] = {}
_notifications: dict[str, list[dict]] = {}


def put(booking: Booking) -> None:
    _bookings[booking.id] = booking


def get(booking_id: str) -> Booking | None:
    return _bookings.get(booking_id)


def add_notification(booking_id: str, message: str, sent_at: str) -> None:
    _notifications.setdefault(booking_id, []).append(
        {"message": message, "sentAt": sent_at}
    )


def list_notifications(booking_id: str) -> list[dict]:
    return list(_notifications.get(booking_id, []))
