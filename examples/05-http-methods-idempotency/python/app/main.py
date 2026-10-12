"""Ch5 HTTP methods & idempotency — FastAPI side.

Extends the Ch4 contract-first anchor's Booking + Cargo resource model from
contracts/openapi/shipping-api.yaml with the full method matrix — GET/POST
on the collection, GET/PUT/PATCH/DELETE/HEAD on an item, explicit 405s for
methods the resource doesn't support, and the idempotency semantics that
distinguish them (PUT replaces the same resource state on every call; POST
mints a new resource every call; DELETE is idempotent in end-state even
though its status code is not: 204 then 404). Every response body here is
schema-validated by this example's verify.sh against
contracts/schemas/shipping.schema.json.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app import store
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

app = FastAPI(title="shipping-python-ch05")


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


def _problem(
    status_code: int,
    title: str,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = Problem(title=title, status=status_code, detail=detail)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
        headers=headers,
    )


# Methods each resource supports, used both for the explicit 405 handlers
# below and as the Allow header value on them.
_ALLOW_COLLECTION = "GET, POST"
_ALLOW_ITEM = "GET, PUT, PATCH, DELETE, HEAD"


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


@app.put("/bookings")
def replace_collection_not_allowed() -> JSONResponse:
    """The collection resource doesn't support PUT (there's no single
    "whole collection" state to replace) — 405 with an Allow header naming
    what it DOES support, and a Problem body instead of an empty one, so a
    caller script doesn't have to special-case this resource's error shape.
    """
    return _problem(
        405,
        "Method Not Allowed",
        "PUT is not supported on the /bookings collection; PUT a specific item at /bookings/{id} instead",
        headers={"Allow": _ALLOW_COLLECTION},
    )


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str) -> JSONResponse:
    booking = store.get_active(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return _json(200, booking)


@app.head("/bookings/{booking_id}")
def head_booking(booking_id: str) -> Response:
    """Unlike bare Starlette, FastAPI's APIRoute does NOT auto-register
    HEAD alongside a GET route (it sets `route.methods` directly rather
    than going through Starlette's Route.__init__, which is the thing that
    adds HEAD) — confirmed empirically: an un-routed HEAD here 405s. So
    this app needs its own HEAD handler: same status as the equivalent
    GET, no body, matching Content-Type when there's a representation.
    """
    booking = store.get_active(booking_id)
    if booking is None:
        return Response(status_code=404, media_type="application/problem+json")
    return Response(status_code=200, media_type="application/json")


@app.post("/bookings/{booking_id}")
def create_on_item_not_allowed(booking_id: str) -> JSONResponse:
    """An item resource doesn't support POST (POST-to-create belongs on
    the collection, at /bookings) — 405 + Allow + Problem, same shape as
    the collection's PUT rejection above.
    """
    return _problem(
        405,
        "Method Not Allowed",
        "POST is not supported on an individual booking; POST a new booking to /bookings instead",
        headers={"Allow": _ALLOW_ITEM},
    )


@app.put("/bookings/{booking_id}")
def replace_booking(booking_id: str, payload: BookingRequest) -> JSONResponse:
    existing = store.get_active(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    # Deterministic (not random) cargo ids: PUT must be idempotent, so
    # replacing a booking with the SAME body twice has to produce the SAME
    # Cargo.id for each item both times — generate_ulid() below mints a
    # fresh random id every call, which POST correctly wants but PUT must
    # not.
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

    existing = store.get_active(booking_id)
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
    # Idempotent in END STATE, not in status code: the first DELETE of a
    # live booking soft-deletes it and returns 204; every DELETE after that
    # (the id never existed, or it's already cancelled) returns 404 —
    # "already gone" — because get_active() treats a cancelled booking the
    # same as a missing one. The resource ends up cancelled either way,
    # which is what idempotency actually promises.
    existing = store.get_active(booking_id)
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
    booking = store.get_active(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return JSONResponse(
        status_code=200,
        content=[c.model_dump(mode="json", exclude_none=True) for c in booking.cargo],
    )


@app.post("/bookings/{booking_id}/cargo")
def add_cargo(booking_id: str, payload: CargoRequest) -> JSONResponse:
    booking = store.get_active(booking_id)
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
