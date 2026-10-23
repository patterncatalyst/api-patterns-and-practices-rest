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

- [Ch0. Prerequisites & the Lab](../00-prerequisites-and-the-lab/): [H]

**Part 1: Foundations & the decision lens**

- [Ch1. APIs & patterns](../01-apis-and-patterns/): [C]
- [Ch2. The API decision framework](../02-api-decision-framework/): [C]

**Part 2: Designing resources with a contract**

- [Ch3. Designing around resources](../03-designing-around-resources/): [C]
- [Ch4. Contract-first with OpenAPI](../04-contract-first-openapi/): [H]
- [Ch5. HTTP methods & the idempotency matrix](../05-http-methods-idempotency/): [H]

**Part 3: HTTP semantics done right**

- [Ch6. Content negotiation & status codes](../06-content-negotiation-status-codes/): [H]
- [Ch7. Partial updates: JSON Patch vs Merge Patch](../07-partial-updates/): [H]

**Part 4: Collections at scale**

- [Ch8. Filtering, projection & pagination](../08-filtering-projection-pagination/): [H]
- [Ch9. Sub-resources](../09-sub-resources/): [C+H]

**Part 5: Asynchronous work & jobs**

- [Ch10. Asynchronous & long-running operations](../10-async-long-running-operations/): [H]
- [Ch11. Rerunnable jobs](../11-rerunnable-jobs/): [H]

**Part 6: Evolution & lifecycle**

- [Ch12. HATEOAS](../12-hateoas/): [H]
- [Ch13. Soft deletion & GDPR purge](../13-soft-deletion-gdpr-purge/): [H]
- [Ch14. Versioning](../14-versioning/): [H]

**Part 7: Large payloads & streaming**

- [Ch15. Large binary resources & Range requests](../15-large-binary-resources-range/): [H]
- [Ch16. Streaming deep-dive](../16-streaming-deep-dive/): [H]
- [Ch17. Cross-protocol choices](../17-cross-protocol-choices/): [C]

**Part 8: Performance & transport**

- [Ch18. Back-end I/O concurrency](../18-backend-io-concurrency/): [H]
- [Ch19. REST over HTTP/2 & HTTP/3](../19-http2-http3/): [C+H]

**Part 9: Multi-protocol contracts & framework deep-dives**

- [Ch20. OpenAPI in depth](../20-openapi-in-depth/): [H]
- [Ch21. Multi-protocol contracts](../21-multi-protocol-contracts/): [H]
- [Ch22. Quarkus REST in depth](../22-quarkus-rest-in-depth/): [H]
- [Ch23. FastAPI in depth](../23-fastapi-in-depth/): [H]

**Part 10: Testing**

- [Ch24. Testing REST APIs](../24-testing-rest-apis/): [H]

**Part 11: Running it: Docker → minikube → CRC**

- [Ch25. Local with Docker/Podman Compose](../25-local-with-docker-compose/): [H]
- [Ch26. Kubernetes on minikube](../26-kubernetes-on-minikube/): [H]
- [Appendix A. OpenShift Local (CRC)](../99-appendix-a-openshift-crc/): [H]

**Part 12: Complete project**

- [Ch27. Complete project](../27-complete-project/): [H]

Chapters are authored in release increments (r01–r06); see the iteration plan
for what lands when. This page fills in as chapters are written.
