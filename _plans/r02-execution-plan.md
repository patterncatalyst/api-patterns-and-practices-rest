---
title: "r02 Execution Plan (Phase 3)"
layout: plan
render_with_liquid: false
---

# r02 Execution Plan — Phase 3 content (Ch6–Ch9)

Relay on branch `docs/r02-content`, mirroring `_plans/r01-execution-plan.md`
(which is the proven pattern). Standing approval: run batches without gating.
Verification unchanged: both stacks live in containers, `verify.sh` schema-validates
live responses against `contracts/schemas/`.

## Scope (from `_plans/iteration-plan.md`)
- **Part 3 — HTTP semantics done right:** Ch6 content negotiation & status codes [H];
  Ch7 partial updates — JSON Patch (RFC 6902) vs JSON Merge Patch (RFC 7396) [H].
- **Part 4 — Collections at scale:** Ch8 filtering, projection & pagination (offset/keyset/seek) [H];
  Ch9 sub-resources — nesting trade-offs, caching, redundant-endpoint pitfalls [C + small H].

## Examples (each extends the Ch4/Ch5 booking app; UNIQUE host ports to avoid collisions)
- `examples/06-content-negotiation` — ports 8086/8006, project `ch06-neg`. Accept/Content-Type,
  406/415, 200/201/204/400/404/409, Location. verify asserts negotiation outcomes + bodies.
- `examples/07-partial-updates` — ports 8087/8007, project `ch07-patch`. JSON Patch vs Merge Patch
  on a booking; 415 on wrong patch media type. verify drives both patch types + validates.
- `examples/08-pagination` — ports 8088/8008, project `ch08-page`. offset/keyset/seek(after_id),
  field projection, limit cap as DoS guard. verify asserts keyset nextCursor correctness + limit cap.
- Ch9 is **concept + small H**: reuse the Ch8 example to illustrate sub-resource nesting; no new
  docker example (prose + small snippets).

## Figures (paired svg+excalidraw via scripts/generate_diagram.py; specs in scripts/diagrams/)
`06-content-negotiation` · `07-patch-vs-merge` · `08-pagination-strategies` · `09-sub-resources`.

## Batches
1. **A (parallel):** `_parts/03-http-semantics.md` + `_parts/04-collections-at-scale.md`; four figures.
2. **B (sequential example builds, to avoid docker resource thrash):** Ch6 → Ch7 → Ch8 example,
   each green before the next; launch each chapter's prose after its example lands.
3. **C (parallel prose):** Ch6/Ch7/Ch8/Ch9 chapters (2,000–2,500 words, codetabs, figure, Decision callout).
4. **D (validation):** Opus adversarial pass on the four chapters (accuracy/voice/domain).
5. **E (wrap):** flip coverage rows (Ch6/7/8 verified after CI green; Ch9 draft); full local gate run;
   push; watch CI; flip verified; open PR + merge.

## Acceptance (same bar as r01)
2,000–2,500 words/chapter + ≥1 diagram; 0 voice ban-tier; validate.py + wordcount GATE + jekyll build
green; each hands-on example both-stack `verify.sh` green in CI; coverage rows truthful.
