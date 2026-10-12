package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.BookingEvent;
import com.patterncatalyst.shipping.model.BookingStatus;

import java.time.Instant;

/**
 * Deterministic cargo-status event sequence streamed by
 * {@link RestDepthResource#exportEvents}. A fixed {@link BookingStatus}
 * progression stands in for the kind of state-transition feed a real
 * tracking system would publish; only {@code occurredAt} varies between
 * calls (wall-clock time of emission) — what matters for this chapter is
 * event SHAPE and the fact that the `limit` query parameter genuinely
 * drives HOW MANY of them come back, not byte-for-byte determinism.
 */
public final class EventGenerator {

    /** `limit` used when the query parameter is omitted entirely. */
    public static final int DEFAULT_LIMIT = 5;

    /** DoS guard: `limit` above this is CLAMPED, never honored unbounded —
     * an unbounded limit lets a client force the server to hold a
     * long-lived stream open indefinitely. */
    public static final int MAX_LIMIT = 20;

    /** Delay between successive streamed items — long enough that a genuine
     * per-item flush is trivially distinguishable from a buffered write. */
    public static final long STREAM_INTERVAL_MILLIS = 200;

    /**
     * A schema-valid (but never-issued) booking id — all 26 Crockford-Base32
     * zero chars — since this focused example streams events without a
     * booking-creation endpoint. '0' is a legal Crockford Base32 digit, so
     * this satisfies BookingEvent.bookingId's `^bkg_[0-9A-HJKMNP-TV-Z]{26}$`
     * pattern without pretending to be a real booking.
     */
    public static final String SAMPLE_BOOKING_ID = "bkg_" + "0".repeat(26);

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

    /** Clamp a requested `limit` into `[1, MAX_LIMIT]` — never 0, never unbounded. */
    public static int clampLimit(int requested) {
        if (requested < 1) {
            return 1;
        }
        return Math.min(requested, MAX_LIMIT);
    }
}
