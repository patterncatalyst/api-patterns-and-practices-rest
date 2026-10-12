package com.patterncatalyst.shipping.model;

import java.util.List;

/**
 * `#/$defs/Booking` — the aggregate root. `_links` is intentionally never
 * populated (HATEOAS is Ch12's concern, not this chapter's); Jackson's
 * non-null inclusion setting (see application.properties) drops
 * `quote`/`requestedPickup`/`updatedAt` when null rather than emitting a
 * JSON `null` the schema doesn't declare.
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
