---
title: "Outline"
order: 0
overview: true
part: "Prerequisites & the Lab"
description: "What this site covers and how it's organized — 27 chapters across 12 parts, both stacks against one contract."
---

This site teaches REST API design against a single OpenAPI contract for a
shipping and cargo booking domain. Every hands-on chapter ships the same example
in **both Quarkus and Python/FastAPI**, and CI validates both stacks against the
contract so they never drift. The full arc is below; the build &amp; iteration
plan, coverage matrix and domain glossary (linked in the footer) carry the
detail.

Legend: each chapter below is tagged **[H]** hands-on (runnable in both stacks),
**[C]** concept, or **[C+H]** where a concept chapter also ships a runnable example.

**Part 0 — Prerequisites & the Lab**

- [Ch0. Prerequisites & the Lab](/docs/00-prerequisites-and-the-lab/) — [H]

**Part 1 — Foundations & the decision lens**

- [Ch1. APIs & patterns](/docs/01-apis-and-patterns/) — [C]
- [Ch2. The API decision framework](/docs/02-api-decision-framework/) — [C]

**Part 2 — Designing resources with a contract**

- [Ch3. Designing around resources](/docs/03-designing-around-resources/) — [C]
- [Ch4. Contract-first with OpenAPI](/docs/04-contract-first-openapi/) — [H]
- [Ch5. HTTP methods & the idempotency matrix](/docs/05-http-methods-idempotency/) — [H]

**Part 3 — HTTP semantics done right**

- [Ch6. Content negotiation & status codes](/docs/06-content-negotiation-status-codes/) — [H]
- [Ch7. Partial updates: JSON Patch vs Merge Patch](/docs/07-partial-updates/) — [H]

**Part 4 — Collections at scale**

- [Ch8. Filtering, projection & pagination](/docs/08-filtering-projection-pagination/) — [H]
- [Ch9. Sub-resources](/docs/09-sub-resources/) — [C+H]

**Part 5 — Asynchronous work & jobs**

- [Ch10. Asynchronous & long-running operations](/docs/10-async-long-running-operations/) — [H]
- [Ch11. Rerunnable jobs](/docs/11-rerunnable-jobs/) — [H]

**Part 6 — Evolution & lifecycle**

- [Ch12. HATEOAS](/docs/12-hateoas/) — [H]
- [Ch13. Soft deletion & GDPR purge](/docs/13-soft-deletion-gdpr-purge/) — [H]
- [Ch14. Versioning](/docs/14-versioning/) — [H]

**Part 7 — Large payloads & streaming**

- [Ch15. Large binary resources & Range requests](/docs/15-large-binary-resources-range/) — [H]
- [Ch16. Streaming deep-dive](/docs/16-streaming-deep-dive/) — [H]
- [Ch17. Cross-protocol choices](/docs/17-cross-protocol-choices/) — [C]

**Part 8 — Performance & transport**

- [Ch18. Back-end I/O concurrency](/docs/18-backend-io-concurrency/) — [H]
- [Ch19. REST over HTTP/2 & HTTP/3](/docs/19-http2-http3/) — [C+H]

**Part 9 — Multi-protocol contracts & framework deep-dives**

- [Ch20. OpenAPI in depth](/docs/20-openapi-in-depth/) — [H]
- [Ch21. Multi-protocol contracts](/docs/21-multi-protocol-contracts/) — [H]
- [Ch22. Quarkus REST in depth](/docs/22-quarkus-rest-in-depth/) — [H]
- [Ch23. FastAPI in depth](/docs/23-fastapi-in-depth/) — [H]

**Part 10 — Testing**

- [Ch24. Testing REST APIs](/docs/24-testing-rest-apis/) — [H]

**Part 11 — Running it: Docker → minikube → CRC**

- [Ch25. Local with Docker/Podman Compose](/docs/25-local-with-docker-compose/) — [H]
- [Ch26. Kubernetes on minikube](/docs/26-kubernetes-on-minikube/) — [H]
- [Appendix A. OpenShift Local (CRC)](/docs/99-appendix-a-openshift-crc/) — [H]

**Part 12 — Complete project**

- [Ch27. Complete project](/docs/27-complete-project/) — [H]

Chapters are authored in release increments (r01–r06); see the iteration plan
for what lands when. This page fills in as chapters are written.
