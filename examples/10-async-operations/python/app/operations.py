"""In-memory store + background worker for long-running confirmation
Operations (Ch10). `asyncio.create_task` + `await asyncio.sleep(...)` stands
in for a real job queue / saga orchestrator — the point of this chapter is
the 202 -> poll -> 303 *protocol*, not a production async runtime. uvicorn
runs this app single-process/single-worker, so a plain module-level dict
needs no locking (mirrors app/store.py); cooperative scheduling means
`cancel()` and the delayed completion below never interleave mid-mutation —
each runs to its next `await` without being pre-empted.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app import store
from app.models import BookingStatus, Operation, OperationStatus, Problem

# The deterministic, SHORT delay the confirmation worker sleeps before
# completing — short enough to keep CI/verify.sh bounded, long enough that a
# poll immediately after the 202 reliably observes RUNNING.
CONFIRMATION_DELAY_SECONDS = 2.0


@dataclass
class _OperationRecord:
    id: str
    booking_id: str
    created_at: str
    status: OperationStatus = OperationStatus.RUNNING
    completed_at: Optional[str] = None
    resource: Optional[str] = None
    error: Optional[Problem] = None
    cancelled: bool = False

    def to_operation(self) -> Operation:
        return Operation(
            id=self.id,
            status=self.status,
            createdAt=self.created_at,
            completedAt=self.completed_at,
            resource=self.resource,
            error=self.error,
        )


_operations: dict[str, _OperationRecord] = {}
_tasks: dict[str, asyncio.Task] = {}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def start_confirmation(op_id: str, booking_id: str) -> Operation:
    record = _OperationRecord(id=op_id, booking_id=booking_id, created_at=_now_utc())
    _operations[op_id] = record
    # asyncio only holds a WEAK reference to a task once nothing else does —
    # without this dict entry the task could be garbage-collected mid-sleep.
    # The done-callback below releases that reference again once it finishes.
    task = asyncio.create_task(_complete_confirmation(op_id))
    task.add_done_callback(lambda _t, op_id=op_id: _tasks.pop(op_id, None))
    _tasks[op_id] = task
    return record.to_operation()


def get(op_id: str) -> Operation | None:
    record = _operations.get(op_id)
    return record.to_operation() if record else None


def cancel(op_id: str) -> bool:
    """Cancels a still-PENDING/RUNNING operation. Returns False if unknown
    or already terminal (SUCCEEDED/FAILED) — the caller treats DELETE as
    idempotent either way. The delayed completion below checks `cancelled`
    before mutating anything, so a cancel that wins the race leaves the
    booking PENDING.
    """
    record = _operations.get(op_id)
    if record is None or record.status not in (OperationStatus.PENDING, OperationStatus.RUNNING):
        return False
    record.cancelled = True
    record.status = OperationStatus.FAILED
    record.completed_at = _now_utc()
    record.error = Problem(
        title="Operation cancelled", status=499,
        detail="Cancelled by client request before completion",
    )
    return True


async def _complete_confirmation(op_id: str) -> None:
    await asyncio.sleep(CONFIRMATION_DELAY_SECONDS)
    record = _operations.get(op_id)
    if record is None or record.cancelled:
        return
    booking = store.get(record.booking_id)
    if booking is not None and booking.status == BookingStatus.PENDING:
        confirmed = booking.model_copy(update={"status": BookingStatus.CONFIRMED, "updatedAt": _now_utc()})
        store.put(confirmed)
    record.status = OperationStatus.SUCCEEDED
    record.completed_at = _now_utc()
    record.resource = f"/bookings/{record.booking_id}"
