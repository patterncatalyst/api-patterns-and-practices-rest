---
title: "Examples"
layout: plan
permalink: /examples/
description: "Every runnable example in this repo, mapped to the chapter it supports."
---

Every hands-on chapter in this site has a matching runnable example under
[`examples/`](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples)
in the repo. Most examples ship **both** a Quarkus (Java) and a FastAPI
(Python) implementation against the same OpenAPI contract; a few chapters are
single-stack by design (Ch22 is a Quarkus REST deep-dive, Ch23 is its FastAPI
counterpart), and the two deployment-tier examples (Ch26, Appendix A) deploy
the same pair of services onto a cluster instead of adding a third stack.

| Example | What it shows | Stacks | Chapter |
|---|---|---|---|
| [00-prerequisites](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/00-prerequisites) | Toolchain pin: Quarkus + FastAPI health checks over Docker Compose | Both | [Ch0]({{ '/docs/00-prerequisites-and-the-lab/' | relative_url }}) |
| [04-contract-first](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/04-contract-first) | Contract-first anchor: shared OpenAPI/JSON Schema booking resource | Both | [Ch4]({{ '/docs/04-contract-first-openapi/' | relative_url }}) |
| [05-http-methods-idempotency](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/05-http-methods-idempotency) | HTTP methods & the idempotency matrix | Both | [Ch5]({{ '/docs/05-http-methods-idempotency/' | relative_url }}) |
| [06-content-negotiation](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/06-content-negotiation) | Content negotiation & status codes | Both | [Ch6]({{ '/docs/06-content-negotiation-status-codes/' | relative_url }}) |
| [07-partial-updates](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/07-partial-updates) | Partial updates: JSON Merge Patch vs. JSON Patch | Both | [Ch7]({{ '/docs/07-partial-updates/' | relative_url }}) |
| [08-pagination](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/08-pagination) | Filtering, projection & pagination | Both | [Ch8]({{ '/docs/08-filtering-projection-pagination/' | relative_url }}) |
| [10-async-operations](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/10-async-operations) | Async / long-running operations | Both | [Ch10]({{ '/docs/10-async-long-running-operations/' | relative_url }}) |
| [11-rerunnable-jobs](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/11-rerunnable-jobs) | Rerunnable, server-driven scheduled jobs | Both | [Ch11]({{ '/docs/11-rerunnable-jobs/' | relative_url }}) |
| [12-hateoas](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/12-hateoas) | HATEOAS: state-dependent `_links` | Both | [Ch12]({{ '/docs/12-hateoas/' | relative_url }}) |
| [13-soft-delete-purge](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/13-soft-delete-purge) | Soft deletion vs. GDPR purge | Both | [Ch13]({{ '/docs/13-soft-deletion-gdpr-purge/' | relative_url }}) |
| [14-versioning](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/14-versioning) | API versioning strategies | Both | [Ch14]({{ '/docs/14-versioning/' | relative_url }}) |
| [15-range-requests](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/15-range-requests) | Large binary resources & Range requests | Both | [Ch15]({{ '/docs/15-large-binary-resources-range/' | relative_url }}) |
| [16-streaming](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/16-streaming) | Three ways to stream a sequence of values incrementally | Both | [Ch16]({{ '/docs/16-streaming-deep-dive/' | relative_url }}) |
| [18-concurrency](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/18-concurrency) | Back-end I/O concurrency against a slow downstream dependency | Both | [Ch18]({{ '/docs/18-backend-io-concurrency/' | relative_url }}) |
| [19-http2-http3](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/19-http2-http3) | REST over HTTP/2 & HTTP/3 | Both | [Ch19]({{ '/docs/19-http2-http3/' | relative_url }}) |
| [20-openapi-depth](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/20-openapi-depth) | OpenAPI 3.1 in depth: JSON Schema-native components | Both | [Ch20]({{ '/docs/20-openapi-in-depth/' | relative_url }}) |
| [21-multi-protocol-contracts](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/21-multi-protocol-contracts) | Multi-protocol contracts: REST + events, one schema | Both | [Ch21]({{ '/docs/21-multi-protocol-contracts/' | relative_url }}) |
| [22-quarkus-rest-depth](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/22-quarkus-rest-depth) | Quarkus REST's build-time, zero-reflection parameter model | Quarkus only | [Ch22]({{ '/docs/22-quarkus-rest-in-depth/' | relative_url }}) |
| [23-fastapi-depth](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/23-fastapi-depth) | FastAPI's parameter model, the Quarkus deep-dive's corollary | FastAPI only | [Ch23]({{ '/docs/23-fastapi-in-depth/' | relative_url }}) |
| [24-testing](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/24-testing) | The test pyramid for the booking create/read surface | Both | [Ch24]({{ '/docs/24-testing-rest-apis/' | relative_url }}) |
| [25-local-with-docker-compose](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/25-local-with-docker-compose) | Full local dev substrate, with an OTel trace end to end | Both | [Ch25]({{ '/docs/25-local-with-docker-compose/' | relative_url }}) |
| [26-minikube](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/26-minikube) | The same two booking services on a minikube deployment tier | Both | [Ch26]({{ '/docs/26-kubernetes-on-minikube/' | relative_url }}) |
| [27-complete-project](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/27-complete-project) | One booking service assembling every prior chapter's pattern | Both | [Ch27]({{ '/docs/27-complete-project/' | relative_url }}) |
| [99-appendix-a-openshift-crc](https://github.com/{{ site.github_username }}/{{ site.github_repo }}/tree/main/examples/99-appendix-a-openshift-crc) | The same two booking services on OpenShift Local (CRC) | Both | [Appendix A]({{ '/docs/99-appendix-a-openshift-crc/' | relative_url }}) |

## Running an example

Each directory is self-contained: a `README.md`, a `compose.yaml` (or
`k8s/` / `helm/` for the two deployment-tier examples), and a `verify.sh` (or
`run-minikube.sh` / `run-crc.sh`) that proves it against the shared
`contracts/openapi/shipping-api.yaml`.

```bash
cd examples/04-contract-first
./verify.sh
```

See [Prerequisites & the Lab]({{ '/docs/00-prerequisites-and-the-lab/' | relative_url }}) for the full toolchain setup.
