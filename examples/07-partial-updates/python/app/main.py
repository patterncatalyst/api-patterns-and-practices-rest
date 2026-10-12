"""Ch7 partial-updates — FastAPI side.

Extends the Ch4 contract-first anchor's Booking + Cargo resource model
(contracts/openapi/shipping-api.yaml) with BOTH partial-update media types
on `PATCH /bookings/{booking_id}`: `application/merge-patch+json` (RFC
7396, kept from Ch4) and `application/json-patch+json` (RFC 6902, new
here, see app/json_patch.py). The single `@app.patch` route dispatches on
the `Content-Type` header itself — FastAPI/Starlette has no built-in
per-Content-Type routing the way JAX-RS's `@Consumes` does — and any other
Content-Type (including none at all, or `text/plain`) comes back as 415.
Every response body here is schema-validated by this example's verify.sh
against contracts/schemas/shipping.schema.json.
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
from app.json_patch import JsonPatchError, JsonPatchTestFailed, apply_patch
from app.quote import compute_quote
from app.ulid import generate_deterministic_ulid, generate_ulid

app = FastAPI(title="shipping-python-ch07")


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
    """Dispatch on Content-Type to one of this chapter's two partial-update
    media types. Starlette's routing is path-based only (unlike JAX-RS's
    `@Consumes`, which can route the SAME path to different methods by
    Content-Type), so the dispatch has to happen by hand, here."""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/merge-patch+json"):
        return await _patch_merge(booking_id, request)
    if content_type.startswith("application/json-patch+json"):
        return await _patch_json_patch(booking_id, request)
    return _problem(
        415,
        "Unsupported Media Type",
        "PATCH requires Content-Type: application/merge-patch+json or application/json-patch+json",
    )


async def _patch_merge(booking_id: str, request: Request) -> JSONResponse:
    """RFC 7396 JSON Merge Patch — a partial object; a field set to `null`
    DELETES that field; nested objects merge recursively."""
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


async def _patch_json_patch(booking_id: str, request: Request) -> JSONResponse:
    """RFC 6902 JSON Patch — a sequence of operations (add/remove/replace/
    move/copy/test) addressed by JSON Pointer, applied in order. A failed
    `test` operation is a 409 Conflict (the request is well-formed, but its
    precondition on the current resource state didn't hold); any other
    malformed/out-of-range operation is a 422 Unprocessable Content."""
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    try:
        operations = await request.json()
    except Exception:
        return _problem(422, "Invalid JSON Patch", "request body is not valid JSON")

    current = existing.model_dump(mode="json", exclude_none=True)
    try:
        patched = apply_patch(current, operations)
    except JsonPatchTestFailed as exc:
        return _problem(409, "JSON Patch test failed", str(exc))
    except JsonPatchError as exc:
        return _problem(422, "Invalid JSON Patch", str(exc))

    # id/createdAt are server-assigned (readOnly in the schema); a JSON
    # Patch can never overwrite them, regardless of what operations the
    # client sent.
    if not isinstance(patched, dict):
        return _problem(422, "Invalid JSON Patch result", "patched document is not a JSON object")
    patched["id"] = existing.id
    patched["createdAt"] = existing.createdAt
    patched["updatedAt"] = _now_utc()

    try:
        updated = Booking.model_validate(patched)
    except ValidationError as exc:
        return _problem(422, "Invalid JSON Patch result", str(exc.errors()))

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
