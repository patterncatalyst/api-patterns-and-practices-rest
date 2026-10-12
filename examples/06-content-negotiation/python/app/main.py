"""Ch6 content negotiation & status codes — FastAPI side.

Extends the Ch4 contract-first anchor's Booking + Cargo resource model from
contracts/openapi/shipping-api.yaml with explicit Accept/Content-Type
negotiation and a full status-code discipline pass across the booking
operations. Every response body here is schema-validated by this example's
verify.sh against contracts/schemas/shipping.schema.json.

FastAPI does none of this negotiation for free, unlike the Quarkus side:
RESTEasy Reactive raises NotAcceptableException/NotSupportedException itself
when a resource method's @Produces/@Consumes can't be satisfied, straight
from the JAX-RS content-negotiation algorithm. FastAPI's routing has no
equivalent — a pydantic body parameter is parsed as JSON regardless of the
request's Content-Type header, and nothing ever inspects Accept — so both
checks are implemented by hand here (`_check_accept` / `_check_content_type`)
and called explicitly at the top of every handler that needs them, mirroring
what the Quarkus side's @Produces/@Consumes annotations buy automatically.
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

app = FastAPI(title="shipping-python-ch06")


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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _problem(400, "Validation failed", str(exc.errors()))


# ---------------------------------------------------------------------------
# Content negotiation (406 Accept / 415 Content-Type)
#
# Mirrors what the Quarkus side's @Produces({APPLICATION_JSON, PROBLEM_JSON})
# / @Consumes(APPLICATION_JSON) declarations buy for free from RESTEasy
# Reactive's content-negotiation algorithm (JAX-RS 2.1 §3.8).
# ---------------------------------------------------------------------------

_PRODUCIBLE_MEDIA_TYPES = ("application/json", "application/problem+json")


def _parse_media_types(header_value: str) -> list[str]:
    """Media types from a comma-separated header, q-values/params stripped."""
    if not header_value:
        return []
    return [part.split(";")[0].strip().lower() for part in header_value.split(",") if part.strip()]


def _check_accept(request: Request) -> JSONResponse | None:
    """406 guard: an absent/empty Accept header means "anything" (RFC 9110
    §12.5.1), so only a header that NAMES types and excludes every type this
    API can produce is a conflict.
    """
    accepted = _parse_media_types(request.headers.get("accept", ""))
    if not accepted:
        return None
    for media_type in accepted:
        if media_type in ("*/*", "application/*") or media_type in _PRODUCIBLE_MEDIA_TYPES:
            return None
    return _problem(
        406,
        "Not Acceptable",
        "The Accept header does not match a media type this endpoint can produce "
        f"(application/json, application/problem+json); got Accept: {request.headers.get('accept', '')}",
    )


def _check_content_type(request: Request, expected: str = "application/json") -> JSONResponse | None:
    """415 guard: the request body's Content-Type must match `expected`
    exactly (ignoring any ``; charset=...`` parameter) — a body sent with
    the wrong media type never reaches the pydantic parser.
    """
    content_type = _parse_media_types(request.headers.get("content-type", ""))
    if content_type and content_type[0] == expected:
        return None
    return _problem(
        415,
        "Unsupported Media Type",
        f"The request's Content-Type is not one this endpoint accepts (expected {expected}); "
        f"got Content-Type: {request.headers.get('content-type') or '(none)'}",
    )


async def _parse_json_body(request: Request) -> tuple[Any, JSONResponse | None]:
    """Parse the raw request body as JSON, returning a 400 Problem on
    failure instead of letting an unhandled JSONDecodeError 500.
    """
    try:
        return await request.json(), None
    except Exception:
        return None, _problem(400, "Invalid request body", "request body is not valid JSON")


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
async def create_booking(request: Request) -> JSONResponse:
    if (problem := _check_content_type(request)) is not None:
        return problem
    if (problem := _check_accept(request)) is not None:
        return problem

    raw, problem = await _parse_json_body(request)
    if problem is not None:
        return problem
    try:
        payload = BookingRequest.model_validate(raw)
    except ValidationError as exc:
        return _problem(400, "Invalid booking request", str(exc.errors()))

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
def list_bookings(request: Request, limit: int = 20) -> JSONResponse:
    if (problem := _check_accept(request)) is not None:
        return problem
    visible = store.list_visible()
    collection = BookingCollection(
        items=visible,
        page=PageMeta(limit=limit, count=len(visible), nextCursor=None),
    )
    return _json(200, collection)


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str, request: Request) -> JSONResponse:
    if (problem := _check_accept(request)) is not None:
        return problem
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return _json(200, booking)


@app.put("/bookings/{booking_id}")
async def replace_booking(booking_id: str, request: Request) -> JSONResponse:
    if (problem := _check_content_type(request)) is not None:
        return problem
    if (problem := _check_accept(request)) is not None:
        return problem

    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    raw, problem = await _parse_json_body(request)
    if problem is not None:
        return problem
    try:
        payload = BookingRequest.model_validate(raw)
    except ValidationError as exc:
        return _problem(400, "Invalid booking request", str(exc.errors()))

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
    if (problem := _check_content_type(request, "application/merge-patch+json")) is not None:
        return problem
    if (problem := _check_accept(request)) is not None:
        return problem

    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    patch_doc, problem = await _parse_json_body(request)
    if problem is not None:
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
def delete_booking(booking_id: str, request: Request) -> Response:
    if (problem := _check_accept(request)) is not None:
        return problem
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    cancelled = existing.model_copy(update={"status": BookingStatus.CANCELLED, "updatedAt": _now_utc()})
    store.put(cancelled)
    return Response(status_code=204)


@app.post("/bookings/{booking_id}/confirm")
def confirm_booking(booking_id: str, request: Request) -> JSONResponse:
    """409 Conflict path: confirming a booking is only valid from PENDING —
    confirming it twice, or confirming one that's already
    cancelled/in-transit/delivered, is a state conflict, not a validation
    error (the request is well-formed; the resource just isn't in a state
    that allows it). This rounds out the status-code table: 200 on success,
    404 if the booking doesn't exist, 409 if it exists but is in the wrong
    state. Mirrors Quarkus's confirmBooking.
    """
    if (problem := _check_accept(request)) is not None:
        return problem
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    if existing.status != BookingStatus.PENDING:
        return _problem(
            409,
            "Conflict",
            f"Booking {booking_id} cannot be confirmed from status {existing.status.value}; "
            "only a PENDING booking can be confirmed",
        )
    confirmed = existing.model_copy(update={"status": BookingStatus.CONFIRMED, "updatedAt": _now_utc()})
    store.put(confirmed)
    return _json(200, confirmed)


# ---------------------------------------------------------------------------
# Cargo sub-resource
# ---------------------------------------------------------------------------

@app.get("/bookings/{booking_id}/cargo")
def list_cargo(booking_id: str, request: Request) -> JSONResponse:
    if (problem := _check_accept(request)) is not None:
        return problem
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return JSONResponse(
        status_code=200,
        content=[c.model_dump(mode="json", exclude_none=True) for c in booking.cargo],
    )


@app.post("/bookings/{booking_id}/cargo")
async def add_cargo(booking_id: str, request: Request) -> JSONResponse:
    if (problem := _check_content_type(request)) is not None:
        return problem
    if (problem := _check_accept(request)) is not None:
        return problem

    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    raw, problem = await _parse_json_body(request)
    if problem is not None:
        return problem
    try:
        payload = CargoRequest.model_validate(raw)
    except ValidationError as exc:
        return _problem(400, "Invalid cargo request", str(exc.errors()))

    cargo = Cargo(id=f"crg_{generate_ulid()}", **payload.model_dump())
    new_cargo_list = [*booking.cargo, cargo]
    updated = booking.model_copy(update={
        "cargo": new_cargo_list,
        "quote": compute_quote(new_cargo_list),
        "updatedAt": _now_utc(),
    })
    store.put(updated)
    return _json(201, cargo, headers={"Location": f"/bookings/{booking_id}/cargo/{cargo.id}"})
