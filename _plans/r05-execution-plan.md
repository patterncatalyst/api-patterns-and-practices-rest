---
title: "r05 Execution Plan (Phase 6)"
layout: plan
render_with_liquid: false
---

# r05 Execution Plan — Phase 6 content (Ch20–Ch24)

Relay on branch `docs/r05-content`, mirroring `_plans/r04-execution-plan.md`.
Standing approval: run batches without gating. Verification unchanged: stacks
run live in containers; `verify.sh` schema-validates/behaviour-checks live
responses via `examples/_lib/lib.sh`. Five hands-on chapters (all [H]) across
two new parts. Ch21 builds on the already-authored `contracts/` artifacts — it
wires an example to them, it does NOT recreate them.

## Approach
- Five [H] chapters, each 2,000–2,500 words + ≥1 paired SVG+`.excalidraw`.
  Part 9 bundles OpenAPI depth, multi-protocol contracts, and the two
  framework deep-dives; Part 10 is the single testing chapter.
- **OpenAPI version framing (constraint change):** the site is kept
  continuously current, so prose leads with the *capability*, not a version
  label. Ch20 is retitled **"OpenAPI in depth"** and its file is
  `_docs/20-openapi-in-depth.md` (renamed from the old `...-31-...`). A version
  number appears only at the one callout where the feature *is* the version —
  full JSON Schema 2020-12 alignment as the shift that makes type
  arrays/`nullable`/webhooks possible. A light sweep softens gratuitous
  "OpenAPI 3.1"/"3.1" labels already in prose (esp. Ch4) and in figure specs.
  Machine fields are untouched: no contract file is renamed and no
  `openapi: 3.1.0` key is changed.
- **Decision A (Ch22/Ch23 single- vs both-stack): SINGLE-STACK.** Ch22 ships a
  Quarkus-only example; Ch23 ships a FastAPI-only example. Rejected "both in
  each" — see below.
- **Decision B (Ch21 CI shape): real minimal broker in CI, registry
  tier-gated local-only.** A single-node Kafka (KRaft, no ZooKeeper) in the
  compose — the broker our AsyncAPI contract already names (`servers.kafka`,
  `protocol: kafka`, "Local Kafka (KRaft)"); `verify.sh`
  drives REST → background CloudEvents emission → broker consume → envelope +
  `$defs` validation. A governance tier — Apicurio Registry (schema/artifact
  registry + xRegistry touchpoint) AND OpenMetadata (data catalog that tracks
  version/schema changes over time; NOT an xRegistry impl) — is SHOWN with a
  reproducible local walkthrough behind compose profiles but kept OUT of CI.
  Rejected both pure-option-1 and pure-option-2 — see below.

## Judgment call A — Ch22/Ch23 are single-stack (resolved)
Ch22 "Quarkus REST in depth" and Ch23 "FastAPI in depth" are the per-framework
superiority/corollary chapters; their whole point is idiomatic depth in ONE
stack (build-time metadata and zero-reflection `@RestHeader`/`@RestQuery` are
Quarkus-only; ASGI/GIL/free-threaded are Python-only). Shipping both would
duplicate the cross-stack coverage every *other* chapter already carries and
dilute the "in depth" framing. **Rejected:** both-stacks-per-chapter — rejected
because the comparison already lives in Ch20/Ch21/Ch24, and a forced mirror
would pull each chapter away from its framework-specific thesis.
Harness/CI still work for a single-stack dir: `discover-examples` globs
`examples/*/verify.sh` regardless of how many services the dir runs, and
`lib.sh` (`compose_up`, `wait_for_http`, `validate_body`) is stack-agnostic —
the single-stack `verify.sh` simply waits on its one port.

## Judgment call B — Ch21 CI shape (resolved)
**Chosen:** CI runs a single-node **Kafka in KRaft mode** (one container, no
ZooKeeper, fast deterministic boot) plus the two thin apps. This is the broker
our stack already standardizes on and the one the committed AsyncAPI contract
names (`contracts/asyncapi/shipping-events.yaml` → `servers.kafka`,
`protocol: kafka`, "Local Kafka (KRaft) from the Docker Compose stack") — the
example must run on the broker its own contract declares, and KRaft keeps it to a
single CI-friendly container. `verify.sh`:
(1) `POST` a booking over REST to each stack → response validated against
`$defs/Booking`; (2) the service emits a **CloudEvents**-enveloped
`BookingEvent` to the broker as a background action; verify consumes it with a
*bounded* timeout and validates the CloudEvents envelope attributes + `data`
against `$defs/BookingEvent`; (3) static schema-reuse assertion — the shared
`contracts/schemas/shipping.schema.json` is `$ref`'d by BOTH
`contracts/openapi/shipping-api.yaml` and `contracts/asyncapi/shipping-events.yaml`;
(4) the Arazzo `booking-workflow.yaml` validates.

**Governance tier (local-only, SHOWN not just mentioned, tier-gated out of CI like
h3 in Ch19) — two complementary tools, kept conceptually distinct:**
- **Apicurio Registry** behind a `registry` compose profile — the schema/artifact
  **registry** and the **xRegistry** touchpoint. The chapter SHOWS publishing the
  OpenAPI + AsyncAPI + shared schema artifacts and resolving them at runtime, and
  surfaces the xRegistry model/API view.
- **OpenMetadata** behind an `catalog` compose profile — a **data catalog**, NOT an
  xRegistry impl (do not conflate the two; state the distinction explicitly in the
  prose). The chapter SHOWS OpenMetadata ingesting the API/schema artifacts and
  then **tracking version and schema changes over time** — a schema evolution /
  version bump appears as a detected change with lineage, which is the governance
  story a registry alone doesn't tell. Provide a concrete local walkthrough
  (compose profile up → ingest → make a schema/version change → show it detected),
  with figures/console captures, so the reader can reproduce it.

Both governance tools are heavy (OpenMetadata needs its own datastore + search +
ingestion) and are the flakiest pieces, so both stay OUT of the CI gate; CI proves
only the live REST + Kafka + CloudEvents path. **Rejected — pure option 1** (broker
+ registry/catalog all in CI): registry/catalog startup + ingestion is the
heaviest/flakiest piece and not the load-bearing teaching point of the live check.
**Rejected — pure option 2** (no broker, all static): it demotes "background event
streaming in one microservice" to a doc check and under-teaches the integrative
core. The hybrid keeps the REST+event path live and deterministic in CI while the
governance tier is fully runnable locally.

## Scope / Examples (UNIQUE host ports; Quarkus 8100+, Python 8020+)
- `examples/20-openapi-depth` — **both** stacks, 8100 (Quarkus) / 8020 (Python),
  project `ch20-openapi`. Each stack serves its generated OpenAPI document
  (`/q/openapi`, `/openapi.json`). verify asserts: the doc is served and
  exercises modern constructs (type arrays / `nullable` via JSON Schema,
  `webhooks`); a **drift check** — the live-generated spec conforms to the
  committed `contracts/openapi` shape (normalize, then assert, not byte-equal);
  a live response body validates against the shared `$defs`.
- `examples/21-multi-protocol-contracts` — **both** stacks + broker, 8101 /
  8021, Kafka (KRaft) broker on 19092 (host), project `ch21-contracts`. verify as
  in Decision B. Governance tier local-only: Apicurio on 8104 behind the
  `registry` profile; OpenMetadata on 8585 behind the `catalog` profile (plus its
  own datastore/search containers in that profile). Neither in CI.
- `examples/22-quarkus-rest-depth` — **Quarkus only**, 8102, project
  `ch22-quarkus`. Zero-reflection `@RestHeader`/`@RestQuery` endpoint +
  reactive NDJSON/large-JSON streaming. verify asserts: a `@RestHeader` is
  bound and echoed, a `@RestQuery` drives the response, NDJSON arrives
  **incrementally** (`curl -N` + timing/counts), body validates against `$defs`.
  LangChain4j SSE / Camel Quarkus / JobRunr covered in prose; at most ONE thin
  extra (JobRunr background job or a LangChain4j-style SSE stub) to avoid
  scope-creep.
- `examples/23-fastapi-depth` — **FastAPI only**, 8022, project `ch23-fastapi`.
  ASGI `StreamingResponse`/SSE + `BackgroundTasks`. verify asserts: SSE/stream
  arrives incrementally (`curl -N` + timing), a `BackgroundTask` side effect is
  observable after the response returns, body validates against `$defs`.
- `examples/24-testing` — **both** stacks + Newman, 8103 / 8023, project
  `ch24-testing`. Contract tests vs OpenAPI (+ AsyncAPI/CloudEvents validation
  on the event side), `@QuarkusTest` + pytest at build time, and a **vendored
  CNDP Newman harness** (from `~/Dev/cloud-native-design-patterns/examples/28-newman`,
  adapted: `collections/` + compose runner) run against BOTH live stacks. verify
  asserts the Newman collection passes against both stacks and contract
  assertions hold; any load run is tiny/bounded (assert pass/counts, not
  absolute latency).

## Figures (paired svg+excalidraw; specs in `scripts/diagrams/`)
`20-openapi-in-depth` · `21-multi-protocol-contracts` · `22-quarkus-rest-in-depth` ·
`23-fastapi-in-depth` · `24-testing-rest-apis`
(spec files `fig_20_openapi_in_depth.py` … `fig_24_testing_rest_apis.py`, amber
`#e8870c`, via `scripts/generate_diagram.py`).

## Parts (check `_parts/` numbering — existing run 00–08)
- `_parts/09-multi-protocol-contracts-and-frameworks.md` (order 9) —
  `part_name: "Multi-protocol contracts & framework deep-dives"`; chapters
  Ch20–Ch23 set `part:` to that string.
- `_parts/10-testing.md` (order 10) — `part_name: "Testing"`; Ch24 sets
  `part:` to that string.

## Coverage-matrix edits (do up front — validate.py reads filenames)
- Additions row **A2**: title → "OpenAPI (in depth)", file →
  `_docs/20-openapi-in-depth.md`.
- Full chapter inventory row **20**: file → `_docs/20-openapi-in-depth.md`.
- Ch20–Ch24 statuses flip `planned` → `draft` (prose in) → `verified` (CI green).

## Batches
1. **A (parallel):** rename Ch20 row in `coverage-matrix.md` (both tables);
   two Part pages (09, 10); five figure specs + generated pairs (20–24);
   the OpenAPI version-label sweep across `_docs/*` (esp. Ch4) and
   `scripts/diagrams/*` prose (soften gratuitous "3.1"; keep the one JSON
   Schema 2020-12 feature callout; touch no contract YAML / no `openapi:`
   key).
2. **B (sequential example builds):** Ch20 → Ch21 → Ch22 → Ch23 → Ch24, each
   `verify.sh` green locally before the next starts; launch each chapter's
   prose after its example lands. Ch21 is the integration-risk gate — get its
   broker path deterministic before moving on.
3. **D (validation):** Opus adversarial pass on the five chapters (voice,
   accuracy, contract-reuse claims, single-stack framing, version-label sweep).
4. **E (wrap):** flip coverage rows to `draft` as prose lands; full local gate
   (`python3 -I scripts/validate.py`, `GATE=1 bash scripts/wordcount.sh`,
   `bundle exec jekyll build --trace`); push; watch CI; flip Ch20–Ch24 to
   `verified` only after the examples matrix is green; open PR + merge.

## Acceptance (same bar as r01–r04)
- 2,000–2,500 words each for Ch20–Ch24; ≥1 paired SVG+`.excalidraw` diagram per
  chapter (figures 20–24 present).
- 0 voice ban-tier (lgtm-professional-voice scan clean).
- `validate.py` + wordcount `GATE=1` + `jekyll build` all green.
- Each example `verify.sh` green in GitHub Actions: Ch20/Ch21/Ch24 both-stack;
  Ch22 Quarkus-only and Ch23 FastAPI-only single-stack dirs discovered by the
  matrix and green; Ch21 runs its Kafka (KRaft) path in CI with Apicurio tier-gated
  out (documented + locally runnable).
- Coverage rows truthful (Ch20–Ch24 `verified` only after CI green); the two
  Ch20 filename rows match `_docs/20-openapi-in-depth.md`.
- CNDP Newman harness vendored into `examples/24-testing`.
- No prose carries gratuitous OpenAPI version labels; a version number appears
  only at the JSON Schema 2020-12 feature callout. No contract file renamed; no
  `openapi:` version key changed.

## Risks (each with how it's detected)
- **Ch21 broker/registry flakiness** → single-node Kafka in KRaft mode (one
  container, no ZooKeeper), bounded consume timeout, Apicurio tier-gated
  local-only. Detected by verify consume-timeout and CI job duration/retries.
- **Both-stack + broker CI time (Ch21)** → keep both apps thin, share one
  broker container. Detected by the `verify: 21-...` job wall-clock.
- **Single-stack matrix edge cases (Ch22/Ch23)** → `verify.sh` waits only on
  its one service; confirm the dir appears in the discover-examples matrix.
  Detected by the matrix entry being present and green.
- **Ch20 drift-detection false positives** → compare normalized/canonical spec
  or validate-against, never byte-equality. Detected by verify stability on
  reruns.
- **LangChain4j/Camel/JobRunr scope-creep (Ch22)** → example stays
  REST-depth-focused (headers/query/streaming); extras are prose, at most one
  thin demo. Detected by example dependency count and build time.
- **Load-test determinism (Ch24)** → tiny bounded Newman/load run; assert
  pass/counts, not latency. Detected by flaky reruns.
- **Version-label sweep over-softening** → soften prose only; preserve the one
  JSON Schema 2020-12 callout and all machine fields. Detected by the Opus
  validation pass and a grep diff review.
- **Push branch with `-u` immediately** (branch already pushed); keep CI green
  on every push.
