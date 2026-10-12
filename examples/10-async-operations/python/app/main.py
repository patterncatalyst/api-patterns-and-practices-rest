"""Ch10 async/long-running-operations example — FastAPI side.

Extends the Ch4 contract-first Booking + Cargo resource model
(contracts/openapi/shipping-api.yaml) with the 202 Accepted -> poll -> 303
See Other long-running operation protocol: POST
/bookings/{id}/confirmation starts an async confirmation (see
app/operations.py for the background worker), GET/DELETE /operations/{id}
polls/cancels it. Every response body here is schema-validated by
examples/10-async-operations's verify.sh against
contracts/schemas/shipping.schema.json — this module is the thing that has
to stay honest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app import operations, store
from app.models import (
    Booking,
    BookingCollection,
    BookingRequest,
    BookingStatus,
    Cargo,
    CargoRequest,
    OperationStatus,
    PageMeta,
    Problem,
)
from app.quote import compute_quote
from app.ulid import generate_deterministic_ulid, generate_ulid

app = FastAPI(title="shipping-python-ch10")


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
        quote=compute_quote(cargo_items),
        requestedPickup=payload.requestedPickup,
        createdAt=_now_utc(),
    )
    store.put(booking)
    return _json(201, booking, headers={"Location": f"/bookings/{booking.id}"})


@app.get("/bookings")
def list_bookings(limit: int = 20) -> JSONResponse:
    visible = store.list_visible()
    collection = BookingCollection(
        items=visible,
        page=PageMeta(limit=limit, count=len(visible), nextCursor=None),
    )
    return _json(200, collection)


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return _json(200, booking)


@app.put("/bookings/{booking_id}")
def replace_booking(booking_id: str, payload: BookingRequest) -> JSONResponse:
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    # Deterministic (not random) cargo ids: PUT must be idempotent, so
    # replacing a booking with the SAME body twice has to produce the SAME
    # Cargo.id for each item both times — generate_ulid() mints a fresh
    # random id every call, which POST correctly wants but PUT must not.
    cargo_items = [
        Cargo(id=f"crg_{generate_deterministic_ulid(f'{booking_id}:{i}')}", **item.model_dump())
        for i, item in enumerate(payload.cargo)
    ]
    updated = Booking(
        id=existing.id,
        status=existing.status,
        origin=payload.origin,
        destination=payload.destination,
        cargo=cargo_items,
        quote=compute_quote(cargo_items),
        requestedPickup=payload.requestedPickup,
        createdAt=existing.createdAt,
        updatedAt=_now_utc(),
    )
    store.put(updated)
    return _json(200, updated)


def _merge_patch(target: Any, patch: Any) -> Any:
    """RFC 7396 JSON Merge Patch, applied to plain dict/JSON-ish values."""
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = _merge_patch(result.get(key), value)
    return result


@app.patch("/bookings/{booking_id}")
async def patch_booking(booking_id: str, request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/merge-patch+json"):
        return _problem(415, "Unsupported Media Type", "PATCH requires Content-Type: application/merge-patch+json")

    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    try:
        patch_doc = await request.json()
    except Exception:
        return _problem(400, "Invalid merge patch", "request body is not valid JSON")

    current = existing.model_dump(mode="json", exclude_none=True)
    merged = _merge_patch(current, patch_doc)
    # id/createdAt are server-assigned (readOnly in the schema); a merge
    # patch can never overwrite them, regardless of what the client sent.
    merged["id"] = existing.id
    merged["createdAt"] = existing.createdAt
    merged["updatedAt"] = _now_utc()

    try:
        updated = Booking.model_validate(merged)
    except ValidationError as exc:
        return _problem(400, "Invalid merge patch result", str(exc.errors()))

    store.put(updated)
    return _json(200, updated)


@app.delete("/bookings/{booking_id}", status_code=204)
def delete_booking(booking_id: str) -> Response:
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    cancelled = existing.model_copy(update={"status": BookingStatus.CANCELLED, "updatedAt": _now_utc()})
    store.put(cancelled)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Cargo sub-resource
# ---------------------------------------------------------------------------

@app.get("/bookings/{booking_id}/cargo")
def list_cargo(booking_id: str) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return JSONResponse(
        status_code=200,
        content=[c.model_dump(mode="json", exclude_none=True) for c in booking.cargo],
    )


@app.post("/bookings/{booking_id}/cargo")
def add_cargo(booking_id: str, payload: CargoRequest) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    cargo = Cargo(id=f"crg_{generate_ulid()}", **payload.model_dump())
    new_cargo_list = [*booking.cargo, cargo]
    updated = booking.model_copy(update={
        "cargo": new_cargo_list,
        "quote": compute_quote(new_cargo_list),
        "updatedAt": _now_utc(),
    })
    store.put(updated)
    return _json(201, cargo, headers={"Location": f"/bookings/{booking_id}/cargo/{cargo.id}"})


# ---------------------------------------------------------------------------
# Confirmation (Ch10: 202 Accepted -> poll /operations/{id} -> 303)
# ---------------------------------------------------------------------------

@app.post("/bookings/{booking_id}/confirmation", status_code=202)
async def request_confirmation(booking_id: str) -> JSONResponse:
    # async def (not def, unlike this module's other handlers): FastAPI
    # runs a plain `def` endpoint in a worker thread via run_in_threadpool,
    # which has no running asyncio event loop — asyncio.create_task() inside
    # operations.start_confirmation() needs one. An `async def` endpoint
    # runs directly on the event loop that the background task is
    # scheduled onto.
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    if booking.status != BookingStatus.PENDING:
        return _problem(
            409, "Booking not confirmable",
            f"Booking {booking_id} is not PENDING (status={booking.status.value})",
        )

    op_id = f"op_{generate_ulid()}"
    operation = operations.start_confirmation(op_id, booking_id)
    return _json(202, operation, headers={"Location": f"/operations/{op_id}"})


# ---------------------------------------------------------------------------
# Operations (Ch10: poll / cancel)
# ---------------------------------------------------------------------------

@app.get("/operations/{operation_id}")
def get_operation(operation_id: str) -> Response:
    operation = operations.get(operation_id)
    if operation is None:
        return _problem(404, "Operation not found", f"No operation with id {operation_id}")
    if operation.status == OperationStatus.SUCCEEDED:
        return Response(status_code=303, headers={"Location": operation.resource})
    return _json(200, operation)


@app.delete("/operations/{operation_id}", status_code=204)
def cancel_operation(operation_id: str) -> Response:
    if operations.get(operation_id) is None:
        return _problem(404, "Operation not found", f"No operation with id {operation_id}")
    # Idempotent either way: a no-op against an already-terminal operation
    # still reports 204, the same way DELETE /bookings/{id} treats a repeat
    # cancel.
    operations.cancel(operation_id)
    return Response(status_code=204)
