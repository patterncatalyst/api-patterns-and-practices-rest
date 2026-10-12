package com.patterncatalyst.shipping.model;

import java.util.List;

/**
 * `#/$defs/Booking` — the aggregate root. Ch15 is deliberately thin here:
 * `quote`/`_links`/`updatedAt` are never populated (no quoting or HATEOAS
 * in this chapter — see Ch4/Ch12 for those). Jackson's non-null inclusion
 * setting (see application.properties) drops them from the JSON output
 * rather than emitting a `null` the shared schema doesn't declare.
 */
public record Booking(
        String id,
        BookingStatus status,
        Location origin,
        Location destination,
        List<Cargo> cargo,
        Money quote,
        String requestedPickup,
        String createdAt,
        String updatedAt) {
}
