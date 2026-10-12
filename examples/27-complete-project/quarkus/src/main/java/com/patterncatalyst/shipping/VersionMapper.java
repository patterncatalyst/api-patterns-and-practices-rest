package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingV1;
import com.patterncatalyst.shipping.model.Cargo;

import java.util.stream.Collectors;

/**
 * Ch14 media-type versioning: projects the ONE stored booking (always kept
 * in the current v2 shape) into the frozen v1 representation. There is no
 * separate v1 store or write path — v1 is a read-only VIEW derived from v2
 * state, negotiated via the {@code Accept} header on the unversioned
 * {@code GET /bookings/{id}}.
 */
public final class VersionMapper {

    /** Vendor media type for the v1 (frozen) booking representation. */
    public static final String MEDIA_TYPE_V1 = "application/vnd.shipping.booking.v1+json";

    /** Vendor media type for the v2 (current) booking representation. */
    public static final String MEDIA_TYPE_V2 = "application/vnd.shipping.booking.v2+json";

    private VersionMapper() {
    }

    /**
     * v1's single {@code cargoDescription} string from v2's {@code cargo[]}
     * array — a lossy, one-way projection (v1 has no way to recover
     * individual cargo items, weights, or hazardous flags from this string
     * alone).
     */
    public static BookingV1 toV1(Booking booking) {
        String cargoDescription = booking.cargo().stream()
                .map(Cargo::description)
                .collect(Collectors.joining("; "));
        return new BookingV1(
                booking.id(),
                booking.status(),
                booking.origin(),
                booking.destination(),
                cargoDescription,
                booking.quote(),
                booking.createdAt());
    }

    /**
     * True iff the Accept header explicitly asks for the v1 vendor type.
     * Anything else — the v2 vendor type, a bare application/json, a
     * missing header, or {@code *}/{@code *} — means "give me the current
     * representation", same as if no version had been requested at all.
     */
    public static boolean wantsV1(String acceptHeader) {
        return acceptHeader != null && acceptHeader.contains(MEDIA_TYPE_V1);
    }
}
