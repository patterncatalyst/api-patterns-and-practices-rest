package com.patterncatalyst.shipping.model;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;

/** `#/$defs/BookingRequest` — client payload to create/replace a booking.
 *
 * Constraints mirror the Python side's pydantic {@code Field(...)}
 * declarations for the same fields (see python/app/models.py): both
 * {@code origin}/{@code destination} are required, and {@code cargo} needs
 * at least one item. {@code @Valid} cascades validation into each nested
 * {@link Location}/{@link CargoRequest}. */
public record BookingRequest(
        @NotNull @Valid Location origin,
        @NotNull @Valid Location destination,
        @NotEmpty @Valid List<CargoRequest> cargo,
        String requestedPickup) {
}
