"""Ch27 complete-project anchor — FastAPI side.

ONE booking service that exercises the whole book's flow end to end over a
single cohesive resource model: contract-first create/read (Ch4), keyset
pagination (Ch8), async confirmation 202->poll->303 (Ch10), HATEOAS
`_links` (Ch12), soft delete + GDPR purge (Ch13), media-type versioning
(Ch14), an incrementally-streamed NDJSON manifest (Ch16), and a background
CloudEvents publish to Kafka once a confirmation completes (Ch21). See
README.md for the full capability-to-chapter map.
"""
from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app import manifest, operations, store
from app.hateoas import links_for_booking, links_for_collection
from app.models import (
    Booking,
    BookingCollection,
    BookingRequest,
    BookingStatus,
    BookingV1,
    Cargo,
    CargoRequest,
    OperationStatus,
    PageMeta,
    Problem,
)
from app.quote import compute_quote
from app.ulid import generate_ulid

app = FastAPI(title="shipping-python-ch27")

# Vendor media types negotiated via the Accept header (Ch14).
MEDIA_TYPE_V1 = "application/vnd.shipping.booking.v1+json"
MEDIA_TYPE_V2 = "application/vnd.shipping.booking.v2+json"

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100  # DoS guard: `limit` above this is clamped, never honored unbounded.


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _with_links(booking: Booking) -> Booking:
    """Computes `_links` fresh from `booking`'s CURRENT status and returns a
    copy carrying them (Ch12). Mirrors ../quarkus/.../BookingResource.java#withLinks."""
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
# Bookings: create (Ch4)
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


# ---------------------------------------------------------------------------
# Bookings: list — Ch8 keyset pagination + Ch12 collection-level HATEOAS.
# ---------------------------------------------------------------------------

def _clamp_limit(limit: int | None) -> int:
    effective = _DEFAULT_LIMIT if limit is None else limit
    return max(1, min(effective, _MAX_LIMIT))


def _encode_cursor(booking_id: str) -> str:
    return base64.urlsafe_b64encode(booking_id.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> str | None:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:
        return None


@app.get("/bookings")
def list_bookings(limit: int | None = None, cursor: str | None = None) -> JSONResponse:
    visible = store.list_visible()
    effective_limit = _clamp_limit(limit)

    after_key = _decode_cursor(cursor) if cursor else None
    candidates = visible if after_key is None else [b for b in visible if b.id > after_key]
    page_items = candidates[:effective_limit]
    next_cursor = _encode_cursor(page_items[-1].id) if len(candidates) > effective_limit else None

    items_with_links = [_with_links(b) for b in page_items]
    page_meta = PageMeta(limit=effective_limit, count=len(items_with_links), nextCursor=next_cursor)
    collection = BookingCollection(
        items=items_with_links,
        page=page_meta,
        links=links_for_collection(effective_limit, next_cursor),
    )
    return _json(200, collection)


# ---------------------------------------------------------------------------
# Bookings: get — Ch14 media-type versioning + Ch13 soft-delete visibility.
# ---------------------------------------------------------------------------

def _to_v1(booking: Booking) -> BookingV1:
    """Project the one stored (v2-shaped) booking into the frozen v1 shape
    — a LOSSY, one-way projection."""
    return BookingV1(
        id=booking.id,
        status=booking.status,
        origin=booking.origin,
        destination=booking.destination,
        cargoDescription="; ".join(item.description for item in booking.cargo),
        price=booking.quote,
        createdAt=booking.createdAt,
    )


def _wants_v1(accept_header: str | None) -> bool:
    return bool(accept_header) and MEDIA_TYPE_V1 in accept_header


@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str, request: Request, includeDeleted: bool = False) -> JSONResponse:
    # Default clients never see a soft-deleted booking: it's "gone" to
    # them, even though the record is still in the store. The
    # audit/compliance view opts back in with includeDeleted=true.
    booking = store.get(booking_id) if includeDeleted else store.get_visible(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    accept_header = request.headers.get("accept")
    if _wants_v1(accept_header):
        body = _to_v1(booking)
        return JSONResponse(
            status_code=200,
            content=body.model_dump(mode="json", exclude_none=True),
            media_type=MEDIA_TYPE_V1,
            headers={"Vary": "Accept"},
        )

    headers = {"Vary": "Accept"}
    if includeDeleted and booking.status == BookingStatus.CANCELLED:
        audit = store.get_audit(booking_id)
        if audit is not None:
            headers["X-Audit-Deleted-At"] = audit.deletedAt
            headers["X-Audit-Reason"] = audit.reason

    return JSONResponse(
        status_code=200,
        content=_with_links(booking).model_dump(mode="json", exclude_none=True, by_alias=True),
        media_type=MEDIA_TYPE_V2,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Confirmation (Ch10: 202 Accepted -> poll /operations/{id} -> 303) — once
# it completes, app/operations.py flips the booking to CONFIRMED and
# publishes the Ch21 CloudEvent.
# ---------------------------------------------------------------------------

@app.post("/bookings/{booking_id}/confirmation", status_code=202)
async def request_confirmation(booking_id: str) -> JSONResponse:
    # async def (not def): FastAPI runs a plain `def` endpoint in a worker
    # thread via run_in_threadpool, which has no running asyncio event loop
    # — asyncio.create_task() inside operations.start_confirmation() needs
    # one.
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


@app.get("/operations/{operation_id}")
def get_operation(operation_id: str) -> Response:
    operation = operations.get(operation_id)
    if operation is None:
        return _problem(404, "Operation not found", f"No operation with id {operation_id}")
    if operation.status == OperationStatus.SUCCEEDED:
        return Response(status_code=303, headers={"Location": operation.resource})
    return _json(200, operation)


# ---------------------------------------------------------------------------
# Soft delete + GDPR purge (Ch13).
# ---------------------------------------------------------------------------

@app.delete("/bookings/{booking_id}", status_code=204)
def delete_booking(booking_id: str, reason: str = "user-requested cancellation") -> Response:
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    store.soft_delete(booking_id, reason)
    return Response(status_code=204)


@app.delete("/bookings/{booking_id}/purge", status_code=204)
def purge_booking(booking_id: str) -> Response:
    """GDPR "right to erasure": hard-deletes the booking AND its audit
    trail. Once purged, even `GET /bookings/{id}?includeDeleted=true` 404s."""
    existed = store.purge(booking_id)
    if not existed:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# NDJSON manifest export (Ch16-style incremental streaming).
# ---------------------------------------------------------------------------

async def _manifest_stream(booking_id: str) -> AsyncIterator[str]:
    for i in range(manifest.LINE_COUNT):
        await asyncio.sleep(manifest.INTERVAL_SECONDS)
        payload = manifest.event_for(booking_id, i)
        yield json.dumps(payload) + "\n"


@app.get("/bookings/{booking_id}/manifest/export")
async def export_manifest(booking_id: str) -> Response:
    if store.get(booking_id) is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return StreamingResponse(_manifest_stream(booking_id), media_type="application/x-ndjson")
