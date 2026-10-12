package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/BookingEvent` — a domain-event payload describing a booking
 * state change. Used both as the CloudEvents `data` published to Kafka
 * (Ch21) and as the record shape streamed by the NDJSON manifest export
 * (Ch16).
 */
public record BookingEvent(
        String bookingId,
        BookingStatus status,
        BookingStatus previousStatus,
        Location origin,
        Location destination,
        String occurredAt) {
}
