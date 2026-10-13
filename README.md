# API Patterns and Practices: REST

Designing **REST APIs** well, with runnable examples in **Quarkus** and
**Python/FastAPI** against one OpenAPI contract — a chapter-based Jekyll site plus a
companion conference deck, in the `lgtm` house style.

**Live site:** https://patterncatalyst.github.io/api-patterns-and-practices-rest/

First of four standalone per-style sites split out of the *Cloud Native APIs*
project (REST → [gRPC](https://github.com/patterncatalyst/api-patterns-and-practices-grpc)
→ GraphQL → WebSockets). Quarkus + Python only.

## What's here

- **27 chapters + an OpenShift Local (CRC) appendix**, across 12 parts — from resource
  design and HTTP semantics through pagination, async operations, HATEOAS, versioning,
  streaming and large payloads, backend concurrency, HTTP/2–3, multi-protocol contracts
  (OpenAPI + AsyncAPI + CloudEvents + Arazzo), framework deep-dives, and testing.
- **Both stacks, first-class:** every hands-on chapter ships a Quarkus **and** a
  Python/FastAPI example against the **same** OpenAPI contract.
- **Contract-first:** `contracts/` is the single source of truth. CI validates both
  stacks against it — a response that violates the schema fails the build.
- **Behavioral verification:** each example's `verify.sh` asserts response *semantics*
  against the contract, not just a status code.
- **Three tiers:** Docker Compose → minikube (Kubernetes) → CRC (OpenShift Local).
- **Three decks:** a 100-level REST concepts deck plus 201 Quarkus and 201 Python
  implementation decks (`presentation/`).

## Domain

The canonical **shipping / cargo booking** domain used across patterncatalyst
material: `Booking` (the aggregate root), `Cargo`, `Location` (UN/LOCODE), `Route`,
`Operation`, and `Money` as a decimal string. See `_plans/domain-glossary.md`. The
gRPC sibling continues the same story — gRPC is the internal routing/tracking service
this REST booking service calls.

## Build locally

```bash
bundle install
bundle exec jekyll serve --baseurl ""
# → http://localhost:4000
```

Run an example's behavioral check (Docker Compose, both stacks):

```bash
bash examples/04-contract-first/verify.sh
```

## Layout

| Path | What |
|---|---|
| `_docs/` | The 27 chapters + appendix (Markdown). |
| `contracts/` | OpenAPI + AsyncAPI + shared JSON Schema + CloudEvents + Arazzo — the source of truth. |
| `examples/` | One runnable example per hands-on chapter, Quarkus + Python, each with `verify.sh`. |
| `presentation/` | The three `.pptx` deck builders. |
| `_plans/` | Iteration plan, coverage matrix, domain glossary. |
| `scripts/` | Static validation, diagram generation, word-count gate. |

## Licence

MIT — prose and code.
