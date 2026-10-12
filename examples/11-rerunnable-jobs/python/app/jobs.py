"""Server-owned state for the single `manifest-reconcile` job: the
schedule/definition (configure, server-owned) plus the run records a client
or the server's own scheduler produce (execute). This is the
configure-vs-execute split the chapter is about:

- `configure()` — a client PUTs a schedule (`enabled`/`interval_seconds`);
  the client never drives an individual run.
- `trigger_run()` — either the periodic ticker (running at the CONFIGURED
  interval) or an explicit "run now" request creates a new
  `Operation`-shaped run record and executes it asynchronously through
  PENDING -> RUNNING -> SUCCEEDED/FAILED.

The "reconcile" work itself is deliberately trivial and fast (a scan of
`app.store`'s bookings) — the point of this chapter is the rerunnable-job
*protocol*, not a real manifest-reconciliation engine. `WORK_DELAY_SECONDS`
keeps a run observably RUNNING for a moment (so a poll immediately after
"run now" reliably sees it mid-flight) while staying well inside verify.sh's
poll budget.

uvicorn runs this app single-process/single-worker, so plain module-level
dicts need no locking — the same convention as app/store.py and
app/operations.py in Ch10.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app import store
from app.models import BookingStatus, JobDefinition, Operation, OperationStatus
from app.ulid import generate_ulid

JOB_ID = "manifest-reconcile"

# Deterministic, short "work" duration for a single run — long enough that
# RUNNING is observable, short enough to keep CI bounded.
WORK_DELAY_SECONDS = 0.3

_logger = logging.getLogger("ch11.jobs")


@dataclass
class _JobDefinitionRecord:
    enabled: bool
    interval_seconds: int
    created_at: str
    updated_at: str

    def to_job_definition(self) -> JobDefinition:
        return JobDefinition(
            id=JOB_ID,
            enabled=self.enabled,
            intervalSeconds=self.interval_seconds,
            createdAt=self.created_at,
            updatedAt=self.updated_at,
        )


@dataclass
class _RunRecord:
    id: str
    created_at: str
    status: OperationStatus = OperationStatus.PENDING
    completed_at: Optional[str] = None

    def to_operation(self) -> Operation:
        return Operation(
            id=self.id,
            status=self.status,
            createdAt=self.created_at,
            completedAt=self.completed_at,
            resource=None,
            error=None,
        )


_definition: Optional[_JobDefinitionRecord] = None
_runs: dict[str, _RunRecord] = {}
# asyncio only holds a WEAK reference to a task once nothing else does —
# these dicts keep the periodic ticker and each run's task alive.
_tick_task: Optional[asyncio.Task] = None
_run_tasks: dict[str, asyncio.Task] = {}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def configure(enabled: bool, interval_seconds: int) -> tuple[JobDefinition, bool]:
    """Upserts the job definition (server-owned schedule) and re-arms the
    periodic ticker at the new `interval_seconds` — this is what makes "the
    client configures the schedule" literally true: the ticker's cadence
    comes from the configured value, not a hardcoded constant. Must be
    called from a coroutine running on the event loop (an `async def`
    endpoint), since it creates an asyncio task — see Ch10's
    operations.start_confirmation for the same gotcha.
    """
    global _definition
    created = _definition is None
    now = _now_utc()
    created_at = _definition.created_at if _definition else now
    _definition = _JobDefinitionRecord(
        enabled=enabled, interval_seconds=interval_seconds, created_at=created_at, updated_at=now,
    )
    _rearm_tick(interval_seconds)
    return _definition.to_job_definition(), created


def get_definition() -> Optional[JobDefinition]:
    return _definition.to_job_definition() if _definition else None


def trigger_run() -> Optional[Operation]:
    """"Run now": creates a run record and executes it asynchronously,
    independent of the periodic ticker. Returns None if the job has never
    been configured.
    """
    if _definition is None:
        return None
    return _start_run()


def get_run(run_id: str) -> Optional[Operation]:
    record = _runs.get(run_id)
    return record.to_operation() if record else None


def list_runs() -> list[Operation]:
    """Newest-first, per the run collection's documented ordering."""
    return [record.to_operation() for record in reversed(list(_runs.values()))]


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def _rearm_tick(interval_seconds: int) -> None:
    global _tick_task
    if _tick_task is not None:
        _tick_task.cancel()
    _tick_task = asyncio.create_task(_tick_loop(interval_seconds))


async def _tick_loop(interval_seconds: int) -> None:
    """Fires every `interval_seconds`. Only starts an automatic run while
    the job is enabled — disabling it stops new runs without un-configuring
    the job entirely.
    """
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            if _definition is not None and _definition.enabled:
                _logger.info("ch11: ticker firing an automatic %s run", JOB_ID)
                _start_run()
    except asyncio.CancelledError:
        pass


def _start_run() -> Operation:
    # "op_" prefix (not "run_"): this run record reuses #/$defs/Operation
    # verbatim, including its id pattern (^op_[0-9A-HJKMNP-TV-Z]{26}$) — see
    # models.Operation's docstring.
    run_id = f"op_{generate_ulid()}"
    record = _RunRecord(id=run_id, created_at=_now_utc())
    _runs[run_id] = record
    task = asyncio.create_task(_execute_run(run_id))
    task.add_done_callback(lambda _t, run_id=run_id: _run_tasks.pop(run_id, None))
    _run_tasks[run_id] = task
    return record.to_operation()


async def _execute_run(run_id: str) -> None:
    """The trivial "reconcile manifests against bookings" work: scan the
    booking store, then report success. A real implementation would compare
    each booking's manifest against carrier data; this chapter's point is
    the job-lifecycle protocol around that work, not the work itself.
    """
    record = _runs.get(run_id)
    if record is None:
        return
    record.status = OperationStatus.RUNNING
    pending_count = sum(1 for b in store.list_visible() if b.status == BookingStatus.PENDING)
    _logger.info("ch11: run %s reconciling %d PENDING booking(s)", run_id, pending_count)
    await asyncio.sleep(WORK_DELAY_SECONDS)
    record.completed_at = _now_utc()
    record.status = OperationStatus.SUCCEEDED
