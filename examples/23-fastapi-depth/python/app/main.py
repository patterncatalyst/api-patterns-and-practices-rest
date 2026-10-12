"""Ch23 "FastAPI in depth" — the per-framework deep-dive corollary to Ch22's
Quarkus REST depth, single-stack on purpose (no quarkus/ counterpart here).
Three ASGI-level mechanics, each demonstrated as a small, deterministic,
independently-verifiable endpoint on top of a thin Ch4-style Booking
resource (POST to create, GET by id — just enough to mint an id):

  1. ASGI STREAMING — GET /bookings/{id}/events (Server-Sent Events via
     `StreamingResponse`, an async generator that `await`s BETWEEN yields so
     frames drip onto the socket one at a time rather than arriving as one
     buffered blob). See app/events.py for the event sequence this streams.

  2. BACKGROUND TASKS — POST /bookings/{id}/notify returns 202 immediately
     (before the notification work has run) and schedules an async
     background task that sleeps, then appends to an in-memory
     per-booking notification log. GET /bookings/{id}/notifications lets a
     caller observe that side effect once it has actually happened —
     proving BackgroundTasks genuinely defers work past the response,
     rather than just hiding a synchronous call behind a 202 status code.

  3. ASYNC vs. THREADPOOL (the GIL story) — GET /thread/async (an `async
     def` handler, which Starlette runs directly on the event loop) and
     GET /thread/sync (a plain `def` handler, which Starlette offloads via
     anyio to a worker thread from its threadpool) each report whether
     they executed on the process's main thread. uvicorn runs this single
     app process with its event loop on the main thread and no reload/
     multi-worker forking, so the async handler is ALWAYS on the main
     thread and the sync handler NEVER is — a small, deterministic window
     into why FastAPI tells you to reach for `async def` plus `await` for
     I/O, and plain `def` only for work you're fine handing to a thread.

The JSON Booking/Problem/BookingEvent bodies here are schema-validated by
this chapter's verify.sh against contracts/schemas/shipping.schema.json.
"""
from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app import store
from app.events import SSE_EVENT_COUNT, SSE_INTERVAL_SECONDS, event_for
from app.models import Booking, BookingRequest, BookingStatus, Cargo, NotifyRequest, Problem
from app.ulid import generate_ulid

app = FastAPI(title="shipping-python-ch23")

# Simulated latency of the "real" work a notification send would do (an
# email/SMS/webhook call) — long enough that a caller reading the response
# promptly and THEN polling for the side effect can tell the two apart,
# short enough to keep CI bounded.
NOTIFY_DELAY_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(status_code: int, model, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=model.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


def _problem(status_code: int, title: str, detail: str | None = None) -> JSONResponse:
    body = Problem(title=title, status=status_code, detail=detail)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _problem(400, "Validation failed", str(exc.errors()))


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "up"}


# ---------------------------------------------------------------------------
# Bookings (thin — just enough to mint an id to hang events/notifications on)
# ---------------------------------------------------------------------------

@app.post("/bookings")
def create_booking(payload: BookingRequest) -> JSONResponse:
    cargo_items = [
        Cargo(id=f"crg_{generate_ulid()}", **item.model_dump())
        for item in payload.cargo
    ]
    booking = Booking(
        id=f"bkg_{generate_ulid()}",
        status=BookingStatus.PENDING,
        origin=payload.origin,
        destination=payload.destination,
        cargo=cargo_items,
        requestedPickup=payload.requestedPickup,
        createdAt=_now_utc(),
    )
    store.put(booking)
    return _json(201, booking, headers={"Location": f"/bookings/{booking.id}"})


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return _json(200, booking)


def _booking_or_404(booking_id: str) -> JSONResponse | None:
    if store.get(booking_id) is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return None


# ---------------------------------------------------------------------------
# 1. ASGI streaming — Server-Sent Events, live cargo-status updates.
#
# The async generator `await asyncio.sleep(...)`s BETWEEN yields, so uvicorn
# flushes each `data: {...}\n\n` frame to the socket as it's produced rather
# than buffering the whole sequence and writing it once at the end — that's
# the entire point this chapter's verify.sh proves by timing first-frame vs.
# last-frame arrival.
# ---------------------------------------------------------------------------

async def _sse_event_stream(booking_id: str) -> AsyncIterator[str]:
    for i in range(SSE_EVENT_COUNT):
        await asyncio.sleep(SSE_INTERVAL_SECONDS)
        payload = event_for(booking_id, i)
        yield f"data: {json.dumps(payload)}\n\n"


@app.get("/bookings/{booking_id}/events")
async def booking_events(booking_id: str) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    return StreamingResponse(_sse_event_stream(booking_id), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 2. BackgroundTasks — return promptly, do the work after the response ships.
#
# `background_tasks.add_task` schedules `_send_notification` to run AFTER
# the 202 response has been sent to the client. Because the task itself is
# `async def` and only `await`s (`asyncio.sleep`), it runs on the same
# event loop as everything else — it just runs LATER, once the response has
# gone out. The in-memory log it appends to is only observable through a
# separate GET, which is exactly what verify.sh polls to prove the side
# effect genuinely happened after, not before, the response returned.
# ---------------------------------------------------------------------------

async def _send_notification(booking_id: str, message: str) -> None:
    await asyncio.sleep(NOTIFY_DELAY_SECONDS)
    store.add_notification(booking_id, message, _now_utc())


@app.post("/bookings/{booking_id}/notify")
async def notify_booking(
    booking_id: str, payload: NotifyRequest, background_tasks: BackgroundTasks
) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    background_tasks.add_task(_send_notification, booking_id, payload.message)
    return JSONResponse(
        status_code=202,
        content={"bookingId": booking_id, "status": "queued"},
    )


@app.get("/bookings/{booking_id}/notifications")
async def list_notifications(booking_id: str) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    return JSONResponse(
        status_code=200,
        content={
            "bookingId": booking_id,
            "notifications": store.list_notifications(booking_id),
        },
    )


# ---------------------------------------------------------------------------
# 3. async vs. threadpool — where does each handler actually execute?
#
# uvicorn runs this process's event loop on the main thread (single
# process, no --workers, no reload). An `async def` route is awaited
# directly on that loop, so it ALWAYS reports `isMainThread: true`. A plain
# `def` route is detected by Starlette and offloaded via
# `anyio.to_thread.run_sync` to a worker thread from its threadpool, so it
# ALWAYS reports `isMainThread: false` — the request was still served, but
# never on the event loop thread.
# ---------------------------------------------------------------------------

def _thread_report(handler: str) -> dict:
    current = threading.current_thread()
    return {
        "handler": handler,
        "isMainThread": current is threading.main_thread(),
        "threadName": current.name,
    }


@app.get("/thread/async")
async def thread_async() -> dict:
    return _thread_report("async")


@app.get("/thread/sync")
def thread_sync() -> dict:
    return _thread_report("sync")
