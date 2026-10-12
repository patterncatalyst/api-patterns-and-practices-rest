package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.BookingEvent;
import com.patterncatalyst.shipping.model.BookingStatus;

import java.time.Instant;

/**
 * Deterministic cargo-status event sequence streamed by the Ch16-style
 * NDJSON manifest export (Ch27's `GET /bookings/{id}/manifest/export`). A
 * fixed {@link BookingStatus} progression stands in for the kind of
 * state-transition feed a real tracking system would publish; only
 * {@code occurredAt} varies between calls.
 */
final class ManifestEventGenerator {

    /** Number of lines the manifest export emits per request. */
    static final int LINE_COUNT = 6;

    /** Delay between successive lines — keeps a full export under ~1.5s. */
    static final long INTERVAL_MILLIS = 250;

    private static final BookingStatus[] SEQUENCE = {
            BookingStatus.PENDING,
            BookingStatus.CONFIRMED,
            BookingStatus.CONFIRMED,
            BookingStatus.IN_TRANSIT,
            BookingStatus.IN_TRANSIT,
            BookingStatus.DELIVERED
    };

    private ManifestEventGenerator() {
    }

    /** The {@code index}-th event (0-based) for {@code bookingId}, cycling through SEQUENCE. */
    static BookingEvent eventFor(String bookingId, int index) {
        BookingStatus status = SEQUENCE[index % SEQUENCE.length];
        BookingStatus previous = index == 0 ? null : SEQUENCE[(index - 1) % SEQUENCE.length];
        return new BookingEvent(bookingId, status, previous, null, null, Instant.now().toString());
    }
}
