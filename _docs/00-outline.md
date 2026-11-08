---
title: "Outline"
order: 0
overview: true
part: "Prerequisites & the Lab"
description: "What this site covers and how it's organized: 27 chapters across 12 parts, both stacks against one contract."
---

This site teaches REST API design against a single OpenAPI contract for a
shipping and cargo booking domain. Every hands-on chapter ships the same example
in **both Quarkus and Python/FastAPI**, and CI validates both stacks against the
contract so they never drift. The full arc is below; the build &amp; iteration
plan, coverage matrix and domain glossary (linked in the footer) carry the
detail.

Legend: each chapter below is tagged **[H]** hands-on (runnable in both stacks),
**[C]** concept, or **[C+H]** where a concept chapter also ships a runnable example.

**Part 0: Prerequisites & the Lab**

- [Chapter 0: Prerequisites & the Lab](../00-prerequisites-and-the-lab/): [H]

**Part 1: Foundations & the decision lens**

- [Chapter 1: APIs & patterns](../01-apis-and-patterns/): [C]
- [Chapter 2: The API decision framework](../02-api-decision-framework/): [C]

**Part 2: Designing resources with a contract**

- [Chapter 3: Designing around resources](../03-designing-around-resources/): [C]
- [Chapter 4: Contract-first with OpenAPI](../04-contract-first-openapi/): [H]
- [Chapter 5: HTTP methods & the idempotency matrix](../05-http-methods-idempotency/): [H]

**Part 3: HTTP semantics done right**

- [Chapter 6: Content negotiation & status codes](../06-content-negotiation-status-codes/): [H]
- [Chapter 7: Partial updates: JSON Patch vs Merge Patch](../07-partial-updates/): [H]

**Part 4: Collections at scale**

- [Chapter 8: Filtering, projection & pagination](../08-filtering-projection-pagination/): [H]
- [Chapter 9: Sub-resources](../09-sub-resources/): [C+H]

**Part 5: Asynchronous work & jobs**

- [Chapter 10: Asynchronous & long-running operations](../10-async-long-running-operations/): [H]
- [Chapter 11: Rerunnable jobs](../11-rerunnable-jobs/): [H]

**Part 6: Evolution & lifecycle**

- [Chapter 12: HATEOAS](../12-hateoas/): [H]
- [Chapter 13: Soft deletion & GDPR purge](../13-soft-deletion-gdpr-purge/): [H]
- [Chapter 14: Versioning](../14-versioning/): [H]

**Part 7: Large payloads & streaming**

- [Chapter 15: Large binary resources & Range requests](../15-large-binary-resources-range/): [H]
- [Chapter 16: Streaming deep-dive](../16-streaming-deep-dive/): [H]
- [Chapter 17: Cross-protocol choices](../17-cross-protocol-choices/): [C]

**Part 8: Performance & transport**

- [Chapter 18: Back-end I/O concurrency](../18-backend-io-concurrency/): [H]
- [Chapter 19: REST over HTTP/2 & HTTP/3](../19-http2-http3/): [C+H]

**Part 9: Multi-protocol contracts & framework deep-dives**

- [Chapter 20: OpenAPI in depth](../20-openapi-in-depth/): [H]
- [Chapter 21: Multi-protocol contracts](../21-multi-protocol-contracts/): [H]
- [Chapter 22: Quarkus REST in depth](../22-quarkus-rest-in-depth/): [H]
- [Chapter 23: FastAPI in depth](../23-fastapi-in-depth/): [H]

**Part 10: Testing**

- [Chapter 24: Testing REST APIs](../24-testing-rest-apis/): [H]

**Part 11: Running it: Docker → minikube → CRC**

- [Chapter 25: Local with Docker/Podman Compose](../25-local-with-docker-compose/): [H]
- [Chapter 26: Kubernetes on minikube](../26-kubernetes-on-minikube/): [H]
- [Appendix A. OpenShift Local (CRC)](../99-appendix-a-openshift-crc/): [H]

**Part 12: Complete project**

- [Chapter 27: Complete project](../27-complete-project/): [H]
