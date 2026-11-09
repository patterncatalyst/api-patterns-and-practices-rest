---
title: "Local with Docker/Podman Compose"
order: 25
part: "Running it: Docker → minikube → CRC"
description: "Both stacks, Postgres and a single-container Grafana LGTM stack under Compose, with one booking's trace followed from the client's traceparent header to Tempo."
duration: "24 min"
---

## Learning objectives

By the end of this chapter you can:

- Wire `quarkus-opentelemetry` and a manual OpenTelemetry Python SDK pipeline to export spans over OTLP/gRPC and OTLP/HTTP to a shared collector.
- Promote `grafana/otel-lgtm` from an opt-in `profiles: ["observability"]` service to a default Compose dependency once tracing is the subject.
- Propagate a fixed W3C `traceparent` header across a request and confirm the trace lands in Tempo under that exact id.
- Write a bounded sleep-poll against Tempo's trace API instead of a single-shot or open-ended wait.
- Decide when to run the full LGTM stack locally by default and when to keep it behind an opt-in profile.

## Why this matters

A booking endpoint returns `201 Created` whether or not its spans ever leave the process. A wrong OTLP port, a typo in a scheme or a broken collector leaves the happy path green and the traces missing. Saying "both services emit spans" proves nothing.

The check that can fail is narrower: one request carries a trace id chosen in advance, and Tempo returns a trace under that exact id. That passes only if the application created the span, the exporter shipped it, the collector accepted it and Tempo stored it. The same Compose file is the first of three tiers for the booking service, followed by Kubernetes on minikube and OpenShift Local.

## The Compose topology

`compose.yaml` runs four services under one project name:

| Service | Image or build | Host ports |
|---|---|---|
| `quarkus` | built from `quarkus/` | 8105 |
| `python` | built from `python/` | 8024 |
| `postgres` | `postgres:17-alpine` | 5432 |
| `lgtm` | `docker.io/grafana/otel-lgtm:0.36.0` | 3000, 4317, 4318, 9090, 3100, 3200 |

Postgres is in the file because the datastore belongs in Compose from day one, but neither application persists bookings here. Adding persistence next to new instrumentation would mix two changes into one example.

`grafana/otel-lgtm` packages Grafana, Tempo, Loki, Mimir and an OpenTelemetry Collector in one image, with the Grafana data sources already pointing at the right internal ports. One container means no inter-service networking to debug, one healthcheck to wait on and one `docker compose down -v` to clean up. It gives up what separate containers buy a real deployment: independent scaling, upgrade cadence and failure domains. For local development and teaching that's the right trade.

Docker and Podman both run this file unchanged. It uses no extension fields or `depends_on` conditions that only one engine understands, so `podman compose up --build` brings up the same four services.

### Why `lgtm` is on by default here

Earlier examples keep `lgtm` behind `profiles: ["observability"]`, started with `docker compose --profile observability up`, because a four-container stack watching two services that emit nothing slows every first boot for no signal. Here the observability stack is the subject. `lgtm` has no `profiles:` key, both applications declare `depends_on: lgtm: condition: service_healthy`, and a plain `docker compose up` starts everything.

## OpenTelemetry instrumentation

Both stacks export to the `lgtm` collector over OTLP, instrumented at different altitudes.

Quarkus is declarative. `quarkus.application.name=shipping-quarkus` in `application.properties` becomes the exported `service.name` when no explicit OTel resource attribute overrides it, and three more properties set the endpoint, the protocol and the sampler. `quarkus-opentelemetry` then instruments every JAX-RS endpoint with no application code: an HTTP server span per request, tagged `http.route` and `http.request.method`, exported over OTLP/gRPC to port 4317.

Python is explicit, because nothing underneath FastAPI auto-configures tracing. `python/app/telemetry.py` builds the pipeline by hand: a `Resource` carrying `service.name` (default `shipping-python`, overridable with `OTEL_SERVICE_NAME`), a `TracerProvider` with `ALWAYS_ON` sampling, an `OTLPSpanExporter` to `http://lgtm:4318/v1/traces`, a `BatchSpanProcessor`, and a global `set_tracer_provider`. `FastAPIInstrumentor.instrument_app(app)` wraps the ASGI app with middleware that starts a span per request. `configure_tracing(app)` runs first in `app/main.py`, so instrumentation is live before the first request. Python uses OTLP/HTTP on 4318 and Quarkus uses gRPC on 4317, which is why Compose publishes both.

{% include codetabs.html langs="Quarkus|Python" %}

```properties
quarkus.otel.exporter.otlp.endpoint=http://lgtm:4317
quarkus.otel.exporter.otlp.protocol=grpc
quarkus.otel.traces.sampler=always_on
```

```python
_SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "shipping-python")
_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://lgtm:4318")


def configure_tracing(app: FastAPI) -> None:
    resource = Resource.create({"service.name": _SERVICE_NAME})
    provider = TracerProvider(resource=resource, sampler=ALWAYS_ON)
    exporter = OTLPSpanExporter(endpoint=f"{_OTLP_ENDPOINT}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
```

Both stacks hardcode `ALWAYS_ON` sampling. The check depends on one hand-picked trace id arriving, and a probabilistic sampler that dropped that request would make a pipeline bug and a coin flip indistinguishable. Production systems tune sampling to control cost and collector volume.

### Propagation

The W3C `traceparent` header is what makes a request continue a trace instead of starting one. `quarkus-opentelemetry` installs the default `tracecontext` propagator, which treats an inbound `traceparent` as the parent of the new server span, so the exported span inherits the caller's trace id. `FastAPIInstrumentor`'s ASGI middleware extracts the header the same way. Neither needs extra code.

## One request traced end to end

Searching Tempo for "something recent that looks right" could match the wrong request or poll forever. The lookup is deterministic and bounded instead.

For each stack, one `POST /bookings` carries a fixed 32-hex trace id in `traceparent`: `1111111111111111aaaaaaaaaaaaaaaa` for Quarkus and `2222222222222222bbbbbbbbbbbbbbbb` for Python. The response must be `201` with a `Location` header and a body valid against `#/$defs/Booking`. Then the script asks Tempo for `GET http://localhost:3200/api/traces/<that-exact-id>`. The id is in the URL before the request is sent, so there's no ambiguity about which trace is meant.

### A bounded poll

Both `BatchSpanProcessor`s flush on their own schedule, roughly every five seconds, and Tempo answers `404` for a trace it hasn't ingested. The script polls every two seconds (`TRACE_POLL_INTERVAL`) to a hard 30-second ceiling (`TRACE_POLL_TIMEOUT`). It succeeds on the first `200` and fails at the ceiling. The cap absorbs a slow flush on a loaded runner and never leaves a pipeline waiting indefinitely.

### Checking the trace

A `200` shows only that some trace exists under that id. The script walks the returned JSON with `jq`, handling both the `batches` and `resourceSpans` shapes that vary by exporter version, and requires three facts:

- a resource attribute `service.name` equals `shipping-quarkus` or `shipping-python`;
- a span attribute among `http.route`, `url.path` and `http.target` equals `/bookings`;
- a span attribute among `http.request.method` and `http.method` equals `POST`.

Before sending traffic, the script waits on `http://localhost:3200/ready`, separately from the container's Docker healthcheck against Grafana's `/api/health`. Grafana answering says nothing about Tempo having finished starting inside the same image, and early traffic would produce a timing-dependent failure unrelated to the instrumentation.

## Reading it in Grafana

Grafana is at `http://localhost:3000` with anonymous admin access (`GF_AUTH_ANONYMOUS_ENABLED=true`), so there's no login. In **Explore**, pick the **Tempo** data source, already provisioned by the image, and search by either trace id. The result is the `POST /bookings` server span with `http.route`, `http.request.method` and `http.response.status_code`. The Python trace also has `http send` and `http receive` spans that `FastAPIInstrumentor` nests under the server span; Quarkus produces none, because its server span sits closer to the socket.

Loki and Mimir run in the same image and are provisioned as Grafana data sources next to Tempo. Neither application emits structured logs or custom metrics over OTLP yet, so only the trace leg is exercised, but the same Explore pane is where a trace id would pivot to related log lines or a metrics dashboard.

{% include excalidraw.html file="25-local-with-docker-compose" alt="A Docker Compose topology with Quarkus and FastAPI containers both exporting OTLP traces to a single grafana/otel-lgtm container bundling Grafana, Tempo, Loki, and Mimir behind one OpenTelemetry Collector, Postgres present but unused, and verify.sh sending a traced POST with a fixed W3C traceparent header then polling Tempo's trace API by that exact id before asserting service name and route attributes on the returned span." caption="Figure 25.1: Both stacks export OTLP to one default LGTM container, and a fixed trace id ties the POST to a bounded Tempo lookup." %}

## When to run LGTM by default

Run the full stack by default when the thing you need to verify can only be shown by a trace, a log or a metric. Otherwise keep `lgtm` behind the opt-in profile.

| Subject | `lgtm` | Why |
|---|---|---|
| Resource model, pagination, schema evolution | Opt-in profile | A contract check proves it; a four-container stack slows every boot |
| A booking's path through two instrumented stacks and a collector | Default | Only querying the pipeline proves it |

Compose is the right place to start because the whole loop (build, run, trace, assert, tear down) stays on one machine with no cluster to provision. The same two images then move to minikube, onto Kubernetes primitives, and to OpenShift Local, which adds operators and its own security defaults. What changes is how much of the platform you stand up yourself.

## Build, run, observe

```bash
cd examples/25-local-with-docker-compose && ./verify.sh
```

The script starts both stacks, Postgres and `lgtm` with `docker compose`, posts a booking to each with a fixed `traceparent`, and polls Tempo until the trace shows the right service name and the `POST /bookings` route. It ends in `PASS`. Quarkus is on 8105, FastAPI on 8024 and Grafana on 3000.

- Add `OTEL_EXPORTER_OTLP_ENDPOINT=http://lgtm:9999` to the `python` service's environment in `compose.yaml`: Quarkus still passes, the Python `POST` still returns a valid `201`, and the Tempo poll for `2222222222222222bbbbbbbbbbbbbbbb` fails at the 30-second ceiling with a last code of `404`.
- Set `quarkus.otel.traces.sampler` to a ratio below 1: the fixed id is dropped on some runs and the check turns flaky.
- Remove `FastAPIInstrumentor.instrument_app(app)`: the Python service keeps serving and the trace never arrives.

## For deeper coverage

- Charity Majors, Liz Fong-Jones & George Miranda, *Observability Engineering* (O'Reilly, 2022): tracing as a first-class verification tool, not just a debugging aid.
- Cloud Native Design Patterns, "Observability" chapter: the broader pattern behind this single-trace check.
- [Quarkus OpenTelemetry guide](https://quarkus.io/guides/opentelemetry): the official reference for `quarkus-opentelemetry` configuration properties.
- [W3C Trace Context specification](https://www.w3.org/TR/trace-context/): the `traceparent` header format both stacks' default propagators read.
