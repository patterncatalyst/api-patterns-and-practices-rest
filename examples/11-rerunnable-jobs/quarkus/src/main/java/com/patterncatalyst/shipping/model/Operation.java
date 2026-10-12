package com.patterncatalyst.shipping.model;

/**
 * `#/$defs/Operation` — a long-running server operation record. Ch11 reuses
 * this exact shape (not a bespoke "JobRun" type) for a manifest-reconcile
 * RUN: {@code id} uses the SAME {@code op_...} prefix as a Ch10 operation
 * (the schema's id pattern is {@code ^op_[0-9A-HJKMNP-TV-Z]{26}$},
 * regardless of which protocol minted it), {@code resource} is left null
 * (a reconcile run doesn't create/affect a single addressable resource the
 * way a Ch10 confirmation does), and {@code error} carries a Problem on
 * FAILED. `_links` is intentionally never populated (HATEOAS lands in
 * Ch12); Jackson's non-null inclusion setting (see application.properties)
 * drops `completedAt`/`resource`/`error` when null rather than emitting a
 * JSON `null` the schema doesn't declare.
 */
public record Operation(
        String id,
        OperationStatus status,
        String createdAt,
        String completedAt,
        String resource,
        Problem error) {
}
