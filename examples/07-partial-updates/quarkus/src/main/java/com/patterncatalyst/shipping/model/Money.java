package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/Money` — amount is a DECIMAL STRING (e.g. "1250.00"), never a
 * JSON number, to avoid binary-float drift. See QuoteCalculator.
 */
public record Money(String currency, String amount) {
}
