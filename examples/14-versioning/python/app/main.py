"""Ch14 versioning example — FastAPI side.

The Ch4 contract-first Booking + Cargo resource model (quote + cargo[]),
backed by an in-memory store, extended with TWO versioning strategies that
both serve the SAME stored booking in two representations:

  - URI versioning: GET /v1/bookings/{id} (frozen BookingV1: price +
    cargoDescription) vs. GET /v2/bookings/{id} (current Booking).
  - Media-type (content-negotiation) versioning: GET /bookings/{id}, where
    the Accept header -- application/vnd.shipping.v1+json vs.
    application/vnd.shipping.v2+json (or plain application/json) -- picks
    the representation. See _negotiate_version() and README.md.

Every v2 response body is schema-validated by verify.sh against
contracts/schemas/shipping.schema.json; v1 isn't in that shared schema (it's
a frozen stub in contracts/openapi/shipping-api-v1.yaml), so verify.sh
checks its shape by hand.
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
    BookingV1,
    Cargo,
    CargoRequest,
    PageMeta,
    Problem,
)
from app.quote import compute_quote
from app.ulid import generate_deterministic_ulid, generate_ulid

app = FastAPI(title="shipping-python-ch14")

# Vendor media types negotiated via the Accept header (RFC 6838 vendor tree).
MEDIA_TYPE_V1 = "application/vnd.shipping.v1+json"
MEDIA_TYPE_V2 = "application/vnd.shipping.v2+json"


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


def _wants_v1(accept_header: str | None) -> bool:
    """True iff the Accept header explicitly asks for the v1 vendor type.

    Anything else -- the v2 vendor type, a bare application/json, */*, or a
    missing header entirely -- means "give me the current representation",
    same as if no version had been requested at all.
    """
    return bool(accept_header) and MEDIA_TYPE_V1 in accept_header


def _to_v1(booking: Booking) -> BookingV1:
    """Project the one stored (v2-shaped) booking into the frozen v1 shape.

    v1's single `cargoDescription` string is built by joining each v2
    cargo item's description -- a LOSSY, one-way projection: v1 has no way
    to recover individual cargo items, weights, or hazardous flags from
    that string alone. That's the real cost of carrying an old
    representation forward: it can only describe what its shape had room
    for.
    """
    return BookingV1(
        id=booking.id,
        status=booking.status,
        origin=booking.origin,
        destination=booking.destination,
        cargoDescription="; ".join(item.description for item in booking.cargo),
        price=booking.quote,
        createdAt=booking.createdAt,
    )


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str, request: Request) -> JSONResponse:
    """MEDIA-TYPE (content-negotiation) versioning: the Accept header, not
    the URL, picks which representation of this ONE booking comes back.
    The response Content-Type always echoes the NEGOTIATED vendor type
    (never just whatever the client happened to send), and every response
    carries `Vary: Accept` -- a shared HTTP cache MUST treat this URL as
    having more than one representation, or it will serve a cached v1 body
    to a client that asked for v2 (see README.md).
    """
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    accept_header = request.headers.get("accept")
    if _wants_v1(accept_header):
        body = _to_v1(booking)
        media_type = MEDIA_TYPE_V1
    else:
        body = booking
        media_type = MEDIA_TYPE_V2

    return JSONResponse(
        status_code=200,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type=media_type,
        headers={"Vary": "Accept"},
    )


@app.get("/v1/bookings/{booking_id}")
def get_booking_v1(booking_id: str) -> JSONResponse:
    """URI versioning, v1 side: always the FROZEN BookingV1 shape (price +
    cargoDescription), regardless of any Accept header -- the URL itself is
    the version pin. Read-only: v1 is a frozen stub for teaching the
    breaking change, not a maintained write API (see README.md).
    """
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return JSONResponse(
        status_code=200,
        content=_to_v1(booking).model_dump(mode="json", exclude_none=True),
        media_type=MEDIA_TYPE_V1,
    )


@app.get("/v2/bookings/{booking_id}")
def get_booking_v2(booking_id: str) -> JSONResponse:
    """URI versioning, v2 side: always the CURRENT Booking shape (quote +
    cargo[]), regardless of any Accept header. The unversioned
    GET /bookings/{id} above also serves this shape by default -- URI
    versioning and "no version pin at all" agree on what "current" means.
    """
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
