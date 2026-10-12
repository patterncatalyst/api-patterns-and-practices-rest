package com.patterncatalyst.shipping.model;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** `#/$defs/CargoRequest` — client payload to add cargo (no server id).
 *
 * Constraints mirror the Python side's pydantic {@code Field(...)}
 * declarations for the same fields (see python/app/models.py). */
public record CargoRequest(
        @NotNull @Size(max = 280) String description,
        @NotNull CargoType type,
        @NotNull @Valid Dimensions dimensions,
        Boolean hazardous) {

    public boolean hazardousOrDefault() {
        return hazardous != null && hazardous;
    }
}
