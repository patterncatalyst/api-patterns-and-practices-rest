package com.patterncatalyst.shipping.model;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/** `#/$defs/Location` — a port or terminal identified by UN/LOCODE. */
public record Location(
        @NotNull @Pattern(regexp = "^[A-Z]{2}[A-Z0-9]{3}$") String unLocode,
        String name,
        @Pattern(regexp = "^[A-Z]{2}$") String country) {
}
