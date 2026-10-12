"""Builds `_links` maps, driven by the booking lifecycle finite-state
machine (Ch12):

    PENDING --confirm--> CONFIRMED --...--> IN_TRANSIT --...--> DELIVERED
       |                     |
       +------cancel---------+

The response IS the state machine: a client follows `_links` rather than
hard-coding which transitions are legal from which status. Every state
exposes `self`; PENDING additionally exposes `confirm` (the Ch10 async
202/poll/303 endpoint) + `cancel`; CONFIRMED exposes only `cancel`;
IN_TRANSIT, DELIVERED and CANCELLED are terminal-for-the-client and expose
nothing but `self`. Mirrors ../quarkus/.../HateoasLinks.java relation-for-
relation.
"""
from __future__ import annotations

from app.models import BookingStatus, Link


def links_for_booking(booking_id: str, status: BookingStatus) -> dict[str, Link]:
    links: dict[str, Link] = {
        "self": Link(href=f"/bookings/{booking_id}", method="GET", title="Get this booking"),
    }

    if status == BookingStatus.PENDING:
        links["confirm"] = Link(
            href=f"/bookings/{booking_id}/confirmation", method="POST", title="Start asynchronous confirmation"
        )
        links["cancel"] = Link(href=f"/bookings/{booking_id}", method="DELETE", title="Cancel this booking")
    elif status == BookingStatus.CONFIRMED:
        links["cancel"] = Link(href=f"/bookings/{booking_id}", method="DELETE", title="Cancel this booking")
    # IN_TRANSIT, DELIVERED, CANCELLED: self only — no further
    # client-driven transition from here.

    return links


def links_for_collection(limit: int, next_cursor: str | None) -> dict[str, Link]:
    """Collection-level links: `self` always, `next` only when another page exists."""
    links: dict[str, Link] = {
        "self": Link(href=f"/bookings?limit={limit}", method="GET", title="This page"),
    }
    if next_cursor is not None:
        links["next"] = Link(
            href=f"/bookings?limit={limit}&cursor={next_cursor}", method="GET", title="Next page"
        )
    return links
