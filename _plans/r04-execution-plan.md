---
title: "r04 Execution Plan (Phase 5)"
layout: plan
render_with_liquid: false
---

# r04 Execution Plan — Phase 5 content (Ch15–Ch19)

Relay on branch `docs/r04-content`, mirroring `_plans/r03-execution-plan.md`.
Standing approval: run batches without gating. Verification unchanged: both
stacks live in containers, `verify.sh` schema-validates/behaviour-checks live
responses. Four hands-on chapters (Ch17 is concept — no new example).

## Scope (from `_plans/iteration-plan.md`)
- **Part 7 — Large payloads & streaming:** Ch15 large binary resources & Range (HEAD, Accept-Ranges,
  Range, 206, Content-Range) [H]; Ch16 streaming deep-dive (chunked TE, SSE, NDJSON, large downloads,
  real-time updates) [H]; Ch17 cross-protocol choices (REST vs WebSockets vs webhooks vs gRPC) [C].
- **Part 8 — Performance & transport:** Ch18 back-end I/O concurrency (Quarkus blocking vs reactive/
  virtual threads; Python async vs threads/GIL; DB+file I/O without thread exhaustion) [H, measured];
  Ch19 REST over HTTP/2 & HTTP/3 (multiplexing, HPACK/QPACK, HOL blocking vs QUIC, connection migration,
  0-RTT) [C + measured H].

## Examples (extend the Ch4 anchor; UNIQUE host ports; Ch17 has NO example)
- `examples/15-range-requests` — 8095/8015, project `ch15-range`. A manifest resource: `HEAD` →
  Accept-Ranges + Content-Length; `GET` with `Range: bytes=…` → 206 + Content-Range + partial body;
  full `GET` → 200; bad range → 416. verify asserts byte-exact partial content + headers.
- `examples/16-streaming` — 8096/8016, project `ch16-stream`. SSE cargo-event stream
  (`text/event-stream`), NDJSON export (`application/x-ndjson`), chunked transfer. verify asserts
  INCREMENTAL delivery (events/lines arrive over time, not one buffered blob) via `curl -N` + timing/counts.
- `examples/18-concurrency` — 8097/8017, project `ch18-conc`. An endpoint doing simulated DB+file I/O;
  Quarkus blocking vs reactive/virtual-threads, Python async vs threadpool. verify fires K concurrent
  requests and asserts all succeed AND wall-clock << K×latency (concurrency, not serialization). Keep K
  and per-request latency small + bounded for CI.
- `examples/19-http2-http3` — 8098/8018, project `ch19-h2`. Same service reachable over HTTP/1.1 and
  HTTP/2 (h2c prior-knowledge in-container, no TLS); verify asserts the negotiated protocol is HTTP/2
  (`curl --http2-prior-knowledge -w '%{http_version}'`). **HTTP/3/QUIC is UDP and impractical behind CI/
  compose networking — TIER-GATE it: document h3 + a local-only path, keep it OUT of verify.sh; verify h2
  everywhere** (per the plan's risk note).

## Figures (paired svg+excalidraw; specs in scripts/diagrams/)
`15-range-request-sequence` · `16-streaming-modes` · `17-cross-protocol` · `18-concurrency-model` ·
`19-http2-http3`.

## Parts
`_parts/07-large-payloads-and-streaming.md` (order 7), `_parts/08-performance-and-transport.md` (order 8).

## Batches
1. **A (parallel):** two Part pages; five figures.
2. **B (sequential example builds):** Ch15 → Ch16 → Ch18 → Ch19, each green before next; launch each
   hands-on chapter's prose after its example lands. Ch17 (concept) prose can run in parallel with Batch B
   (depends only on its figure).
3. **D (validation):** Opus adversarial pass on the five chapters.
4. **E (wrap):** flip coverage rows (Ch15/16/18/19 verified after CI green; Ch17 draft as concept); full
   local gate; push; watch CI; flip verified; open PR + merge.

## Acceptance (same bar as r01–r03)
2,000–2,500 words/chapter + ≥1 diagram; 0 voice ban-tier; validate.py + wordcount GATE + jekyll build
green; each hands-on example both-stack `verify.sh` green in CI (h3 tier-gated out); coverage rows truthful.
Push branch with `-u` immediately.

## Risks
- SSE/chunked buffered behind a proxy → Ch16 verify asserts incremental delivery with `curl -N` + timing.
- Concurrency test flaky/slow in CI → bound K and latency; assert ratio, not absolute times.
- HTTP/3/QUIC not runnable in CI → h3 documented + local-only; verify h2 only.
- Measured examples nondeterministic → keep loads tiny and assert relative behaviour.
