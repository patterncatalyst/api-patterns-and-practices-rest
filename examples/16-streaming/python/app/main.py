"""Ch16 streaming deep-dive — FastAPI side.

A thin Ch4-style Booking resource (POST to create, GET by id — just enough
to mint a booking id) plus three streaming endpoints, all built on an async
generator yielding frames incrementally rather than building one buffered
response body:

  * GET /bookings/{id}/events          — Server-Sent Events (live updates)
  * GET /bookings/events/export        — NDJSON (bulk/batch export)
  * GET /bookings/events/export/chunked — dedicated chunked-transfer demo

See app/events.py for the deterministic cargo-status event sequence shared
by all three. The JSON Booking/Problem/BookingEvent bodies here are
schema-validated by examples/16-streaming's verify.sh against
contracts/schemas/shipping.schema.json.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app import store
from app.events import (
    CHUNKED_LINE_COUNT,
    EXPORT_EVENT_COUNT,
    EXPORT_SAMPLE_BOOKING_ID,
    SSE_EVENT_COUNT,
    SSE_INTERVAL_SECONDS,
    event_for,
)
from app.models import Booking, BookingRequest, BookingStatus, Cargo, Problem
from app.ulid import generate_ulid

app = FastAPI(title="shipping-python-ch16")


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
# Bookings (thin — just enough to mint an id to stream events against)
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
# 1. Server-Sent Events — live cargo-status updates for one booking.
#
# The async generator `await asyncio.sleep(...)`s BETWEEN yields, so
# uvicorn flushes each `data: {...}\n\n` frame to the socket as it's
# produced rather than buffering the whole sequence and writing it once at
# the end — that's the entire point this chapter's verify.sh proves by
# timing first-byte vs. last-byte.
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
# 2. NDJSON export — one JSON object per line, flushed incrementally.
# ---------------------------------------------------------------------------

async def _ndjson_export_stream() -> AsyncIterator[str]:
    for i in range(EXPORT_EVENT_COUNT):
        payload = event_for(EXPORT_SAMPLE_BOOKING_ID, i)
        yield json.dumps(payload) + "\n"


@app.get("/bookings/events/export")
async def export_events() -> Response:
    return StreamingResponse(_ndjson_export_stream(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# 3. Dedicated chunked-transfer demo — a larger generated payload with no
#    Content-Length, proving Transfer-Encoding: chunked. SSE and NDJSON
#    above are ALSO chunked under the hood (uvicorn never knows their total
#    length up front either); this endpoint isolates the mechanics from
#    either framing so verify.sh can assert it directly.
# ---------------------------------------------------------------------------

async def _chunked_export_stream() -> AsyncIterator[str]:
    for i in range(CHUNKED_LINE_COUNT):
        yield f"line-{i}: " + ("x" * 200) + "\n"


@app.get("/bookings/events/export/chunked")
async def export_chunked() -> Response:
    return StreamingResponse(_chunked_export_stream(), media_type="text/plain")
