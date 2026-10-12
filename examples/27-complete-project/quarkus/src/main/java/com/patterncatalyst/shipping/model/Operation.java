package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/Operation` — a long-running server operation record (202
 * Accepted -&gt; poll -&gt; 303, Ch10).
 */
public record Operation(
        String id,
        OperationStatus status,
        String createdAt,
        String completedAt,
        String resource,
        Problem error) {
}
