package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.Link;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Builds the `_links` map for a Booking, driven by the booking lifecycle
 * finite-state machine (see _plans/domain-glossary.md):
 *
 *   PENDING ──confirm──▶ CONFIRMED ──load──▶ IN_TRANSIT ──deliver──▶ DELIVERED
 *      │                     │
 *      └──────cancel─────────┴──────────────▶ CANCELLED
 *
 * The response IS the state machine: a client follows `_links` rather than
 * hard-coding which transitions are legal from which status. Every state
 * exposes `self`; PENDING additionally exposes `confirm` + `cancel`;
 * CONFIRMED exposes only `cancel`; IN_TRANSIT, DELIVERED and CANCELLED are
 * terminal-for-the-client and expose nothing but `self`.
 */
final class HateoasLinks {

    private HateoasLinks() {
    }

    static Map<String, Link> forBooking(String id, BookingStatus status) {
        Map<String, Link> links = new LinkedHashMap<>();
        links.put("self", new Link("/bookings/" + id, "GET", "Get this booking"));

        switch (status) {
            case PENDING -> {
                links.put("confirm", new Link("/bookings/" + id + "/confirmation", "POST", "Confirm this booking"));
                links.put("cancel", new Link("/bookings/" + id, "DELETE", "Cancel this booking"));
            }
            case CONFIRMED -> links.put("cancel", new Link("/bookings/" + id, "DELETE", "Cancel this booking"));
            case IN_TRANSIT, DELIVERED, CANCELLED -> {
                // self only — no further client-driven transition from here.
            }
        }
        return links;
    }
}
