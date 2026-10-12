package com.patterncatalyst.shipping.model;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * `#/$defs/Booking` — the aggregate root. `_links` IS populated (Ch12
 * HATEOAS): every response carries exactly the relations valid from the
 * booking's CURRENT status — see HateoasLinks. Jackson's non-null inclusion
 * setting (see application.properties) drops `quote`/`requestedPickup`/
 * `updatedAt` when null rather than emitting a JSON `null` the schema
 * doesn't declare.
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
        String updatedAt,
        @JsonProperty("_links") Map<String, Link> links) {
}
