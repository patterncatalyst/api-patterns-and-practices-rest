package com.patterncatalyst.shipping.model;

/** `#/$defs/PageMeta` — keyset-pagination metadata (full paging: Ch8). */
public record PageMeta(int limit, int count, String nextCursor) {
}
