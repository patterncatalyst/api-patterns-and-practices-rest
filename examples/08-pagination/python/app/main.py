"""Ch8 filtering, projection & pagination — FastAPI side.

Extends the Ch4 contract-first Booking + Cargo resource model with three
pagination strategies (offset, keyset/cursor, seek) and sparse fieldset
projection on GET /bookings, backed by the same in-memory store. Every
non-projected response body is still schema-validated by
examples/08-pagination's verify.sh against
contracts/schemas/shipping.schema.json.
"""
from __future__ import annotations

import base64
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

app = FastAPI(title="shipping-python-ch08")

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100  # DoS guard: `limit` above this is clamped, never honored unbounded.


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


def _clamp_limit(limit: int | None) -> int:
    """DoS guard: `limit` above `_MAX_LIMIT` is CLAMPED, never honored
    unbounded (matches `#/$defs/PageMeta.limit`'s `maximum: 100` in the
    shared schema). An unbounded limit lets a client force the server to
    materialize and serialize an arbitrarily large response in one shot."""
    effective = _DEFAULT_LIMIT if limit is None else limit
    return max(1, min(effective, _MAX_LIMIT))


def _encode_cursor(booking_id: str) -> str:
    """Opaque cursor = base64url of the last-seen booking id. Callers must
    treat it as opaque; this encoding is an implementation detail."""
    return base64.urlsafe_b64encode(booking_id.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> str | None:
    """A malformed cursor is treated as "start from the beginning" rather
    than failing the request — a client replaying a stale/corrupted cursor
    still gets a valid (if restarted) page."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def _compute_page(
    visible: list[Booking],
    offset: int | None,
    after_id: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[Booking], str | None]:
    """Resolves exactly one of three mutually-exclusive strategies, in
    precedence order: offset > after_id (seek) > cursor (keyset, default).
    `visible` must already be sorted ascending by id (see
    store.list_visible())."""
    if offset is not None:
        off = max(0, offset)
        return visible[off : off + limit], None

    if after_id:
        candidates = [b for b in visible if b.id > after_id]
        return candidates[:limit], None

    # Keyset/cursor — the default/stable strategy. A null/blank cursor
    # means "first page"; following page.nextCursor walks the whole set
    # with no dupes or gaps, because each page's lower bound is the highest
    # id actually returned by the page before it.
    after_key = _decode_cursor(cursor) if cursor else None
    candidates = visible if after_key is None else [b for b in visible if b.id > after_key]
    page_items = candidates[:limit]
    next_cursor = _encode_cursor(page_items[-1].id) if len(candidates) > limit else None
    return page_items, next_cursor


def _project(items: list[Booking], fields: str) -> list[dict[str, Any]]:
    """Sparse fieldset projection. `id` is always included regardless of
    whether it was requested. The result is a list of plain dicts, NOT
    `Booking` models, because a projected item generally fails the full
    `Booking` schema (missing required properties) — that's expected and
    documented in README.md, not a bug."""
    requested = [f.strip() for f in fields.split(",") if f.strip()]
    projected: list[dict[str, Any]] = []
    for booking in items:
        full = booking.model_dump(mode="json", exclude_none=True)
        item: dict[str, Any] = {"id": full["id"]}
        for field in requested:
            if field != "id" and field in full:
                item[field] = full[field]
        projected.append(item)
    return projected


@app.get("/bookings")
def list_bookings(
    limit: int | None = None,
    offset: int | None = None,
    after_id: str | None = None,
    cursor: str | None = None,
    fields: str | None = None,
) -> JSONResponse:
    """Four orthogonal query knobs, documented in
    examples/08-pagination/README.md: `limit` (clamped page size),
    `offset` (classic pagination), `after_id` (seek pagination, takes
    precedence over cursor), `cursor` (keyset pagination, the
    DEFAULT/stable strategy), and `fields` (sparse fieldset — when
    present the response is NOT a schema-conforming `BookingCollection`,
    built by hand instead of through the `Booking` model)."""
    visible = store.list_visible()
    effective_limit = _clamp_limit(limit)
    page_items, next_cursor = _compute_page(visible, offset, after_id, cursor, effective_limit)
    page_meta = PageMeta(limit=effective_limit, count=len(page_items), nextCursor=next_cursor)

    if not fields:
        collection = BookingCollection(items=page_items, page=page_meta)
        return _json(200, collection)

    return JSONResponse(
        status_code=200,
        content={
            "items": _project(page_items, fields),
            "page": page_meta.model_dump(mode="json", exclude_none=True),
        },
    )


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
