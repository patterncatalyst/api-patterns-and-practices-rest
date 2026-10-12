package com.patterncatalyst.shipping.model;

/**
 * The server-owned schedule/definition half of Ch11's rerunnable-jobs
 * protocol — NOT part of the shared shipping.schema.json contract (it has
 * no shipping-domain meaning), so it's a small local shape documented in
 * README.md instead of `#/$defs/...`.
 *
 * <p>A client PUTs {@code enabled}/{@code intervalSeconds} to configure
 * *when* the job should run; it never drives an individual execution —
 * that's the separate {@link Operation}-shaped run record returned by
 * {@code POST /jobs/manifest-reconcile/runs} and listed at
 * {@code GET /jobs/manifest-reconcile/runs}. This is the chapter's point:
 * configuring the schedule and executing a run are two different resources
 * with two different owners (client configures; server — or an explicit
 * "run now" — executes).
 */
public record JobDefinition(
        String id,
        boolean enabled,
        int intervalSeconds,
        String createdAt,
        String updatedAt) {
}
