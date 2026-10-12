package com.patterncatalyst.shipping.model;

import java.util.List;

/** `#/$defs/BookingCollection` — a page of bookings. */
public record BookingCollection(List<Booking> items, PageMeta page) {
}
