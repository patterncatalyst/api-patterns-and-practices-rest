---
title: "r03 Execution Plan (Phase 4)"
layout: plan
render_with_liquid: false
---

# r03 Execution Plan — Phase 4 content (Ch10–Ch14)

Relay on branch `docs/r03-content`, mirroring `_plans/r02-execution-plan.md`.
Standing approval: run batches without gating. Verification unchanged: both
stacks live in containers, `verify.sh` schema-validates live responses against
`contracts/schemas/`. All five chapters are hands-on → five new both-stack examples.

## Scope (from `_plans/iteration-plan.md`)
- **Part 5 — Asynchronous work & jobs:** Ch10 async/long-running operations (202 + Location,
  status polling, 303 on completion, cancel link) [H]; Ch11 rerunnable jobs (server-owned schedules,
  configure-vs-execute split; JobRunr / FastAPI background) [H].
- **Part 6 — Evolution & lifecycle:** Ch12 HATEOAS (state-dependent links, response as FSM, self links) [H];
  Ch13 soft deletion & GDPR purge (audit, referential integrity, hidden-from-queries, purge job) [H];
  Ch14 versioning (URI / query / header / media-type + caching) [H].

## Examples (extend the Ch4 anchor; UNIQUE host ports)
- `examples/10-async-operations` — 8090/8010, project `ch10-async`. `POST /bookings/{id}/confirmation`
  → 202 + Location(operation); `GET /operations/{id}` → 200 (running) then 303 (done) → confirmed booking;
  cancel link. Uses the `Operation` type already in the contract. verify: 202→poll→303 sequence + cancel.
- `examples/11-rerunnable-jobs` — 8091/8011, project `ch11-jobs`. A server-owned scheduled
  manifest-reconcile job; configure (create/enable schedule) vs execute (run now) split. Quarkus
  Quartz/scheduler (or JobRunr); FastAPI APScheduler/BackgroundTasks. verify: configure a job, trigger a
  run, assert the run record/state; keep schedule intervals short + deterministic for CI.
- `examples/12-hateoas` — 8092/8012, project `ch12-hateoas`. State-dependent `_links` on `Booking`
  (already in schema): PENDING offers confirm+cancel, DELIVERED offers neither; self link always.
  verify: assert the link set matches the booking's state (the FSM).
- `examples/13-soft-delete-purge` — 8093/8013, project `ch13-purge`. Soft-delete (CANCELLED, hidden from
  default queries) + an audit trail + a purge operation that hard-deletes under a compliance rule.
  verify: delete→hidden-from-list→still-addressable-for-audit→purge→404.
- `examples/14-versioning` — 8094/8014, project `ch14-version`. URI (`/v1` vs `/v2`) AND media-type
  (`application/vnd.shipping.v1+json`) versioning; v1 = the frozen shape in
  `contracts/openapi/shipping-api-v1.yaml` (price+cargoDescription), v2 = current. verify: same booking
  served in both shapes; correct Vary/Content-Type.

## Figures (paired svg+excalidraw; specs in scripts/diagrams/)
`10-async-lifecycle` (202→poll→303) · `11-job-lifecycle` · `12-hateoas-state-machine` ·
`13-soft-delete-purge` · `14-versioning-strategies`.

## Parts
`_parts/05-async-work-and-jobs.md` (order 5), `_parts/06-evolution-and-lifecycle.md` (order 6).

## Batches
1. **A (parallel):** two Part pages; five figures.
2. **B (sequential example builds):** Ch10 → Ch11 → Ch12 → Ch13 → Ch14, each green before next;
   launch each chapter's prose after its example lands (prose overlaps the next build).
3. **D (validation):** Opus adversarial pass on the five chapters.
4. **E (wrap):** flip coverage rows (Ch10–14 verified after CI green); full local gate; push; watch CI;
   flip verified; open PR + merge.

## Acceptance (same bar as r01/r02)
2,000–2,500 words/chapter + ≥1 diagram; 0 voice ban-tier; validate.py + wordcount GATE + jekyll build
green; each example both-stack `verify.sh` green in CI; coverage rows truthful. **Push branch with `-u`
immediately (r02 durability lesson).**
