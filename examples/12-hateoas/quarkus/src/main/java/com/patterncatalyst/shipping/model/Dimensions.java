package com.patterncatalyst.shipping.model;

import jakarta.validation.constraints.Positive;

/** `#/$defs/Dimensions` — physical measure of a cargo item. */
public record Dimensions(@Positive double weightKg, @Positive Double volumeM3) {
}
