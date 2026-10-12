"""Ch20 OpenAPI-in-depth anchor — FastAPI side.

Two things live here:

1. A trimmed LIVE booking resource (create + fetch only — the full
   create/read/list/cargo/replace/patch/delete sequence already lives in
   Ch4) so verify.sh has a real round trip to schema-validate against
   contracts/schemas/shipping.schema.json.
2. A CUSTOM OpenAPI document (`custom_openapi`, wired onto `app.openapi`)
   demonstrating two OpenAPI-3.1 / full-JSON-Schema-alignment capabilities:
   a top-level `webhooks` section (native FastAPI support via the
   `webhooks=` constructor argument) and a `type`-array nullable property
   patched onto the generated Booking schema (pydantic v2's default
   `Optional[str]` rendering is `anyOf: [{type: string}, {type: null}]`,
   not the `type: ["string", "null"]` array form this chapter is
   demonstrating — the patch below makes that construct explicit and
   deterministic rather than relying on a generator's internal choice).
   See README.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app import store
from app.models import (
    Booking,
    BookingEvent,
    BookingRequest,
    BookingStatus,
    Cargo,
    Problem,
)
from app.quote import compute_quote
from app.ulid import generate_ulid

# ---------------------------------------------------------------------------
# Webhooks (OpenAPI 3.1 top-level `webhooks` section).
#
# FastAPI never CALLS these — a webhooks router only documents an outbound
# notification a real deployment would POST to a client-registered callback
# URL. Passing it to FastAPI(webhooks=...) is enough for it to render under
# the `webhooks` key of /openapi.json once `openapi_version` is 3.1 (FastAPI's
# default since 0.99.0).
# ---------------------------------------------------------------------------

webhooks_router = APIRouter()


@webhooks_router.post(
    "bookingStatusChanged",
    response_model=BookingEvent,
    summary="Notify a registered callback URL when a booking's status changes",
)
def booking_status_changed(body: BookingEvent) -> None:
    """Documentation-only — see module docstring. Never invoked."""


app = FastAPI(title="shipping-python-ch20", webhooks=webhooks_router)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version="1.0.0",
        routes=app.routes,
        webhooks=app.webhooks.routes,
    )

    # Patch an OpenAPI-3.1 `type` ARRAY nullable property onto Booking — see
    # module docstring for why this is a deliberate patch rather than a
    # bare pydantic-generated field. Mirrors the Quarkus side's
    # `cancellationReason` (META-INF/openapi.yaml) field-for-field: same
    # name, same description, same illustrative (non-required, not part of
    # the actual Booking response body) status. Flip this to
    # `"nullable": True` (OAS-3.0 style) and verify.sh's "nullable
    # construct present" check still passes; delete it and watch it fail.
    booking_schema = schema["components"]["schemas"]["Booking"]
    booking_schema["properties"]["cancellationReason"] = {
        "description": (
            "Null until the booking is cancelled. Declared as an OpenAPI "
            "3.1 JSON Schema `type` ARRAY ([\"string\", \"null\"]) rather "
            "than an OAS-3.0 `nullable: true` flag — full JSON Schema "
            "alignment is one of this chapter's two headline OpenAPI-3.1 "
            "capabilities."
        ),
        "type": ["string", "null"],
    }

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


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
# Bookings — trimmed to create + fetch (see module docstring)
# ---------------------------------------------------------------------------

@app.post("/bookings", response_model=Booking, status_code=201)
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


@app.get("/bookings/{booking_id}", response_model=Booking)
def get_booking(booking_id: str) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return _json(200, booking)
