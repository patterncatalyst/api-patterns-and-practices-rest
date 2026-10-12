package com.patterncatalyst.shipping.model;

/**
 * The FROZEN v1 representation negotiated via
 * {@code Accept: application/vnd.shipping.booking.v1+json} (Ch14
 * media-type versioning). Two shape differences from the current
 * `#/$defs/Booking` (v2) make v1 -&gt; v2 a breaking (major) change:
 *
 * <ul>
 *   <li>{@code price} (here) vs. {@code quote} (v2) — same {@link Money}
 *       value, renamed field.</li>
 *   <li>{@code cargoDescription}, a single string (here) vs. {@code cargo},
 *       an array of {@link Cargo} items (v2).</li>
 * </ul>
 *
 * No {@code _links} (HATEOAS postdates v1) and no {@code updatedAt}. Never
 * constructed from client input — always projected from the one stored
 * (v2-shaped) {@link Booking} via {@code VersionMapper.toV1}. NOT in the
 * shared contract schema (shipping.schema.json has no BookingV1 def) — a
 * frozen prior representation lives outside the current contract by
 * definition; verify.sh checks its shape by hand.
 */
public record BookingV1(
        String id,
        BookingStatus status,
        Location origin,
        Location destination,
        String cargoDescription,
        Money price,
        String createdAt) {
}
