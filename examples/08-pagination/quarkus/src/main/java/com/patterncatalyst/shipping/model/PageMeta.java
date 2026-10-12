package com.patterncatalyst.shipping.model;

/** `#/$defs/PageMeta` — pagination metadata. `limit` is server-clamped to
 * [1, 100]; `count` is the number of items in THIS page; `nextCursor` is
 * the opaque keyset cursor for the next page, null on the last page (only
 * populated by the cursor/keyset strategy — see BookingResource). */
public record PageMeta(int limit, int count, String nextCursor) {
}
