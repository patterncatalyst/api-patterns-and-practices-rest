package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/Money` — amount is a DECIMAL STRING (e.g. "1250.00"), never a
 * JSON number, to avoid binary-float drift. Ch16's Booking.quote is always
 * null (no quoting in this chapter); the type stays schema-accurate in case
 * a future pass wires quoting back in.
 */
public record Money(String currency, String amount) {
}
