"""Pydantic mirrors of contracts/schemas/shipping.schema.json's $defs, scoped
to what Ch21 needs: Booking/Cargo create + the BookingEvent published to
Kafka. Field names, requiredness, patterns and `extra="forbid"` intentionally
match the shared schema so a shape drift here surfaces as a pydantic
validation error on the way in, and as a validate_response.py failure on the
way out (see ../../_lib/validate_response.py). Mirrors
examples/04-contract-first/python/app/models.py.
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
    """`#/$defs/BookingRequest` — client payload to create a booking."""

    model_config = ConfigDict(extra="forbid")

    origin: Location
    destination: Location
    cargo: list[CargoRequest] = Field(min_length=1)
    requestedPickup: Optional[date] = None


class Booking(BaseModel):
    """`#/$defs/Booking` — the aggregate root.

    `_links` is intentionally never populated; responses are always
    serialized with `exclude_none=True` so optional fields (`quote`,
    `requestedPickup`, `updatedAt`) are omitted rather than emitted as a JSON
    `null` the schema doesn't declare.
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


class Problem(BaseModel):
    """`#/$defs/Problem` — RFC 9457 Problem Details (application/problem+json)."""

    model_config = ConfigDict(extra="allow")

    type: str = "about:blank"
    title: str
    status: int
    detail: Optional[str] = None
    instance: Optional[str] = None


class BookingEvent(BaseModel):
    """`#/$defs/BookingEvent` — the CloudEvents `data` payload published to
    `shipping.bookings.lifecycle` on a booking state change."""

    model_config = ConfigDict(extra="forbid")

    bookingId: str
    status: BookingStatus
    previousStatus: Optional[BookingStatus] = None
    origin: Optional[Location] = None
    destination: Optional[Location] = None
    occurredAt: str
