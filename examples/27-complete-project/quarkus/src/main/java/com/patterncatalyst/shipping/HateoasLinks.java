package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.Link;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Builds the `_links` map for a Booking, driven by the booking lifecycle
 * finite-state machine (Ch12):
 *
 *   PENDING ──confirm──▶ CONFIRMED ──...──▶ IN_TRANSIT ──...──▶ DELIVERED
 *      │                     │
 *      └──────cancel─────────┘
 *
 * The response IS the state machine: a client follows `_links` rather than
 * hard-coding which transitions are legal from which status. Every state
 * exposes `self`; PENDING additionally exposes `confirm` (the Ch10 async
 * 202/poll/303 endpoint) + `cancel`; CONFIRMED exposes only `cancel`;
 * IN_TRANSIT, DELIVERED and CANCELLED are terminal-for-the-client and
 * expose nothing but `self`.
 */
final class HateoasLinks {

    private HateoasLinks() {
    }

    static Map<String, Link> forBooking(String id, BookingStatus status) {
        Map<String, Link> links = new LinkedHashMap<>();
        links.put("self", new Link("/bookings/" + id, "GET", "Get this booking"));

        switch (status) {
            case PENDING -> {
                links.put("confirm", new Link("/bookings/" + id + "/confirmation", "POST", "Start asynchronous confirmation"));
                links.put("cancel", new Link("/bookings/" + id, "DELETE", "Cancel this booking"));
            }
            case CONFIRMED -> links.put("cancel", new Link("/bookings/" + id, "DELETE", "Cancel this booking"));
            case IN_TRANSIT, DELIVERED, CANCELLED -> {
                // self only — no further client-driven transition from here.
            }
        }
        return links;
    }

    /** Collection-level links: `self` always, `next` only when another page exists. */
    static Map<String, Link> forCollection(int limit, String nextCursor) {
        Map<String, Link> links = new LinkedHashMap<>();
        links.put("self", new Link("/bookings?limit=" + limit, "GET", "This page"));
        if (nextCursor != null) {
            links.put("next", new Link("/bookings?limit=" + limit + "&cursor=" + nextCursor, "GET", "Next page"));
        }
        return links;
    }
}
