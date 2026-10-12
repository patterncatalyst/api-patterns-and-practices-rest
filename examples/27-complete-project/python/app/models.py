"""Pydantic mirrors of contracts/schemas/shipping.schema.json's $defs, plus
the two local (non-contract) shapes this example needs: DeletionAudit
(Ch13) and BookingV1 (Ch14). Field names, requiredness, patterns and
`extra="forbid"` intentionally match the shared schema so a shape drift
here surfaces as a pydantic validation error on the way in, and as a
validate_response.py failure on the way out (see ../../_lib/validate_response.py).
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CargoType(str, Enum):
    GENERAL = "GENERAL"
    REFRIGERATED = "REFRIGERATED"
    HAZARDOUS = "HAZARDOUS"
    OVERSIZED = "OVERSIZED"
    LIQUID_BULK = "LIQUID_BULK"


class BookingStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class OperationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Money(BaseModel):
    """`#/$defs/Money` — amount is a DECIMAL STRING, never a JSON number."""

    model_config = ConfigDict(extra="forbid")

    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: str = Field(pattern=r"^-?[0-9]+\.[0-9]{2}$")


class Location(BaseModel):
    """`#/$defs/Location` — a port or terminal identified by UN/LOCODE."""

    model_config = ConfigDict(extra="forbid")

    unLocode: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]{3}$")
    name: Optional[str] = None
    country: Optional[str] = Field(default=None, pattern=r"^[A-Z]{2}$")


class Dimensions(BaseModel):
    """`#/$defs/Dimensions` — physical measure of a cargo item."""

    model_config = ConfigDict(extra="forbid")

    weightKg: float = Field(gt=0)
    volumeM3: Optional[float] = Field(default=None, gt=0)


class Link(BaseModel):
    """`#/$defs/Link` — a single HATEOAS link (RFC 8288-style relation):
    `{href, method, title}`."""

    model_config = ConfigDict(extra="forbid")

    href: str
    method: str = "GET"
    title: Optional[str] = None


class CargoRequest(BaseModel):
    """`#/$defs/CargoRequest` — client payload to add cargo (no server id)."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=280)
    type: CargoType
    dimensions: Dimensions
    hazardous: bool = False


class Cargo(CargoRequest):
    """`#/$defs/Cargo` — one cargo item carried under a booking."""

    id: str


class BookingRequest(BaseModel):
    """`#/$defs/BookingRequest` — client payload to create a booking."""

    model_config = ConfigDict(extra="forbid")

    origin: Location
    destination: Location
    cargo: list[CargoRequest] = Field(min_length=1)
    requestedPickup: Optional[date] = None


class Booking(BaseModel):
    """`#/$defs/Booking` — the aggregate root.

    `links` is serialized as `_links` via the `_links` alias (Ch12
    HATEOAS) — see `hateoas.links_for_booking`, which computes exactly the
    relations valid from the booking's CURRENT `status`. Responses are
    always serialized with `exclude_none=True` and `by_alias=True` (see
    main.py's `_json` helper).
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    status: BookingStatus
    origin: Location
    destination: Location
    cargo: list[Cargo] = Field(min_length=1)
    quote: Optional[Money] = None
    requestedPickup: Optional[date] = None
    createdAt: str
    updatedAt: Optional[str] = None
    links: Optional[dict[str, Link]] = Field(default=None, alias="_links")


class BookingV1(BaseModel):
    """The FROZEN v1 representation negotiated via
    `Accept: application/vnd.shipping.booking.v1+json` (Ch14 media-type
    versioning). Two shape differences from `Booking` (v2) make v1 -> v2 a
    breaking (major) change: `price` here vs. `quote` (same `Money` value,
    renamed field), and a single `cargoDescription` string here vs. an
    array of `Cargo` items (`cargo`). No `_links` (HATEOAS postdates v1)
    and no `updatedAt`. Never built from client input; always projected
    from the one stored (v2-shaped) `Booking` via `_to_v1()` in main.py.
    NOT in the shared contract schema — verify.sh checks its shape by
    hand.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    status: BookingStatus
    origin: Location
    destination: Location
    cargoDescription: str
    price: Optional[Money] = None
    createdAt: str


class PageMeta(BaseModel):
    """`#/$defs/PageMeta` — keyset-pagination metadata (Ch8). `nextCursor`
    is null on the last page."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(ge=1, le=100, default=20)
    count: int = Field(ge=0)
    nextCursor: Optional[str] = None


class BookingCollection(BaseModel):
    """`#/$defs/BookingCollection` — a page of bookings with keyset
    pagination and collection-level HATEOAS links (`self`, and `next` when
    another page exists)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    items: list[Booking]
    page: PageMeta
    links: Optional[dict[str, Link]] = Field(default=None, alias="_links")


class Problem(BaseModel):
    """`#/$defs/Problem` — RFC 9457 Problem Details (application/problem+json)."""

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: Optional[str] = None
    instance: Optional[str] = None


class Operation(BaseModel):
    """`#/$defs/Operation` — a long-running server operation record (202
    Accepted -> poll -> 303, Ch10)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: OperationStatus
    createdAt: str
    completedAt: Optional[str] = None
    resource: Optional[str] = None
    error: Optional[Problem] = None


class DeletionAudit(BaseModel):
    """Local audit-trail shape — NOT part of the shared contract schema
    (Ch13). A soft-delete (`DELETE /bookings/{id}`) records one of these; a
    purge (`DELETE /bookings/{id}/purge`) erases it along with the booking
    itself. Rides along as response HEADERS on the audit view rather than
    as extra `Booking` fields, since the schema declares
    `additionalProperties: false` on `Booking`.
    """

    deletedAt: str
    reason: str


class BookingEvent(BaseModel):
    """`#/$defs/BookingEvent` — a domain-event payload describing a
    booking state change. Used both as the CloudEvents `data` published to
    Kafka (Ch21) and as the record shape streamed by the NDJSON manifest
    export (Ch16)."""

    model_config = ConfigDict(extra="forbid")

    bookingId: str
    status: BookingStatus
    previousStatus: Optional[BookingStatus] = None
    origin: Optional[Location] = None
    destination: Optional[Location] = None
    occurredAt: str
