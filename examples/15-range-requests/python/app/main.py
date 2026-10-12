"""Ch15 large binary resources & Range — FastAPI side.

A thin Ch4-style Booking resource (POST to create, GET by id — just enough
to mint a booking id) plus /bookings/{id}/manifest implementing HTTP Range
requests (RFC 9110 §14) over a deterministic, fixed-size, in-memory
"manifest" blob (see app/manifest.py). The JSON Booking/Problem responses
here are schema-validated by examples/15-range-requests's verify.sh against
contracts/schemas/shipping.schema.json; the manifest's binary body is
validated by byte count and Range/Content-Range headers instead — the
shared contract declares its media type (`application/pdf`) but, being
binary, doesn't (and can't) pin an exact byte pattern for it.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app import store
from app.manifest import get_manifest
from app.models import Booking, BookingRequest, BookingStatus, Cargo, Problem
from app.ulid import generate_ulid

app = FastAPI(title="shipping-python-ch15")

# bytes=START-END, bytes=START- (open), or bytes=-SUFFIXLEN (suffix).
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


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
# Bookings (thin — just enough to mint an id for the manifest below)
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


# ---------------------------------------------------------------------------
# Manifest — the large binary resource, with Range support
# ---------------------------------------------------------------------------

def _booking_or_404(booking_id: str) -> JSONResponse | None:
    if store.get(booking_id) is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return None


@app.head("/bookings/{booking_id}/manifest")
def head_manifest(booking_id: str) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    data = get_manifest(booking_id)
    return Response(
        status_code=200,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(len(data))},
    )


@app.get("/bookings/{booking_id}/manifest")
def get_manifest_endpoint(
    booking_id: str,
    range_header: str | None = Header(default=None, alias="Range"),
) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    data = get_manifest(booking_id)
    total = len(data)

    if not range_header:
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Accept-Ranges": "bytes", "Content-Length": str(total)},
        )

    match = RANGE_RE.match(range_header.strip())
    if not match:
        # A malformed Range header is ignored per RFC 9110 §14.2 — fall back
        # to serving the full representation rather than rejecting outright.
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Accept-Ranges": "bytes", "Content-Length": str(total)},
        )

    start_group, end_group = match.groups()
    if start_group == "":
        if end_group == "":
            # "bytes=-" with neither bound: not a satisfiable range.
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        # Suffix range: bytes=-N -> the last N bytes of the resource.
        suffix_length = int(end_group)
        start = max(0, total - suffix_length)
        end = total - 1
    else:
        start = int(start_group)
        end = int(end_group) if end_group else total - 1

    if start >= total or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})

    end = min(end, total - 1)
    chunk = data[start : end + 1]
    return Response(
        content=chunk,
        status_code=206,
        media_type="application/pdf",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Content-Length": str(len(chunk)),
        },
    )
