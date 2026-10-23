---
title: "Prerequisites & the Lab"
order: 0
part: "Prerequisites & the Lab"
description: "Set up the contract-first lab: the Quarkus and FastAPI toolchains, the Docker Compose stack with LGTM observability, and the shipping/cargo domain you'll build against."
duration: "25 min"
---

## Learning objectives

By the end of this chapter you can:

- Bring up the lab with `docker compose up --build`, and opt into the LGTM observability stack with `docker compose --profile observability up --build`.
- Explain why both stacks build inside a container from Red Hat UBI 10 base images instead of relying on a host-installed JDK or Python interpreter.
- Avoid the `uv`-built virtual environment relocation gotcha by building and running at the same `WORKDIR`.
- Trace the booking lifecycle state machine (`PENDING` → `CONFIRMED` → `IN_TRANSIT` → `DELIVERED`, with `CANCELLED` reachable from either of the first two).
- Run `verify.sh` to confirm both services answer their health checks and the stack tears down cleanly.

## Why this matters

Every chapter after this one hands you a running example in two languages against one contract. This chapter is where that becomes true on your machine: the container toolchain the examples build with, the Compose stack that boots them side by side, and the shipping/cargo domain every resource, every status code, and every diagram in this site refers back to. Nothing here touches the OpenAPI contract itself. That's Chapter 4. This chapter proves the two stacks boot, answer a health check, and tear back down cleanly, so the plumbing is never the thing you're debugging once the real API design starts.

## What the lab needs, and why

The one thing you need on the host, regardless of which stack you read first, is a container engine with Compose v2: Docker Desktop/Engine or Podman, either providing `docker compose` (Podman aliases or ships an equivalent `podman compose`). Every example in this site builds its Quarkus and Python images from inside a container, targeting Red Hat UBI 10 base images, so the host itself never needs a JDK or a Python interpreter installed to run `docker compose up`. That's a deliberate design point, not an accident: a contract-first API's whole premise is that two differently-implemented services agree on a wire format, and the easiest way to make that claim false is to let host-level toolchain drift leak into what each container actually ships. Build inside the container, and the artifact a reader runs is the same artifact CI validates.

Local, non-container development is still worth setting up if you intend to read code in an IDE, set breakpoints, or iterate faster than a container rebuild allows. For the Quarkus side that means JDK 25 and Maven, plus the Quarkus CLI for its `quarkus dev` live-coding mode; the simplest route to all three is [SDKMAN](https://sdkman.io), which manages JVM toolchain versions without touching your distribution's package manager:

```bash
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"
sdk install java 25-tem
sdk install maven 3.9.9
sdk install jbang && sdk install quarkus
```

For the Python side, [uv](https://docs.astral.sh/uv/) replaces `pip`, `venv`, and a separate interpreter manager with one tool that installs Python 3.14 itself, resolves dependencies, and runs the project from a lockfile:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14
```

Neither installation is required to run a single example end to end: `docker compose up` is sufficient for that on any machine with a container engine. But both pay off once you're past Chapter 0 and want to step through a request handler rather than just watch its output.

## Two stacks, one contract

This site teaches REST patterns as decisions, not as one framework's API, which is why every hands-on chapter ships the same example twice: once on Quarkus, once on FastAPI, both serving the identical OpenAPI contract from Chapter 4 onward. A pattern that only reads clearly in one language's idioms risks teaching the framework instead of the pattern underneath it. Seeing the same idempotency matrix, the same pagination strategy, or the same HATEOAS link expressed in a Jakarta REST resource and in a FastAPI path operation is what makes clear which parts are REST and which parts are just how one framework happens to spell it.

Quarkus runs in JVM mode here (fast-jar packaging, not a native image) because the native build's longer compile time is a poor trade for a tutorial you rebuild on every chapter. The example's `pom.xml` pins Quarkus to `3.40.1`, the current stable LTS release, and targets Java 25:

```xml
<!-- examples/00-prerequisites/quarkus/pom.xml -->
<properties>
  <maven.compiler.release>25</maven.compiler.release>
  <quarkus.platform.group-id>io.quarkus.platform</quarkus.platform.group-id>
  <quarkus.platform.artifact-id>quarkus-bom</quarkus.platform.artifact-id>
  <!-- Quarkus latest stable LTS (3.40.x, released Sept 2026). -->
  <quarkus.platform.version>3.40.1</quarkus.platform.version>
</properties>
```

FastAPI runs on Uvicorn under Python 3.14, with `uv` as the sole dependency and interpreter manager: no `pip`, Poetry, or conda alongside it for a project `uv` already owns. `pyproject.toml` pins the Python floor and the two runtime dependencies this skeleton needs:

```toml
# examples/00-prerequisites/python/pyproject.toml
[project]
name = "shipping-python"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.32",
]
```

Both stacks build from Red Hat UBI 10, and both Containerfiles are named `Containerfile` rather than `Dockerfile`, a naming convention from the OCI Image Format effort that signals "build with any OCI-compliant tool" rather than implying a Docker-specific syntax, even though `docker build` happily reads either name. The Quarkus side is a two-stage build: compile against `ubi10/openjdk-25`, then copy the resulting fast-jar layout into the smaller `ubi10/openjdk-25-runtime` image so the final container carries no build tooling:

{% include codetabs.html langs="Quarkus|Python" %}

```dockerfile
# examples/00-prerequisites/quarkus/Containerfile
FROM registry.access.redhat.com/ubi10/openjdk-25:1.24-15 AS build
WORKDIR /build
COPY pom.xml .
COPY src ./src
RUN mvn -B package -DskipTests -Dmaven.javadoc.skip=true

FROM registry.access.redhat.com/ubi10/openjdk-25-runtime:1.24-15
COPY --from=build --chown=185 /build/target/quarkus-app/lib/ /deployments/lib/
COPY --from=build --chown=185 /build/target/quarkus-app/*.jar /deployments/
ENTRYPOINT [ "/opt/jboss/container/java/run/run-java.sh" ]
```
```dockerfile
# examples/00-prerequisites/python/Containerfile
FROM registry.access.redhat.com/ubi10/python-314-minimal:10.2-1791464217 AS build
USER 0
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.24
COPY pyproject.toml ./
COPY app ./app
RUN uv sync --no-dev

FROM registry.access.redhat.com/ubi10/python-314-minimal:10.2-1791464217
COPY --from=build --chown=1001:0 /app/.venv /app/.venv
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Both pins (`openjdk-25:1.24-15` and `python-314-minimal:10.2-1791464217`) are exact tags, not floating majors; re-check them against `skopeo list-tags` and bump each one as a reviewed change, never as a side effect of an unrelated rebuild. UBI 10 ships only a `-minimal` Python image, not a full `ubi10/python-314`, which is why the Python Containerfile installs `uv` itself with `pip` before using it to resolve the rest. One UBI 10 gotcha costs a debugging session if you miss it: the image runs as UID `1001`, so the build stage switches to `USER 0` to write into `/app`, and it builds the virtual environment at the exact path the runtime stage mounts it at, because a Python venv embeds the absolute interpreter path into every console script it generates and isn't relocatable afterward.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>If you move a <code>uv</code>-built virtual environment to a different path between build and runtime stages, every entry-point script inside it breaks silently with a "no such file or directory" that names an interpreter path from the build stage, not the runtime one. Build and run at the same <code>WORKDIR</code>.</p></div>

## The lab topology

The Ch0 example's `compose.yaml` brings up three services by default: `quarkus` on port 8080, `python` on port 8000, and a `postgres:17-alpine` database seeded with a `shipping` database, user, and password. Neither application talks to Postgres yet (that wiring arrives with the contract-first build in Chapter 4), but the database is in the stack from day one so the topology you develop against never changes shape later, only grows a schema. Each service carries its own Docker healthcheck (`curl` against the HTTP endpoint for the two apps, `pg_isready` for Postgres), which is what lets `verify.sh` and CI poll for "actually ready," not just "container started."

A fourth service, `lgtm` (Grafana's all-in-one image bundling Loki, Grafana, Tempo, and Mimir behind one OpenTelemetry Collector), sits behind a Compose `profiles: ["observability"]` entry, which means plain `docker compose up` never starts it. Neither application exports telemetry at this stage of the site, so bringing up a four-container observability stack to watch two services that emit nothing would just slow down every chapter's first boot for no signal. The profile exists so Chapter 25 (and any chapter after it) can opt in with one flag once there's something worth tracing:

```bash
docker compose up --build                            # app stack only: quarkus, python, postgres
docker compose --profile observability up --build     # + Grafana LGTM on :3000
```

{% include excalidraw.html file="00-lab-topology" alt="The Compose lab topology: a Quarkus container and a FastAPI container both serving the same OpenAPI contract on their own ports, both backed by a shared Postgres container, with an optional LGTM observability lane gated behind a profile flag that is off by default, and CI shown schema-validating the live responses from both services against that one contract." caption="Figure 0.1: The lab: two stacks, one contract, optional LGTM, CI as the drift gate." %}

That figure is the shape every later hands-on chapter reuses: two application containers answering the same contract, one shared datastore, an observability lane you turn on when you need it, and CI sitting outside the stack asserting that both containers' live responses still match the schema. Nothing about that shape changes as the site adds resources, async flows, or streaming; only what's inside `quarkus` and `python` grows.

## The domain this site builds against

Every example from here forward works against one domain: a company that books cargo for shipment between ports. The vocabulary is fixed in `_plans/domain-glossary.md` and reused verbatim in the contract, the code, and every diagram, so a term introduced in one chapter means the same thing in all the others.

A **Booking** is the aggregate root: a customer's request to move cargo from an origin to a destination. It is the resource everything else in the domain hangs off of. A **Cargo** item is one piece of goods carried under a booking: a description, a type, a weight in kilograms, a volume in cubic metres, a hazardous flag. A booking owns one or more cargo items, and a cargo item has no meaning or identity outside the booking that requested it be shipped. A **Location** is a port or terminal, identified by its UN/LOCODE (`USNYC` for New York, `NLRTM` for Rotterdam, `SGSIN` for Singapore) rather than a free-text name, which is what later chapters reference as a cacheable, independently-addressable piece of reference data shared across thousands of bookings. Later parts add a **Route** (the planned sequence of **Leg**s moving a booking's cargo), a **Manifest** (the consolidated listing of everything aboard a voyage, which becomes the large-binary and streaming example in Part 7), and an **Operation** (a server-owned record of long-running work, returned by a `202` and polled for status in Chapter 10).

A booking's **Money** amount (the quote to carry its cargo) is represented as a decimal string (`{ "currency": "USD", "amount": "1250.00" }`) rather than a floating-point number, because a float can't represent every two-decimal currency value exactly, and silent rounding drift in a shipping invoice is the kind of bug nobody notices until a reconciliation report doesn't balance. Every monetary value anywhere in this site's contract follows that rule.

The booking lifecycle is a finite-state machine, and it's worth learning now because it reappears as the mechanism behind several later patterns, not just as domain trivia:

```
PENDING ──confirm──▶ CONFIRMED ──load──▶ IN_TRANSIT ──deliver──▶ DELIVERED
   │                     │
   └──────cancel─────────┴──────────────▶ CANCELLED
```

A booking is created `PENDING`, moves to `CONFIRMED` once accepted, `IN_TRANSIT` once loaded, and `DELIVERED` on arrival; it can be `CANCELLED` from either of the first two states, but never once it's moved beyond them. Chapter 12's HATEOAS treatment exposes exactly this FSM as response links: a `PENDING` booking's representation offers `confirm` and `cancel` links, a `DELIVERED` booking offers neither, so a client discovers legal next actions from the response instead of hardcoding which states permit which transitions. Chapter 10's async confirmation flow drives a booking through its first transition via a `202` and a poll loop, and Chapter 21's event stream emits a CloudEvent on every transition this diagram shows. One state machine, three different patterns built on top of it.

## Running the Ch0 example

The example under `examples/00-prerequisites/` doesn't touch the domain yet (no bookings, no cargo, just a `GET /` and a health check on each service) because its only job is proving the toolchain works before Chapter 4 puts a resource model behind it. Run it with the repository's standard per-chapter verification script.

`verify.sh` brings the app stack up with `docker compose`, polls `http://localhost:8080/q/health` and `http://localhost:8000/health` until each one answers (with a timeout, not an indefinite wait), asserts both return HTTP `200`, prints `PASS` with the status codes it saw, and tears the stack down afterward so no container is left running when it exits. That last step matters for a reason beyond tidiness: a chapter's verification is only meaningful if it proves the stack can come up from nothing and shut down cleanly every time, which is exactly what CI depends on when it runs this same script on every commit. A script that only checks "did the container process start" would pass even if the handler inside it threw on every request; polling the actual HTTP endpoint and asserting the status code is what makes `verify.sh` behavioral rather than cosmetic.

You can run the same checks manually, which is useful the first time through so you see each step rather than one summarized `PASS`:

```bash
docker compose up --build
curl -s http://localhost:8080/q/health   # Quarkus liveness/readiness
curl -s http://localhost:8080/           # {"service":"shipping-quarkus","status":"up"}
curl -s http://localhost:8000/health     # FastAPI health
curl -s http://localhost:8000/           # {"service":"shipping-python","status":"up"}
docker compose down -v
```

If you installed the local JDK and `uv` toolchains above, both services also run directly on the host without a container rebuild, which is the faster loop once you're iterating on code rather than proving the stack boots:

{% include codetabs.html langs="Quarkus|Python" %}

```bash
# Quarkus — live-coding mode, rebuilds on save
quarkus dev
```
```bash
# Python — reload on save
cd examples/00-prerequisites/python
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

`quarkus dev` starts Quarkus in its live-coding mode, which recompiles and reloads changed classes on the next incoming request rather than requiring a manual restart; `uv run` executes `uvicorn` inside the project's managed virtual environment without a separate `source .venv/bin/activate` step, and `--reload` gives FastAPI the equivalent watch-and-restart behavior. Neither local-dev path touches Postgres or the container network Compose sets up, which is fine for this chapter's health-check-only example. Once Chapter 4 wires in a database, local dev against a container-provided Postgres (or `quarkus dev`'s own Dev Services, which can launch an ephemeral Postgres automatically) becomes the more common pattern.

## What every later chapter assumes

From here on, every hands-on chapter in this site follows the same shape this one established: a runnable example under `examples/NN-chapter-name/` with both a Quarkus and a Python implementation, a `verify.sh` that asserts response bodies and status codes rather than just "the container started," and a `compose.yaml` that boots cleanly with LGTM available but off by default. Once the contract lands in Chapter 4, a CI job adds one more guarantee on top of each chapter's own `verify.sh`: it validates both stacks' live responses against `contracts/openapi/shipping-api.yaml` directly, so a chapter's "verified" status means the two independent implementations didn't just agree with each other, they agree with the contract that's supposed to govern both. A chapter's footer only flips to `Verification status: verified` once that CI check and both stacks' scripts are green, a status this chapter's own example will carry the moment Chapter 4 extends it with the first real resource.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Run against Compose when you want the exact environment CI validates (both stacks, Postgres, the full network topology), which is the right default for anything you'll compare against a later chapter's expected output. Switch to local dev (<code>quarkus dev</code> / <code>uv run --reload</code>) once you're editing one service's code and want a sub-second feedback loop; rebuilding a container image on every save is the wrong tool for that step, even though the container is still what ships and what CI checks last.</p></div>

## Build, run, observe

```bash
cd examples/00-prerequisites && ./verify.sh
```

`verify.sh` brings both services up with `docker compose`, polls each one's health endpoint until it answers, and asserts both return HTTP `200`. It prints `PASS` once both assertions hold and tears the stack down; see `examples/00-prerequisites/README.md` for the full run output.

## For deeper coverage

- Sam Newman, *Building Microservices*, 2nd ed. (O'Reilly, 2021): independent service boundaries and why two differently-implemented stacks need one shared contract to avoid drift.
- [Docker Compose specification](https://docs.docker.com/reference/compose-file/): `profiles`, healthchecks, and the multi-service topology this lab's `compose.yaml` builds on.
- [Open Container Initiative: Image Format Specification](https://github.com/opencontainers/image-spec): the OCI convention behind naming a build file `Containerfile` rather than `Dockerfile`.
- Cloud Native Design Patterns, [Communications](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/02-communications.md): the companion book's treatment of inter-service communication styles this lab's two-stacks-one-contract setup exists to exercise.
