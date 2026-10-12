package com.patterncatalyst.shipping.model;

import java.util.List;

/** `#/$defs/BookingRequest` — client payload to create a booking. */
public record BookingRequest(
        Location origin,
        Location destination,
        List<CargoRequest> cargo,
        String requestedPickup) {
}
