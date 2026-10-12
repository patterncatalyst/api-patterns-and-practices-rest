package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingV1;
import com.patterncatalyst.shipping.model.Cargo;

import java.util.stream.Collectors;

/**
 * Projects the ONE stored booking (always kept in the current v2 shape, per
 * {@code BookingStore}) into the frozen v1 representation. There is no
 * separate v1 store or v1 write path — v1 is a read-only VIEW derived from
 * v2 state, which is exactly the point this example teaches: versioning is
 * about the representation a client gets back, not about forking the
 * underlying resource.
 */
public final class VersionMapper {

    /** Vendor media type for the v1 (frozen) booking representation. */
    public static final String MEDIA_TYPE_V1 = "application/vnd.shipping.v1+json";

    /** Vendor media type for the v2 (current) booking representation. */
    public static final String MEDIA_TYPE_V2 = "application/vnd.shipping.v2+json";

    private VersionMapper() {
    }

    /**
     * v1's single {@code cargoDescription} string from v2's {@code cargo[]}
     * array — joining each item's description is a lossy, one-way
     * projection (v1 has no way to recover individual cargo items, weights,
     * or hazardous flags from this string alone). That's the real cost of
     * carrying an old representation: it can only describe what its shape
     * had room for.
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
     * Picks v1 or v2 from the {@code Accept} header for the UNVERSIONED
     * {@code /bookings/{id}} endpoint (media-type/content-negotiation
     * versioning). Defaults to v2 for anything else — a missing header, a
     * bare {@code application/json}, {@code *}/{@code *}, or the explicit
     * v2 vendor type — so "no opinion" and "current version" behave the
     * same way.
     */
    public static boolean wantsV1(String acceptHeader) {
        return acceptHeader != null && acceptHeader.contains("vnd.shipping.v1+json");
    }
}
