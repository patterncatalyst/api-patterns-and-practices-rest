"""Ch12 HATEOAS — FastAPI side.

Extends the Ch4 contract-first Booking + Cargo resource model
(contracts/openapi/shipping-api.yaml, contracts/schemas/shipping.schema.json)
with state-dependent `_links`: every Booking response carries exactly the
relations valid from its current `status`, driven by the booking lifecycle
finite-state machine (see app/hateoas.py). Every response body here is
schema-validated by this chapter's verify.sh against
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

from app import store
from app.hateoas import links_for_booking
from app.models import (
    Booking,
    BookingCollection,
    BookingRequest,
    BookingStatus,
    Cargo,
    CargoRequest,
    PageMeta,
    Problem,
)
from app.quote import compute_quote
from app.ulid import generate_deterministic_ulid, generate_ulid

app = FastAPI(title="shipping-python-ch12")


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _with_links(booking: Booking) -> Booking:
    """Computes `_links` fresh from `booking`'s CURRENT status and returns a
    copy carrying them. Every response-building call site routes through
    here rather than storing links on the Booking kept in app/store.py, so
    a transition can never leave a stale link behind. Mirrors
    ../quarkus/.../BookingResource.java#withLinks.
    """
    return booking.model_copy(update={"links": links_for_booking(booking.id, booking.status)})


def _json(status_code: int, model, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=model.model_dump(mode="json", exclude_none=True, by_alias=True),
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
    return _json(201, _with_links(booking), headers={"Location": f"/bookings/{booking.id}"})


@app.get("/bookings")
def list_bookings(limit: int = 20) -> JSONResponse:
    visible = [_with_links(b) for b in store.list_visible()]
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
    return _json(200, _with_links(booking))


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
    return _json(200, _with_links(updated))


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
    return _json(200, _with_links(updated))


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
# State transitions — these drive the booking lifecycle FSM so verify.sh can
# observe a DIFFERENT `_links` set at each state. Not part of the shared
# OpenAPI contract (ch10's async 202/poll/303 `/confirmation` protocol is
# the contract-level version of `confirm`); this chapter keeps each
# transition a single synchronous 200 on purpose, to isolate the HATEOAS
# behavior from the async protocol taught in Ch10. Mirrors
# ../quarkus/.../BookingResource.java's confirmBooking/startTransit/
# deliverBooking/transition.
# ---------------------------------------------------------------------------

def _transition(
    booking_id: str, required_current: BookingStatus, next_status: BookingStatus, verb_phrase: str
) -> JSONResponse:
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    if existing.status != required_current:
        return _problem(
            409,
            "Invalid state transition",
            f"Booking {booking_id} is {existing.status.value}; only a "
            f"{required_current.value} booking can be {verb_phrase}",
        )
    updated = existing.model_copy(update={"status": next_status, "updatedAt": _now_utc()})
    store.put(updated)
    return _json(200, _with_links(updated))


@app.post("/bookings/{booking_id}/confirmation")
def confirm_booking(booking_id: str) -> JSONResponse:
    return _transition(booking_id, BookingStatus.PENDING, BookingStatus.CONFIRMED, "confirmed")


@app.post("/bookings/{booking_id}/transit")
def start_transit(booking_id: str) -> JSONResponse:
    return _transition(booking_id, BookingStatus.CONFIRMED, BookingStatus.IN_TRANSIT, "moved to IN_TRANSIT")


@app.post("/bookings/{booking_id}/delivery")
def deliver_booking(booking_id: str) -> JSONResponse:
    return _transition(booking_id, BookingStatus.IN_TRANSIT, BookingStatus.DELIVERED, "delivered")
