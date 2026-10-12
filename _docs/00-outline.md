---
title: "Outline"
order: 0
overview: true
part: "Prerequisites & the Lab"
description: "What this site covers and how it's organized — 27 chapters across 12 parts, both stacks against one contract."
---

This site teaches REST API design against a single OpenAPI 3.1 contract for a
shipping and cargo booking domain. Every hands-on chapter ships the same example
in **both Quarkus and Python/FastAPI**, and CI validates both stacks against the
contract so they never drift. The full arc is below; the build &amp; iteration
plan, coverage matrix and domain glossary (linked in the footer) carry the
detail.

Legend: **[H]** hands-on (runnable in both stacks) · **[C]** concept.

| Part | Chapters |
|---|---|
| **0 — Prerequisites & the Lab** | Ch0 Prerequisites, toolchain, Compose + LGTM, the shipping/cargo domain [H] |
| **1 — Foundations & the decision lens** | Ch1 APIs & patterns [C] · Ch2 The API decision framework [C] |
| **2 — Designing resources with a contract** | Ch3 Designing around resources [C] · Ch4 Contract-first with OpenAPI 3.1 [H] · Ch5 HTTP methods & idempotency [H] |
| **3 — HTTP semantics done right** | Ch6 Content negotiation & status codes [H] · Ch7 Partial updates: JSON Patch vs Merge Patch [H] |
| **4 — Collections at scale** | Ch8 Filtering, projection & pagination [H] · Ch9 Sub-resources [C+H] |
| **5 — Asynchronous work & jobs** | Ch10 Async / long-running operations [H] · Ch11 Rerunnable jobs [H] |
| **6 — Evolution & lifecycle** | Ch12 HATEOAS [H] · Ch13 Soft deletion & GDPR purge [H] · Ch14 Versioning [H] |
| **7 — Large payloads & streaming** | Ch15 Large binary resources & Range [H] · Ch16 Streaming deep-dive [H] · Ch17 Cross-protocol choices [C] |
| **8 — Performance & transport** | Ch18 Back-end I/O concurrency [H] · Ch19 REST over HTTP/2 & HTTP/3 [C+H] |
| **9 — Multi-protocol contracts & frameworks** | Ch20 OpenAPI 3.1 in depth [H] · Ch21 Multi-protocol contracts [H] · Ch22 Quarkus REST in depth [H] · Ch23 FastAPI in depth [H] |
| **10 — Testing** | Ch24 Testing REST APIs [H] |
| **11 — Running it** | Ch25 Docker/Podman Compose [H] · Ch26 Kubernetes on minikube [H] · Appendix A OpenShift Local (CRC) [H] |
| **12 — Complete project** | Ch27 The shipping/cargo booking API, end to end [H] |

Chapters are authored in release increments (r01–r06); see the iteration plan
for what lands when. This page fills in as chapters are written.
