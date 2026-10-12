package com.patterncatalyst.shipping.model;

/** `#/$defs/PageMeta` — keyset-pagination metadata (Ch8). `nextCursor` is
 * null on the last page. */
public record PageMeta(int limit, int count, String nextCursor) {
}
