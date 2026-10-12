package com.patterncatalyst.shipping.model;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;

/** `#/$defs/BookingRequest` — client payload to create/replace a booking. */
public record BookingRequest(
        @NotNull @Valid Location origin,
        @NotNull @Valid Location destination,
        @NotEmpty @Valid List<CargoRequest> cargo,
        String requestedPickup) {
}
