package com.patterncatalyst.shipping.model;

/**
 * `BookingV1` from {@code contracts/openapi/shipping-api-v1.yaml} — the
 * FROZEN previous major version of the booking representation. Two shape
 * differences from the current `#/$defs/Booking` (v2) make v1 -> v2 a
 * breaking (major) change:
 *
 * <ul>
 *   <li>{@code price} (here) vs. {@code quote} (v2) — same {@link Money}
 *       value, renamed field.</li>
 *   <li>{@code cargoDescription}, a single string (here) vs. {@code cargo},
 *       an array of {@link Cargo} items (v2).</li>
 * </ul>
 *
 * There is no {@code updatedAt} or {@code requestedPickup} in v1 — those
 * fields simply didn't exist yet. Never constructed directly from client
 * input in this example; always projected from the one stored (v2-shaped)
 * {@link Booking} via {@code VersionMapper.toV1}.
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
