"""Ch10: in-memory store + background worker for long-running confirmation
Operations. `asyncio.create_task` + `await asyncio.sleep(...)` stands in
for a real job queue / saga orchestrator — once the confirmation completes,
it flips the booking to CONFIRMED (app/store.py) and publishes the Ch21
CloudEvent (app/events.py), tying the async protocol and the background
event-streaming path together. uvicorn runs this app single-process/
single-worker, so a plain module-level dict needs no locking.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app import events, store
from app.models import BookingStatus, Operation, OperationStatus, Problem

# The deterministic, SHORT delay the confirmation worker sleeps before
# completing — short enough to keep CI/verify.sh bounded, long enough that
# a poll immediately after the 202 reliably observes RUNNING.
CONFIRMATION_DELAY_SECONDS = 1.5


@dataclass
class _OperationRecord:
    id: str
    booking_id: str
    created_at: str
    status: OperationStatus = OperationStatus.RUNNING
    completed_at: Optional[str] = None
    resource: Optional[str] = None
    error: Optional[Problem] = None

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
    task = asyncio.create_task(_complete_confirmation(op_id))
    task.add_done_callback(lambda _t, op_id=op_id: _tasks.pop(op_id, None))
    _tasks[op_id] = task
    return record.to_operation()


def get(op_id: str) -> Operation | None:
    record = _operations.get(op_id)
    return record.to_operation() if record else None


async def _complete_confirmation(op_id: str) -> None:
    await asyncio.sleep(CONFIRMATION_DELAY_SECONDS)
    record = _operations.get(op_id)
    if record is None:
        return
    confirmed = store.confirm(record.booking_id)
    record.status = OperationStatus.SUCCEEDED
    record.completed_at = _now_utc()
    record.resource = f"/bookings/{record.booking_id}"
    if confirmed is not None and confirmed.status == BookingStatus.CONFIRMED:
        events.publish_confirmed(confirmed, BookingStatus.PENDING)
