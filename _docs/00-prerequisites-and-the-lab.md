---
title: "Prerequisites & the Lab"
order: 0
part: "Prerequisites & the Lab"
description: "Set up the contract-first lab: the Quarkus and FastAPI toolchains, the Docker Compose stack with LGTM observability, and the shipping and cargo domain you'll build against."
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

Every hands-on chapter gives you a running example in two languages against one contract. That only works if the plumbing is boring: the container toolchain the examples build with, the Compose stack that boots them side by side, and the shipping and cargo domain every resource, status code and diagram refers to. Get the stack booting, answering health checks and tearing down cleanly now, and you never debug it once the API design starts.

## What the lab needs

The only host requirement is a container engine with Compose v2: Docker Engine or Podman (`podman compose`). Both stacks build from inside a container on Red Hat UBI 10 base images, so the host needs no JDK and no Python interpreter. That matters for a contract-first API: two services agree on a wire format only if the artifact you run is the artifact CI validates, and host toolchain drift is the easiest way to break that.

Install the local toolchains if you want an IDE, breakpoints, or a faster loop than a container rebuild. For Quarkus that means JDK 25, Maven and the Quarkus CLI, all through [SDKMAN](https://sdkman.io):

```bash
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"
sdk install java 25-tem
sdk install maven 3.9.9
sdk install jbang && sdk install quarkus
```

For Python, [uv](https://docs.astral.sh/uv/) replaces `pip`, `venv` and the interpreter manager. It installs Python 3.14, resolves dependencies and runs the project from a lockfile:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14
```

`docker compose up` runs every example without either one.

## Two stacks, one contract

Every hands-on chapter ships the same example on Quarkus and on FastAPI, both serving the identical OpenAPI contract. A pattern that reads clearly in only one language teaches the framework instead of the pattern. Seeing an idempotency rule, a pagination strategy or a HATEOAS link in a Jakarta REST resource and in a FastAPI path operation separates what is REST from what is one framework's spelling.

Quarkus runs in JVM mode (fast-jar packaging, not a native image), because a native build's compile time is a poor trade for an example you rebuild constantly. The `pom.xml` pins the current stable LTS release and Java 25:

```xml
<!-- examples/00-prerequisites/quarkus/pom.xml -->
<properties>
  <maven.compiler.release>25</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  <quarkus.platform.group-id>io.quarkus.platform</quarkus.platform.group-id>
  <quarkus.platform.artifact-id>quarkus-bom</quarkus.platform.artifact-id>
  <!-- Quarkus latest stable LTS (3.40.x, released Sept 2026). -->
  <quarkus.platform.version>3.40.1</quarkus.platform.version>
</properties>
```

FastAPI runs on Uvicorn under Python 3.14, with `uv` as the only dependency and interpreter manager:

```toml
# examples/00-prerequisites/python/pyproject.toml
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.32",
]
```

Both Containerfiles use the name `Containerfile`, not `Dockerfile`, to signal any OCI-compliant build tool; `docker build` reads either. The Quarkus build compiles against `ubi10/openjdk-25`, then copies the fast-jar layout into `ubi10/openjdk-25-runtime` so the final image carries no build tooling:

{% include codetabs.html langs="Quarkus|Python" %}

```dockerfile
# Boot skeleton: Quarkus, UBI 10, JVM mode (fast-jar), no native.
# Build: docker build -f Containerfile -t shipping-quarkus .
#
# Base image pins (re-check with `skopeo list-tags
# docker://registry.access.redhat.com/ubi10/openjdk-25`, confirm with
# `skopeo inspect`; bump deliberately):
#   registry.access.redhat.com/ubi10/openjdk-25:1.24-15
#   registry.access.redhat.com/ubi10/openjdk-25-runtime:1.24-15

# ── Stage 1: Build ──────────────────────────────────────────
FROM registry.access.redhat.com/ubi10/openjdk-25:1.24-15 AS build

WORKDIR /build
COPY pom.xml .
COPY src ./src

RUN mvn -B package -DskipTests -Dmaven.javadoc.skip=true -Dmaven.wagon.http.retryHandler.count=3 -Daether.connector.http.retryHandler.count=3

# ── Stage 2: Runtime (fast-jar) ─────────────────────────────
FROM registry.access.redhat.com/ubi10/openjdk-25-runtime:1.24-15

ENV LANGUAGE='en_US:en'

COPY --from=build --chown=185 /build/target/quarkus-app/lib/ /deployments/lib/
COPY --from=build --chown=185 /build/target/quarkus-app/*.jar /deployments/
COPY --from=build --chown=185 /build/target/quarkus-app/app/ /deployments/app/
COPY --from=build --chown=185 /build/target/quarkus-app/quarkus/ /deployments/quarkus/

EXPOSE 8080
USER 185

ENV JAVA_OPTS_APPEND="-Dquarkus.http.host=0.0.0.0 -Djava.util.logging.manager=org.jboss.logmanager.LogManager"
ENV JAVA_APP_JAR="/deployments/quarkus-run.jar"

ENTRYPOINT [ "/opt/jboss/container/java/run/run-java.sh" ]
```
```dockerfile
# Boot skeleton: FastAPI, UBI 10, uv-managed.
# Build: docker build -f Containerfile -t shipping-python .
#
# UBI 10 publishes only the -minimal Python image (no ubi10/python-312).
# Pin: registry.access.redhat.com/ubi10/python-314-minimal:10.2-1791464217
# Re-check with:
#   skopeo list-tags docker://registry.access.redhat.com/ubi10/python-314-minimal
# and confirm with `skopeo inspect`. Bump deliberately.

# ── Stage 1: Build ──────────────────────────────────────────
FROM registry.access.redhat.com/ubi10/python-314-minimal:10.2-1791464217 AS build

# The image runs as UID 1001; the build stage needs root to write /app.
# Build at the same path the runtime uses: a venv is not relocatable, its
# console scripts carry the absolute interpreter path.
USER 0
WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.24

COPY pyproject.toml ./
COPY app ./app

# No uv.lock committed yet for this boot skeleton (two pure-Python deps);
# --locked is adopted once the lockfile lands with the contract-first API build.
RUN uv sync --no-dev

# ── Stage 2: Runtime ────────────────────────────────────────
FROM registry.access.redhat.com/ubi10/python-314-minimal:10.2-1791464217

WORKDIR /app

COPY --from=build --chown=1001:0 /app/.venv /app/.venv
COPY --from=build --chown=1001:0 /app/app /app/app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000
USER 1001

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Both base-image pins are exact tags, not floating majors. Check them with `skopeo list-tags` and bump them as a reviewed change, never as a side effect of an unrelated rebuild. UBI 10 ships only a `-minimal` Python image, so the Python build installs `uv` with `pip` first. The image runs as UID `1001`, so the build stage switches to `USER 0` to write into `/app`. It builds the virtual environment at the exact path the runtime stage mounts it, because a venv embeds absolute interpreter paths in its console scripts and isn't relocatable.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>If you move a <code>uv</code>-built virtual environment to a different path between build and runtime stages, every entry-point script inside it breaks with a "no such file or directory" that names the build stage's interpreter path. Build and run at the same <code>WORKDIR</code>.</p></div>

## The lab topology

`compose.yaml` starts three services by default: `quarkus` on port 8080, `python` on port 8000, and `postgres:17-alpine` with a seeded `shipping` database. Neither application uses Postgres yet, but it's in the stack from the start so the topology only grows a schema later and never changes shape. Each service has a Docker healthcheck (`curl` for the apps, `pg_isready` for Postgres), so `verify.sh` and CI wait for "ready," not "container started."

A fourth service, `lgtm` (Grafana's all-in-one image bundling Loki, Grafana, Tempo and Mimir behind an OpenTelemetry Collector), sits behind the Compose profile `observability`, so plain `docker compose up` never starts it. Nothing emits telemetry until the deployment chapters, and a four-container stack watching silent services only slows first boot.

```bash
docker compose up --build                            # app stack only: quarkus, python, postgres
docker compose --profile observability up --build     # + Grafana LGTM on :3000
```

{% include excalidraw.html file="00-lab-topology" alt="The Compose lab topology: a Quarkus container and a FastAPI container both serving the same OpenAPI contract on their own ports, both backed by a shared Postgres container, with an optional LGTM observability lane gated behind a profile flag that is off by default, and CI shown schema-validating the live responses from both services against that one contract." caption="Figure 0.1: The lab: two stacks, one contract, optional LGTM, CI as the drift gate." %}

Two application containers answer the same contract, one datastore is shared, observability is opt-in, and CI sits outside the stack checking that both containers' live responses still match the schema. Later chapters grow what is inside `quarkus` and `python`, not this shape.

## The domain

Every example works against one domain: a company that books cargo between ports. The vocabulary is fixed here and reused verbatim in the contract, the code and every diagram.

- **Booking:** the aggregate root, a customer's request to move cargo from an origin to a destination.
- **Cargo:** one piece of goods under a booking, with a description, type, weight in kilograms, volume in cubic meters and a hazardous flag. It has no identity outside its booking.
- **Location:** a port or terminal identified by UN/LOCODE (`USNYC`, `NLRTM`, `SGSIN`), not a free-text name. It is cacheable reference data shared across bookings.
- **Route** and **Leg:** the planned sequence of legs that moves a booking's cargo.
- **Manifest:** the consolidated listing of everything aboard a voyage, later the large-binary and streaming example.
- **Operation:** a server-owned record of long-running work, returned by a `202` and polled for status.

A booking's **Money** amount is a decimal string, `{ "currency": "USD", "amount": "1250.00" }`, not a float. A float can't represent every two-decimal value exactly, and silent rounding drift in an invoice surfaces only when a reconciliation report doesn't balance. Every monetary value in the contract follows that rule.

The booking lifecycle is a finite-state machine, and it reappears as the mechanism behind several later patterns:

```
PENDING ──confirm──▶ CONFIRMED ──load──▶ IN_TRANSIT ──deliver──▶ DELIVERED
   │                     │
   └──────cancel─────────┴──────────────▶ CANCELLED
```

A booking is created `PENDING`, becomes `CONFIRMED` once accepted, `IN_TRANSIT` once loaded and `DELIVERED` on arrival. It can be `CANCELLED` from either of the first two states, never after. Hypermedia links expose this machine to clients: a `PENDING` booking offers `confirm` and `cancel`, a `DELIVERED` one offers neither. An asynchronous confirmation drives the first transition through a `202` and a poll loop, and an event stream emits a CloudEvent on every transition.

## Run it by hand

`examples/00-prerequisites/` has no bookings or cargo yet, only `GET /` and a health check on each service. Run the same checks by hand:

```bash
docker compose up --build
curl -s http://localhost:8080/q/health   # Quarkus liveness/readiness
curl -s http://localhost:8080/           # {"service":"shipping-quarkus","status":"up"}
curl -s http://localhost:8000/health     # FastAPI health
curl -s http://localhost:8000/           # {"service":"shipping-python","status":"up"}
docker compose down -v
```

If you installed the local toolchains, both services also run on the host without a container rebuild, which is the faster loop once you're editing code:

{% include codetabs.html langs="Quarkus|Python" %}

```bash
# Quarkus: live-coding mode, rebuilds on save
quarkus dev
```
```bash
# Python: reload on save
cd examples/00-prerequisites/python
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

`quarkus dev` recompiles and reloads changed classes on the next request. `uv run` executes `uvicorn` inside the project's managed environment, and `--reload` restarts it on save. Neither touches the Compose network. Once a database is wired in, run against a container-provided Postgres, or let `quarkus dev` start an ephemeral one with Dev Services.

## What every hands-on chapter provides

Each hands-on chapter has a runnable example under `examples/NN-name/` with a Quarkus and a Python implementation, a `verify.sh`, and a `compose.yaml` that boots with LGTM available but off. Once the contract exists, CI also validates both stacks' live responses against `contracts/openapi/shipping-api.yaml`, so "verified" means the two implementations agree with the contract and not just with each other.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Run against Compose when you want the environment CI validates: both stacks, Postgres and the full network. Switch to local dev (<code>quarkus dev</code> or <code>uv run --reload</code>) when you're editing one service and want a sub-second loop. The container is still what ships and what CI checks last.</p></div>

## Build, run, observe

```bash
cd examples/00-prerequisites && ./verify.sh
```

`verify.sh` brings both services up, waits for each health endpoint, expects HTTP `200` from both, prints `PASS` and tears the stack down. See `examples/00-prerequisites/README.md` for full output.

- Run plain `docker compose up --build`, then `docker compose ps`: three services, no `lgtm`, because the observability profile is off by default.
- Start with `--profile observability`: Grafana answers on `:3000` and the application endpoints are unchanged.

## For deeper coverage

- Sam Newman, *Building Microservices*, 2nd ed. (O'Reilly, 2021): independent service boundaries and why two differently-implemented stacks need one shared contract to avoid drift.
- [Docker Compose specification](https://docs.docker.com/reference/compose-file/): `profiles`, healthchecks, and the multi-service topology this lab's `compose.yaml` builds on.
- [Open Container Initiative: Image Format Specification](https://github.com/opencontainers/image-spec): the OCI convention behind naming a build file `Containerfile` rather than `Dockerfile`.
- Cloud Native Design Patterns, [Communications](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/02-communications.md): the companion book's treatment of inter-service communication styles this lab's two-stacks-one-contract setup exists to exercise.
