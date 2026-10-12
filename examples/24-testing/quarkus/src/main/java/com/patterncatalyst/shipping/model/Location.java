package com.patterncatalyst.shipping.model;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/** `#/$defs/Location` — a port or terminal identified by UN/LOCODE.
 *
 * Constraints mirror the Python side's pydantic {@code Field(...)}
 * declarations for the same fields (see python/app/models.py) so both
 * stacks reject the same malformed input. */
public record Location(
        @NotNull @Pattern(regexp = "^[A-Z]{2}[A-Z0-9]{3}$") String unLocode,
        String name,
        @Pattern(regexp = "^[A-Z]{2}$") String country) {
}
