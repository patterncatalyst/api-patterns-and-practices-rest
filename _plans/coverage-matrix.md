---
title: "Coverage Matrix"
layout: plan
render_with_liquid: false
---

# Coverage Matrix

Every source-deck topic and every requested addition maps to exactly one
chapter. `scripts/validate.py` reads this file and fails CI when a chapter whose
**Status is not `planned`** is missing its `_docs/*.md` file — so coverage can
be authored incrementally (all rows start `planned`) while still guaranteeing no
mapped-and-claimed chapter silently disappears.

**Status legend:** `planned` (file not yet written) · `draft` (prose in,
unverified) · `verified` (both stacks run green, footer flipped).

## Deck topics → chapters (14)

| # | Deck topic | Chapter | File | Status |
|---|---|---|---|---|
| D1 | APIs & patterns | Ch1 | `_docs/01-apis-and-patterns.md` | draft |
| D2 | Resource design | Ch3 | `_docs/03-designing-around-resources.md` | draft |
| D3 | OpenAPI | Ch4 | `_docs/04-contract-first-openapi.md` | verified |
| D4 | HTTP methods + idempotency | Ch5 | `_docs/05-http-methods-idempotency.md` | verified |
| D5 | HTTP semantics | Ch6 | `_docs/06-content-negotiation-status-codes.md` | verified |
| D6 | JSON Patch vs Merge Patch | Ch7 | `_docs/07-partial-updates.md` | verified |
| D7 | Filtering & pagination | Ch8 | `_docs/08-filtering-projection-pagination.md` | verified |
| D8 | Sub-resources | Ch9 | `_docs/09-sub-resources.md` | draft |
| D9 | Async / long-running operations | Ch10 | `_docs/10-async-long-running-operations.md` | verified |
| D10 | Rerunnable jobs | Ch11 | `_docs/11-rerunnable-jobs.md` | verified |
| D11 | HATEOAS | Ch12 | `_docs/12-hateoas.md` | verified |
| D12 | Soft deletion | Ch13 | `_docs/13-soft-deletion-gdpr-purge.md` | verified |
| D13 | Versioning | Ch14 | `_docs/14-versioning.md` | verified |
| D14 | Large binary resources | Ch15 | `_docs/15-large-binary-resources-range.md` | verified |

## Additions → chapters (10)

| # | Addition | Chapter | File | Status |
|---|---|---|---|---|
| A1 | API decision framework | Ch2 | `_docs/02-api-decision-framework.md` | draft |
| A2 | OpenAPI 3.1 (in depth) | Ch20 | `_docs/20-openapi-31-in-depth.md` | planned |
| A3 | Streaming (SSE / NDJSON / chunked) | Ch16 | `_docs/16-streaming-deep-dive.md` | verified |
| A4 | Cross-protocol choices | Ch17 | `_docs/17-cross-protocol-choices.md` | draft |
| A5 | Back-end I/O concurrency | Ch18 | `_docs/18-backend-io-concurrency.md` | verified |
| A6 | HTTP/2 & HTTP/3 | Ch19 | `_docs/19-http2-http3.md` | verified |
| A7 | Multi-protocol contracts (OpenAPI/AsyncAPI/CloudEvents/Arazzo + xRegistry) | Ch21 | `_docs/21-multi-protocol-contracts.md` | planned |
| A8 | Quarkus REST in depth | Ch22 | `_docs/22-quarkus-rest-in-depth.md` | planned |
| A9 | FastAPI in depth | Ch23 | `_docs/23-fastapi-in-depth.md` | planned |
| A10 | Full testing (contract + integration + Newman + load) | Ch24 | `_docs/24-testing-rest-apis.md` | planned |

## Runtime-tier additions → chapters (3)

| # | Addition | Chapter | File | Status |
|---|---|---|---|---|
| T1 | Docker/Podman Compose tier | Ch0 / Ch25 | `_docs/25-local-with-docker-compose.md` | planned |
| T2 | minikube tier | Ch26 | `_docs/26-kubernetes-on-minikube.md` | planned |
| T3 | CRC / OpenShift Local tier | Appendix A | `_docs/99-appendix-a-openshift-crc.md` | planned |

## Full chapter inventory (27 + appendix)

| Ch | File | Part | Status |
|---|---|---|---|
| 0 | `_docs/00-prerequisites-and-the-lab.md` | Part 0 | verified |
| 1 | `_docs/01-apis-and-patterns.md` | Part 1 | draft |
| 2 | `_docs/02-api-decision-framework.md` | Part 1 | draft |
| 3 | `_docs/03-designing-around-resources.md` | Part 2 | draft |
| 4 | `_docs/04-contract-first-openapi.md` | Part 2 | verified |
| 5 | `_docs/05-http-methods-idempotency.md` | Part 2 | verified |
| 6 | `_docs/06-content-negotiation-status-codes.md` | Part 3 | verified |
| 7 | `_docs/07-partial-updates.md` | Part 3 | verified |
| 8 | `_docs/08-filtering-projection-pagination.md` | Part 4 | verified |
| 9 | `_docs/09-sub-resources.md` | Part 4 | draft |
| 10 | `_docs/10-async-long-running-operations.md` | Part 5 | verified |
| 11 | `_docs/11-rerunnable-jobs.md` | Part 5 | verified |
| 12 | `_docs/12-hateoas.md` | Part 6 | verified |
| 13 | `_docs/13-soft-deletion-gdpr-purge.md` | Part 6 | verified |
| 14 | `_docs/14-versioning.md` | Part 6 | verified |
| 15 | `_docs/15-large-binary-resources-range.md` | Part 7 | verified |
| 16 | `_docs/16-streaming-deep-dive.md` | Part 7 | verified |
| 17 | `_docs/17-cross-protocol-choices.md` | Part 7 | draft |
| 18 | `_docs/18-backend-io-concurrency.md` | Part 8 | verified |
| 19 | `_docs/19-http2-http3.md` | Part 8 | verified |
| 20 | `_docs/20-openapi-31-in-depth.md` | Part 9 | planned |
| 21 | `_docs/21-multi-protocol-contracts.md` | Part 9 | planned |
| 22 | `_docs/22-quarkus-rest-in-depth.md` | Part 9 | planned |
| 23 | `_docs/23-fastapi-in-depth.md` | Part 9 | planned |
| 24 | `_docs/24-testing-rest-apis.md` | Part 10 | planned |
| 25 | `_docs/25-local-with-docker-compose.md` | Part 11 | planned |
| 26 | `_docs/26-kubernetes-on-minikube.md` | Part 11 | planned |
| A | `_docs/99-appendix-a-openshift-crc.md` | Part 11 | planned |
| 27 | `_docs/27-complete-project.md` | Part 12 | planned |
