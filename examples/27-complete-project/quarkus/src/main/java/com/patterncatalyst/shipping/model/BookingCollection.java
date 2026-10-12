package com.patterncatalyst.shipping.model;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/** `#/$defs/BookingCollection` — a page of bookings with keyset pagination
 * and collection-level HATEOAS links (`self`, and `next` when another page
 * exists). */
public record BookingCollection(
        List<Booking> items,
        PageMeta page,
        @JsonProperty("_links") Map<String, Link> links) {
}
