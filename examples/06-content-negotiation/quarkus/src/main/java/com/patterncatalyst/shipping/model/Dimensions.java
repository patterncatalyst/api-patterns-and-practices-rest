package com.patterncatalyst.shipping.model;

import jakarta.validation.constraints.Positive;

/** `#/$defs/Dimensions` — physical measure of a cargo item.
 *
 * Constraints mirror the Python side's pydantic {@code Field(gt=0)}
 * declarations for the same fields (see python/app/models.py): a missing
 * {@code weightKg} deserializes to the primitive default {@code 0}, which
 * {@code @Positive} rejects the same as an explicit non-positive value. */
public record Dimensions(@Positive double weightKg, @Positive Double volumeM3) {
}
