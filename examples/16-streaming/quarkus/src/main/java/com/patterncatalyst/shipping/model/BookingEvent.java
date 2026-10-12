package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/BookingEvent` — a single cargo-status event, as streamed by
 * StreamingResource's SSE/NDJSON/chunked endpoints. The shared schema
 * documents this as "the CloudEvents `data`; AsyncAPI channel message" —
 * Ch16 reuses it as the wire shape for all three streaming modes rather
 * than inventing a chapter-local event type, so the same schema that
 * backs Ch4's synchronous Booking model also backs this chapter's
 * streamed events. `origin`/`destination` are never populated here (Ch16
 * keeps the payload small per event, per the chapter's focus on delivery
 * *mechanics* over event content); Jackson's non-null inclusion setting
 * (see application.properties) drops them from the JSON output.
 */
public record BookingEvent(
        String bookingId,
        BookingStatus status,
        BookingStatus previousStatus,
        Location origin,
        Location destination,
        String occurredAt) {
}
