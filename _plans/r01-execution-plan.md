---
title: "r01 Execution Plan (Phase 2)"
layout: plan
render_with_liquid: false
---

# r01 Execution Plan — Phase 2 content (Ch0–Ch5)

Opus-planned, user-approved (2026-10-12). Executed as a relay on branch
`docs/r01-content`: Sonnet executors per step, Opus validation per batch,
checkpoint commit per step. **Verification strategy: live both-stacks in
containers, schema-validate live responses** (user-approved, full rigor).
**Standing approval: run all batches without gating between them.**

## Approach

Contract-anchored, examples-first-where-they-gate-prose. Scaffold (codetabs
include + six figures + verify library), stand up both-stack example apps +
`verify.sh`, author the three concept chapters in parallel, then the three
hands-on chapters against their now-real examples. Flip coverage rows last,
gated on a full local green run (`validate.py` + `wordcount.sh GATE=1` +
`jekyll build` + every `verify.sh`).

Examples verification: each hands-on example ships `compose.yaml` building+running
BOTH Quarkus and FastAPI from UBI 10 containers; `verify.sh` drives a request
sequence against each stack and pipes every response body through a shared
JSON-Schema-2020-12 validator against `contracts/schemas/shipping.schema.json`
(status codes AND payload semantics). Drift-proof = validator `--selftest`
(tampered body must be rejected) + documented per-example drift probe. LGTM
behind a compose profile, out of the verify path.

## Step status

| # | Step | Files | Tier | Status |
|---|---|---|---|---|
| 1 | Part pages 1–2 | `_parts/01-foundations.md`, `_parts/02-resources-with-a-contract.md` | sonnet | pending |
| 2 | Port codetabs include | `_includes/codetabs.html`, `assets/js/codetabs.js`, `assets/css/site.css`, `_layouts/default.html` | sonnet | pending |
| 3 | Six figures | `scripts/diagrams/*.py`, `assets/diagrams/*.{svg,excalidraw}`, `assets/diagrams/README.md` | sonnet | pending |
| 4 | Shared verify library | `examples/_lib/validate_response.py`, `examples/_lib/lib.sh` | sonnet | pending |
| 5 | Ch0 example (skeletons + Compose/LGTM) | `examples/00-prerequisites/**` | sonnet | pending |
| 6 | Ch4 example (anchor: both stacks serve contract) | `examples/04-contract-first/**` | sonnet | pending |
| 7 | Ch5 example (method matrix + idempotent PUT) | `examples/05-http-methods-idempotency/**` | sonnet | pending |
| 8 | CI determinism (optional, skip if venv works) | `.github/workflows/contracts.yml` | sonnet | pending |
| 9 | Ch1 APIs & patterns [C] | `_docs/01-apis-and-patterns.md` | sonnet | pending |
| 10 | Ch2 decision framework [C] | `_docs/02-api-decision-framework.md` | sonnet | pending |
| 11 | Ch3 designing around resources [C] | `_docs/03-designing-around-resources.md` | sonnet | pending |
| 12 | Ch0 prerequisites-and-the-lab [H] | `_docs/00-prerequisites-and-the-lab.md` | sonnet | pending |
| 13 | Ch4 contract-first-openapi [H, anchor] | `_docs/04-contract-first-openapi.md` | sonnet | pending |
| 14 | Ch5 http-methods-idempotency [H] | `_docs/05-http-methods-idempotency.md` | sonnet | pending |
| 15 | Flip coverage rows + catalogue | `_plans/coverage-matrix.md`, `assets/diagrams/README.md` | sonnet | pending |
| 16 | Full local gate run | (read-only) | sonnet | pending |

## Batching

- **Batch 1 (parallel):** 1, 2, 3, 4 — disjoint paths.
- **Batch 2 (sequential):** 5 → 6 → 7 (Ch5 extends Ch4). (8 only if venv insufficient.)
- **Batch 3 (parallel):** 9, 10, 11 — concept chapters, depend on Batch 1.
- **Batch 4 (parallel):** 12, 13, 14 — hands-on prose, depend on Batch 2 + figures/codetabs.
- **Batch 5 (serial):** 15 then 16.

Single-writer shared files: `_plans/coverage-matrix.md` (step 15), `assets/css/site.css`
(step 2), `assets/diagrams/README.md` (steps 3 then 15), `.github/workflows/contracts.yml` (step 8).

## Acceptance criteria (phase-wide)

1. `_parts/01-foundations.md` + `_parts/02-resources-with-a-contract.md` exist with
   `title/order/part_name/blurb`; homepage shows three Part cards.
2. Six `_docs` chapters exist with correct `title/order/part/description`; each `part:`
   matches a `_parts` `part_name`.
3. Every chapter 2,000–2,500 prose words (`GATE=1 wordcount.sh`) + ≥1 paired
   SVG+.excalidraw via `excalidraw.html`.
4. `validate.py` all checks green (unguarded-liquid, codetab-integrity, bash-syntax, coverage…).
5. Each hands-on example ships BOTH stacks + `verify.sh` asserting payload semantics; a
   contract-violating 200 fails the run.
6. CI `examples` job green within bounded runtime; `contracts` + `site` jobs stay green.
7. Coverage: Ch1/2/3 = `draft`, Ch0/4/5 = `verified` once both stacks green (else `draft`).
8. House voice; zero coffee-shop residue; callouts as raw HTML; literal Liquid in `{% raw %}`.

## Risks

- Quarkus container build time blows CI budget → JVM fast-jar + cached layers + minimal apps;
  fallback to recorded fixtures for heavier stack.
- Validator misses a 3.1 / 2020-12 construct → self-test + positive assert on `Operation`
  (`type:["string","null"]`); pin `jsonschema>=4.18` + `referencing`.
- codetab count mismatch → `validate.py` codetab-integrity (exactly 2 fences per `langs`).
- Row flipped to draft before prose in-band → flip only in step 15 after local word count passes.
- Both stacks drift in payload shape → same `verify.sh` runs against both + schema-validates.
- Compose container leak on runner → `lib.sh` trap `compose_down -v`, unique project names.
