---
title: "Build & Iteration Plan"
layout: plan
render_with_liquid: false
---

# Build & Iteration Plan — API Patterns and Practices: REST

Synthesized (ultraplan) from three Opus planning passes — risk-first (engineering
spine), simplest-first (release cadence), reader-outcome (pedagogy). Status:
**awaiting review**. No chapter prose or code is written until this plan is approved.

## Approach

- **Contract-first spine.** One OpenAPI contract (`contracts/openapi/shipping-api.yaml`,
  booking + cargo domain) is the single source of truth. It is authored before the
  first implementation and a CI job validates **both** the Quarkus and FastAPI
  implementations against it — drift fails the build.
- **Both stacks are first-class.** Every hands-on chapter ships a Quarkus **and** a
  Python/FastAPI example against the identical contract (per the project requirement).
  Iterations stage work by *parts*, not by stack, so the two never diverge.
- **Contracts across the sync/async divide (cross-cutting thread).** The site threads the four
  contract languages and shows when each applies and how they compose: **OpenAPI** (synchronous
  request/response), **AsyncAPI 3** (event channels / background streaming), **CloudEvents** (the
  event envelope + metadata), and **Arazzo** (multi-step API workflows/sequences across calls).
  Core payload types live once in shared JSON Schema components under `contracts/schemas/` and are
  **reused** by both the OpenAPI and AsyncAPI documents (no duplicated type definitions); a
  microservice that pairs REST calls with background event streaming is the worked example. Gets a
  dedicated chapter (Ch21), a recurring "which contract?" Decision box, and is applied in the complete project.
- **Outcome-driven.** Every Part opens with an "after this part, the reader can…"
  capability. The **API decision framework** is a first-class chapter early (Ch2) and
  recurs as a "Decision" callout closing each concept chapter, then is exercised whole
  in the complete project.
- **Auditable coverage.** `_plans/coverage-matrix.md` maps every deck topic and every
  requested addition to a chapter; CI fails if a mapped chapter file is missing.
- **Behavioral verification.** Each example carries a `verify.sh` that asserts payload
  semantics against the contract — a 200 with a contract-violating body fails. A
  chapter's `*Verification status: verified*` footer flips only after both stacks run green.
- **Always releasable.** Ship in increments r01→r06; each ends on a clean Jekyll build
  with the iteration table updated.

Rejected: chapters-first/contract-later (unenforceable drift); single reference stack
(violates the both-stacks requirement); status-code-only verification (a 200 can lie);
big-bang all-chapters (no releasable checkpoint).

## Part → Chapter outline (every deck topic + addition mapped)

Legend: **[H]** hands-on (runnable example in BOTH stacks), **[C]** concept.
**Depth standard (every chapter):** 2,000–2,500 words of prose (excluding code listings, diagram
captions and command output) and **≥1 paired SVG+.excalidraw diagram** embedded in the chapter —
concept and hands-on alike, per the other patterncatalyst sites.

**Part 0 — Prerequisites & the Lab** · _r01_
_After this part, the reader has the contract-first toolchain running locally._
- **Ch0** Prerequisites, toolchain pins (Quarkus latest LTS, Python/FastAPI+Poetry, UBI 10), Docker Compose + LGTM, the shipping/cargo domain + coffee-shop→cargo glossary. [H-setup] — *addition: Docker tier*

**Part 1 — Foundations & the decision lens** · _r01_
_After this part, the reader can decide whether REST fits an interaction and name the constraint it rests on._
- **Ch1** APIs & patterns: RPC vs Web APIs; REST constraints; resource-oriented architecture. [C] — *deck: APIs & patterns*
- **Ch2** The API decision framework (which pattern/style/transport; the criteria axes reused in every Decision box). [C] — *addition: decision framework*

**Part 2 — Designing resources with a contract** · _r01_
_After this part, the reader can model a domain as resources and express it as an OpenAPI contract CI enforces against both stacks._
- **Ch3** Designing around resources: nouns not verbs, don't mirror the DB, collections vs items, chatty-API/extraneous-fetch anti-patterns. [C] — *deck: resource design*
- **Ch4** Contract-first with OpenAPI: author bookings+cargo, CI validation wired, both stacks scaffolded to serve it. [H] (anchor) — *deck: OpenAPI; addition: OpenAPI*
- **Ch5** HTTP methods & the idempotency matrix. [H] — *deck: HTTP methods + idempotency*

**Part 3 — HTTP semantics done right** · _r02_
_After this part, the reader can return correct status codes, headers and representations, and do partial updates two correct ways._
- **Ch6** Content negotiation & status codes: Content-Type/Accept, 415/406, 200/201/204/400/404/409, Location. [H] — *deck: HTTP semantics*
- **Ch7** Partial updates: JSON Patch (RFC 6902) vs JSON Merge Patch. [H] — *deck: JSON Patch vs Merge Patch*

**Part 4 — Collections at scale** · _r02_
_After this part, the reader can design collection endpoints that stay fast and safe under load and choose a pagination strategy on purpose._
- **Ch8** Filtering, field projection & pagination: offset / keyset / seek (after_id), sane defaults, limits as a DoS guard. [H] — *deck: filtering & pagination*
- **Ch9** Sub-resources: nesting trade-offs, caching, redundant-endpoint pitfalls. [C + small H] — *deck: sub-resources*

**Part 5 — Asynchronous work & jobs** · _r03_
_After this part, the reader can model work that doesn't finish within one request/response._
- **Ch10** Asynchronous / long-running operations: 202 + Location, status polling, 303 on completion, cancel link. [H] — *deck: async/LRO*
- **Ch11** Rerunnable jobs: server-owned schedules, configure-vs-execute split (JobRunr / FastAPI background). [H] — *deck: rerunnable jobs*

**Part 6 — Evolution & lifecycle** · _r03_
_After this part, the reader can evolve an API without breaking clients and delete under compliance rules._
- **Ch12** HATEOAS: state-dependent links, the response as a finite-state machine, self links. [H] — *deck: HATEOAS*
- **Ch13** Soft deletion & GDPR purge: audit, referential integrity, hidden-from-queries, purge job. [H] — *deck: soft deletion*
- **Ch14** Versioning: URI / query / header / media-type + caching implications. [H] — *deck: versioning*

**Part 7 — Large payloads & streaming** · _r04_
_After this part, the reader can move large or continuous data over REST and recognize when to leave REST._
- **Ch15** Large binary resources & Range requests: HEAD, Accept-Ranges, Range, 206, Content-Range. [H] — *deck: large binary resources*
- **Ch16** Streaming deep-dive: chunked transfer encoding, SSE, NDJSON, media/Range, real-time updates, large downloads. [H] — *addition: streaming*
- **Ch17** Cross-protocol choices: REST vs WebSockets vs webhooks vs gRPC, especially for streaming. [C] — *addition: cross-protocol*

**Part 8 — Performance & transport** · _r04_
_After this part, the reader can reason about backend concurrency and HTTP/2-3 behavior behind the API._
- **Ch18** Back-end I/O concurrency: Quarkus blocking vs reactive/virtual threads; Python async vs threads/GIL; DB + file I/O behind an API without thread exhaustion. [H] — *addition: backend I/O concurrency*
- **Ch19** REST over HTTP/2 & HTTP/3: multiplexing, HPACK/QPACK, TCP head-of-line blocking vs QUIC stream isolation, connection migration, 0-RTT. [C + measured H] — *addition: HTTP/2 & HTTP/3*

**Part 9 — Multi-protocol contracts & framework deep-dives** · _r05_
_After this part, the reader can treat the contract as living, compose REST with event contracts, and build idiomatic REST in each stack._
- **Ch20** OpenAPI in depth: JSON Schema 2020-12 alignment, type arrays/nullable, webhooks, generation in both stacks, drift detection. [H] — *addition: OpenAPI depth*
- **Ch21** Multi-protocol contracts — OpenAPI + AsyncAPI 3 + CloudEvents + Arazzo: what each solves and when to reach for it; **schema reuse** (shared JSON Schema components referenced by both the OpenAPI and AsyncAPI docs); pairing REST calls with background **event streaming** in one microservice; CloudEvents as the event envelope; **Arazzo** describing the multi-step booking→routing→tracking workflow; **registry** touchpoint — publish/resolve the OpenAPI + AsyncAPI + schema artifacts in **Apicurio Registry** (already in the stack; CNCF, aligning to the **xRegistry** spec) and show the **xRegistry** model/API via Apicurio and/or the xRegistry reference server. (Apicurio xRegistry compliance is on its roadmap — verify support level at authoring time; OpenMetadata is a data catalog, not an xRegistry impl.) [H] — *addition: multi-protocol contracts (OpenAPI/AsyncAPI/CloudEvents/Arazzo + xRegistry via Apicurio)*
- **Ch22** Quarkus REST in depth: build-time metadata, zero-reflection @RestHeader/@RestQuery, reactive-first streaming of files/large JSON/NDJSON, LangChain4j SSE, Camel Quarkus/CXF, JobRunr. [H] — *addition: Quarkus section*
- **Ch23** FastAPI in depth: ASGI streaming, StreamingResponse/SSE, BackgroundTasks, threads vs async for I/O, GIL/free-threaded. [H] — *addition: FastAPI corollary*

**Part 10 — Testing** · _r05_
_After this part, the reader can prove an implementation conforms to the contract and behaves under load._
- **Ch24** Testing REST APIs: contract tests vs OpenAPI (and AsyncAPI/CloudEvents validation for the event side), @QuarkusTest + pytest integration, Newman, load testing (reuse the CNDP harness at `examples/28-newman`). [H] — *addition: full testing*

**Part 11 — Running it: Docker → minikube → CRC** · _r06_
_After this part, the reader can run and observe the API where its Kubernetes behavior differs from Compose._
- **Ch25** Local with Docker/Podman Compose + LGTM, one request traced end to end. [H] — *addition: Docker tier*
- **Ch26** Kubernetes differences on minikube: ingress vs compose networking, probes, config/secrets, HPA. [H] — *addition: minikube tier*
- **Appendix A** OpenShift Local (CRC): Routes, edge TLS, in-cluster build (use the `lgtm-crc` skill). [H] — *addition: CRC tier*

**Part 12 — Complete project** · _r06_
_After this part, the reader can make and defend a complete REST design decision end to end._
- **Ch27** Complete project: the shipping/cargo booking API end to end — contract-first booking + cargo, async confirmation (202→poll→303), keyset pagination, HATEOAS, media-type versioning, soft delete + purge, streamed manifest, **plus a background CloudEvents stream (AsyncAPI) sharing schemas with the REST contract and an Arazzo workflow tying the sequence together**, traced through LGTM, contract-validated and load-tested in both stacks. [H] — *integrative*

**Coverage:** 27 chapters + CRC appendix across 12 parts. All deck topics and all additions (incl. the multi-protocol-contracts thread) map to a chapter (maintained in `_plans/coverage-matrix.md`, CI-checked).

## Per-hands-on example plan (both stacks, against `contracts/openapi/shipping-api.yaml`)

Ch0 boot skeleton + compose/LGTM · Ch4 both stacks serve the contract, CI validates ·
Ch5 method matrix + idempotent PUT · Ch6 201+Location, 415/406, 409 · Ch7 RFC 6902 +
merge-patch on a booking · Ch8 offset/keyset/seek + field projection · Ch9 nested vs flat
cargo · Ch10 async confirmation 202→poll→303+cancel · Ch11 scheduled manifest-reconcile
job · Ch12 state-dependent links · Ch13 soft-delete + filtered reads + purge · Ch14 URI
+ media-type versioning · Ch15 HEAD+Range→206 on a manifest · Ch16 SSE cargo events +
NDJSON export + ranged download · Ch18 reactive vs blocking (Quarkus) / async vs threads
(FastAPI) over Postgres + files, measured · Ch19 same service over h1/h2/h3, measured ·
Ch20 edit contract → regenerate/validate → deliberate drift fails CI · Ch21 one microservice:
REST booking (OpenAPI) + background CloudEvents stream described by AsyncAPI, both referencing the
same `contracts/schemas/` components, with an Arazzo workflow for booking→routing→tracking · Ch22
Quarkus zero-reflection + reactive streaming · Ch23 FastAPI ASGI streaming + background tasks ·
Ch24 contract + integration + Newman + load · Ch25 compose + trace · Ch26 minikube ·
AppA CRC · Ch27 complete project.

## Diagrams (≥1 per chapter, paired `.svg`+`.excalidraw` in `assets/diagrams/`)

Every chapter embeds at least one figure. Named concept figures:
`01-rest-constraints` · `02-decision-framework` (reused throughout) · `03-resource-model`
· `05-idempotency-matrix` (Ch5) · `09-sub-resources` · `10-async-lifecycle` (202→poll→303)
· `12-hateoas-state-machine` · `14-versioning-strategies` · `16-streaming-modes` ·
`17-cross-protocol` · `19-http2-http3` · `21-multiprotocol-contracts` (OpenAPI/AsyncAPI/CloudEvents/
Arazzo + shared schema components, REST+events microservice). Every remaining chapter gets a
purpose-built figure too (e.g. Ch4 contract-first flow, Ch6 negotiation/status decision, Ch7
patch-vs-merge, Ch8 pagination strategies, Ch11 job lifecycle, Ch13 soft-delete+purge flow, Ch15
range-request sequence, Ch18 concurrency model, Ch20 living-contract CI loop, Ch22/23 request
pipelines, Ch24 test pyramid, Ch25/26 deploy topology, Ch27 complete project architecture). Each hands-on
example additionally ships its own `architecture.{svg,excalidraw}` (CNDP convention).

## Execution phases (checkpoint commit after each)

- **Phase 1 — Contract & CI spine** *(retires top risks; blocks all chapters).*
  `contracts/openapi/shipping-api.yaml` (+ v1/v2 stubs for Ch14), `contracts/asyncapi/` (event
  channels), `contracts/schemas/` (shared JSON Schema components reused by both OpenAPI & AsyncAPI),
  and `contracts/cloudevents/` + `contracts/arazzo/` (envelope + workflow) laid out from the start;
  `_plans/coverage-matrix.md`
  + `_plans/domain-glossary.md`; `.github/workflows/contracts.yml` (lint + build both stacks +
  run each `verify.sh` + fail on schema drift); port `scripts/generate_diagram.py`; add
  `scripts/wordcount.sh` (2,000–2,500 gate) + a per-chapter "has ≥1 diagram" check; `_config.yml` exclude `contracts/`; **replace the
  residual eBPF/Aya scaffold copy** in `index.html` and placeholder chapters. Commit `ci: contract-first spine`.
- **Phase 2 — r01 content:** Parts 0–2 (Ch0–5) prose + both-stack examples + concept diagrams + deck-map seed.
- **Phase 3 — r02:** Parts 3–4 (Ch6–9).
- **Phase 4 — r03:** Parts 5–6 (Ch10–14).
- **Phase 5 — r04:** Parts 7–8 (Ch15–19).
- **Phase 6 — r05:** Parts 9–10 (Ch20–24); vendor the CNDP load/Newman harness.
- **Phase 7 — r06:** Part 11 (Ch25–26 + Appendix A, minikube + CRC) and Part 12 (Ch27 complete project).
- **Phase 8 — Deck + polish + release:** build the conference deck from the site via `lgtm-presentation`
  (coffee-shop→cargo), `lgtm-professional-voice` sweep, hub entry in
  `patterncatalyst-workshops-tutorials-list/_data/sites.yml`, tag + release via `lgtm-github`.

Each code phase is executed as a relay (Sonnet executors per chapter/example, Opus validation
against the acceptance criteria) with a checkpoint commit per chapter that lands green.

**"Shippable r01"** = Jekyll builds clean with Parts 0–2 authored to depth; the OpenAPI
contract exists and CI validates **both** stacks against it on Docker Compose; every r01
hands-on chapter has verified-run Quarkus + FastAPI examples; r01 diagrams paired; nav/cards
resolve; no eBPF/Aya residue.

## Acceptance criteria

1. `docker/podman compose up` brings up the REST service + LGTM; one request is traced end to end.
2. Every `examples/*` validates against `contracts/openapi/` in CI; a deliberate response-schema drift **fails** the build.
3. Both stacks exist for every hands-on chapter and pass the **same** `verify.sh` (payload semantics, not status code).
4. `_plans/coverage-matrix.md` maps all 14 deck topics + 10 additions to chapters; CI fails on a missing mapped file.
5. Each chapter is 2,000–2,500 words excl. code/captions/output (`scripts/wordcount.sh`); **every** chapter embeds ≥1 paired SVG+.excalidraw diagram; verification footer flips only on green.
6. `bundle exec jekyll build` green on every push; no residual eBPF/Aya scaffold copy.
7. Runs on all three tiers: compose (Ch24), minikube (Ch25), CRC (Appendix A).
8. Ch23 runs a Newman collection + a load test on the reused CNDP harness, green in CI.
9. The deck covers every deck agenda item, translated to shipping/cargo; `lgtm-professional-voice` scan reports zero flagged tics.
10. Hub `_data/sites.yml` has a live entry; release PR to `main` is green and deploys.
11. Core payload types are defined once in `contracts/schemas/` and referenced by BOTH the OpenAPI and AsyncAPI documents (no duplicated type definitions); events validate against CloudEvents; an Arazzo workflow describes the complete project sequence; artifacts are published to Apicurio Registry (xRegistry touchpoint).

## Resolved decisions (reviewer, 2026-10-11)

- **Stacks:** BOTH Quarkus **and** FastAPI per hands-on chapter against the identical contract. ✅
- **Accent:** house amber (consistent with the lgtm family). ✅
- **Granularity:** 27 chapters + CRC appendix across 12 parts (was 26; +Ch21 multi-protocol contracts). ✅
- **Runtime tiers:** minikube (Ch25) and CRC (Appendix A) as **full hands-on chapters**. ✅

Plan approved at these settings. Execution begins at Phase 1 (contract & CI spine).

## Risks (and detection)

- Behavioral lie (200 while violating contract) — `verify.sh` asserts payload + CI schema-validates live responses. *Retired Phase 1.*
- Dual-stack divergence — same `verify.sh` both stacks + single-spec CI. *Both stacks first-class.*
- Silent coverage gap — coverage matrix + CI file-exists check. *Phase 1.*
- Domain-translation inconsistency — single glossary + one canonical contract; voice pass greps coffee-shop residue. *Phase 1.*
- HTTP/3/QUIC hard to demo behind compose/ingress (UDP) — Ch19 tier-gates h3, documents fallback, verifies h2 everywhere.
- SSE/chunked buffered behind K8s ingress — Ch16/Ch25 behavioral test asserts incremental delivery.
- CNDP load-harness shape (`examples/28-newman`) — confirm/vendor early in Phase 6; pin under `examples/_harness/` if needed.
- OpenAPI / JSON-Schema-2020-12 tooling gaps (support can be uneven) — choose a capable validator in Phase 1; assert modern constructs.
- Scope overrun (26 ch × 2 stacks) — r01–r06 cadence; each iteration independently shippable.
- Toolchain pin drift (latest LTS, UBI 10) — pin in Ch0 + Containerfiles; CI build is the canary.
