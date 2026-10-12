package com.patterncatalyst.shipping.model;

/** `#/$defs/Location` — a port or terminal identified by UN/LOCODE. */
public record Location(String unLocode, String name, String country) {
}
