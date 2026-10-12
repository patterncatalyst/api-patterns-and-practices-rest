package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/BookingEvent` — a single cargo-status event, as streamed by
 * {@link com.patterncatalyst.shipping.RestDepthResource}'s NDJSON export.
 * Reused unchanged from the shared contract (the same type Ch16's
 * streaming deep-dive emits) rather than inventing a chapter-local event
 * shape. `origin`/`destination` are never populated here; Jackson's
 * non-null inclusion setting (see application.properties) drops them from
 * the JSON output.
 */
public record BookingEvent(
        String bookingId,
        BookingStatus status,
        BookingStatus previousStatus,
        Location origin,
        Location destination,
        String occurredAt) {
}
