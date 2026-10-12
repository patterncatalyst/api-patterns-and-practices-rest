"""Pydantic mirrors of contracts/schemas/shipping.schema.json's $defs.

Field names, requiredness, patterns and `extra="forbid"` all intentionally
match the shared schema so a shape drift here surfaces as a pydantic
validation error on the way in, and as a validate_response.py failure on
the way out (see ../../_lib/validate_response.py).
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
    """`#/$defs/BookingRequest` — client payload to create/replace a booking."""

    model_config = ConfigDict(extra="forbid")

    origin: Location
    destination: Location
    cargo: list[CargoRequest] = Field(min_length=1)
    requestedPickup: Optional[date] = None


class Booking(BaseModel):
    """`#/$defs/Booking` — the aggregate root.

    `_links` is intentionally never populated (HATEOAS lands in Ch12);
    responses are always serialized with `exclude_none=True` so optional
    fields (`quote`, `requestedPickup`, `updatedAt`) are omitted rather than
    emitted as a JSON `null` the schema doesn't declare.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    status: BookingStatus
    origin: Location
    destination: Location
    cargo: list[Cargo] = Field(min_length=1)
    quote: Optional[Money] = None
    requestedPickup: Optional[date] = None
    createdAt: str
    updatedAt: Optional[str] = None


class PageMeta(BaseModel):
    """`#/$defs/PageMeta` — keyset-pagination metadata (full paging: Ch8)."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(ge=1, le=100, default=20)
    count: int = Field(ge=0)
    nextCursor: Optional[str] = None


class BookingCollection(BaseModel):
    """`#/$defs/BookingCollection` — a page of bookings."""

    model_config = ConfigDict(extra="forbid")

    items: list[Booking]
    page: PageMeta


class Problem(BaseModel):
    """`#/$defs/Problem` — RFC 9457 Problem Details (application/problem+json)."""

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: Optional[str] = None
    instance: Optional[str] = None


class OperationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Operation(BaseModel):
    """`#/$defs/Operation` — a long-running server operation record. Ch11
    reuses this exact shape (not a bespoke "JobRun" type) for a
    manifest-reconcile RUN: `id` uses the SAME `op_...` prefix as a Ch10
    operation (the schema's id pattern is `^op_[0-9A-HJKMNP-TV-Z]{26}$`,
    regardless of which protocol minted it), `resource` stays
    None (a reconcile run doesn't create/affect one addressable resource the
    way a Ch10 confirmation does), and `error` carries a Problem on FAILED.
    Responses are always serialized with `exclude_none=True` so
    `completedAt`/`resource`/`error` are omitted rather than emitted as a
    JSON `null` the schema doesn't declare.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    status: OperationStatus
    createdAt: str
    completedAt: Optional[str] = None
    resource: Optional[str] = None
    error: Optional[Problem] = None


class JobDefinition(BaseModel):
    """The server-owned schedule/definition half of Ch11's rerunnable-jobs
    protocol — NOT part of the shared shipping.schema.json contract (no
    shipping-domain meaning), so it's a small local shape documented in
    README.md instead of `#/$defs/...`. A client configures `enabled` /
    `intervalSeconds`; it never drives an individual execution — that's the
    separate `Operation`-shaped run record.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    enabled: bool
    intervalSeconds: int
    createdAt: str
    updatedAt: str
