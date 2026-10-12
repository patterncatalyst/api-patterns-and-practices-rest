"""Builds the `_links` map for a Booking, driven by the booking lifecycle
finite-state machine (see _plans/domain-glossary.md):

    PENDING --confirm--> CONFIRMED --load--> IN_TRANSIT --deliver--> DELIVERED
       |                     |
       +------cancel---------+--------------> CANCELLED

The response IS the state machine: a client follows `_links` rather than
hard-coding which transitions are legal from which status. Every state
exposes `self`; PENDING additionally exposes `confirm` + `cancel`; CONFIRMED
exposes only `cancel`; IN_TRANSIT, DELIVERED and CANCELLED are
terminal-for-the-client and expose nothing but `self`. Mirrors
../quarkus/.../HateoasLinks.java relation-for-relation.
"""
from __future__ import annotations

from app.models import BookingStatus, Link


def links_for_booking(booking_id: str, status: BookingStatus) -> dict[str, Link]:
    links: dict[str, Link] = {
        "self": Link(href=f"/bookings/{booking_id}", method="GET", title="Get this booking"),
    }

    if status == BookingStatus.PENDING:
        links["confirm"] = Link(
            href=f"/bookings/{booking_id}/confirmation", method="POST", title="Confirm this booking"
        )
        links["cancel"] = Link(href=f"/bookings/{booking_id}", method="DELETE", title="Cancel this booking")
    elif status == BookingStatus.CONFIRMED:
        links["cancel"] = Link(href=f"/bookings/{booking_id}", method="DELETE", title="Cancel this booking")
    # IN_TRANSIT, DELIVERED, CANCELLED: self only — no further
    # client-driven transition from here.

    return links
