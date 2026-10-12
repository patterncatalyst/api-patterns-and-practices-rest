"""Ch21 multi-protocol-contracts anchor — FastAPI side.

ONE service exposing a synchronous REST path (`POST /bookings` ->
`#/$defs/Booking`, per contracts/openapi/shipping-api.yaml) that also drives
a background event-streaming path (a CloudEvents-enveloped `BookingEvent`
published to Kafka, per contracts/asyncapi/shipping-events.yaml). The
Booking shape/quote logic is the same as examples/04-contract-first — this
chapter's addition is app/events.py, fired via FastAPI's BackgroundTasks so
the synchronous response never waits on the broker.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import store
from app.events import publish_confirmed
from app.models import Booking, BookingRequest, BookingStatus, Cargo, Problem
from app.quote import compute_quote
from app.ulid import generate_ulid

app = FastAPI(title="shipping-python-ch21")


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
# Bookings
# ---------------------------------------------------------------------------

def confirm_and_publish(created: Booking) -> None:
    """Background action: PENDING -> CONFIRMED, then publish the
    CloudEvents-enveloped BookingEvent. Runs off the request thread (FastAPI
    BackgroundTasks, dispatched to a threadpool), so it never blocks the
    synchronous REST response above it."""
    confirmed = created.model_copy(update={"status": BookingStatus.CONFIRMED, "updatedAt": _now_utc()})
    store.put(confirmed)
    publish_confirmed(confirmed, BookingStatus.PENDING)


@app.post("/bookings")
def create_booking(payload: BookingRequest, background_tasks: BackgroundTasks) -> JSONResponse:
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
        quote=compute_quote(cargo_items),
        requestedPickup=payload.requestedPickup,
        createdAt=_now_utc(),
    )
    store.put(booking)

    # Background action: confirm + emit the CloudEvent. The response below
    # returns immediately with the PENDING booking it just created.
    background_tasks.add_task(confirm_and_publish, booking)

    return _json(201, booking, headers={"Location": f"/bookings/{booking.id}"})


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return _json(200, booking)
