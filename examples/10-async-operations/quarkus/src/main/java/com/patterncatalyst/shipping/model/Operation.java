package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/Operation` — a long-running server operation record (202
 * Accepted -> poll -> 303, Ch10). `_links` is intentionally never populated
 * (HATEOAS lands in Ch12); Jackson's non-null inclusion setting (see
 * application.properties) drops `completedAt`/`resource`/`error` when null
 * rather than emitting a JSON `null` the schema doesn't declare.
 */
public record Operation(
        String id,
        OperationStatus status,
        String createdAt,
        String completedAt,
        String resource,
        Problem error) {
}
