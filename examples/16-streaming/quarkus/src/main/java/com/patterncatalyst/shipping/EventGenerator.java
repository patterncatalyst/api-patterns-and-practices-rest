package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.BookingEvent;
import com.patterncatalyst.shipping.model.BookingStatus;

import java.time.Instant;

/**
 * Deterministic cargo-status event sequence — the small payload this
 * chapter streams in all three modes (SSE, NDJSON, chunked). A fixed
 * {@link BookingStatus} progression stands in for the kind of
 * state-transition feed a real tracking system would publish; only
 * {@code occurredAt} varies between calls (wall-clock time of emission),
 * matching the spirit of the deterministic generators in Ch15's
 * ManifestGenerator without needing exact byte-for-byte reproducibility —
 * what matters here is event SHAPE and DELIVERY TIMING, not a frozen
 * clock.
 */
public final class EventGenerator {

    /** Number of events a single SSE stream or export run emits. */
    public static final int SSE_EVENT_COUNT = 5;

    /** Delay between successive SSE ticks — keeps a full stream under ~1.5s. */
    public static final long SSE_INTERVAL_MILLIS = 250;

    /** Row count for the NDJSON export endpoint. */
    public static final int EXPORT_EVENT_COUNT = 10;

    /** Line count for the dedicated chunked-transfer demo endpoint. */
    public static final int CHUNKED_LINE_COUNT = 500;

    /**
     * A schema-valid (but never-issued) booking id — all 26 Crockford-Base32
     * zero chars — used by the NDJSON export, which isn't scoped to a real
     * booking the caller created. '0' is a legal Crockford Base32 digit, so
     * this satisfies BookingEvent.bookingId's `^bkg_[0-9A-HJKMNP-TV-Z]{26}$`
     * pattern without pretending to be a real booking.
     */
    public static final String EXPORT_SAMPLE_BOOKING_ID = "bkg_" + "0".repeat(26);

    private static final BookingStatus[] SEQUENCE = {
            BookingStatus.CONFIRMED,
            BookingStatus.IN_TRANSIT,
            BookingStatus.IN_TRANSIT,
            BookingStatus.IN_TRANSIT,
            BookingStatus.DELIVERED
    };

    private EventGenerator() {
    }

    /** The {@code index}-th event (0-based) for {@code bookingId}, cycling through SEQUENCE. */
    public static BookingEvent eventFor(String bookingId, int index) {
        BookingStatus status = SEQUENCE[index % SEQUENCE.length];
        BookingStatus previous = index == 0 ? BookingStatus.PENDING : SEQUENCE[(index - 1) % SEQUENCE.length];
        return new BookingEvent(bookingId, status, previous, null, null, Instant.now().toString());
    }
}
