package com.patterncatalyst.shipping.model;

/** `#/$defs/Cargo` — one cargo item carried under a booking. */
public record Cargo(String id, String description, CargoType type, Dimensions dimensions, boolean hazardous) {
}
