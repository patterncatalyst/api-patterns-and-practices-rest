package com.patterncatalyst.shipping.model;

/** `#/$defs/CargoRequest` — client payload to add cargo (no server id). */
public record CargoRequest(String description, CargoType type, Dimensions dimensions, Boolean hazardous) {

    public boolean hazardousOrDefault() {
        return hazardous != null && hazardous;
    }
}
