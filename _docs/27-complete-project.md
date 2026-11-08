---
title: "Complete project"
order: 27
part: "Complete project"
description: "One booking service on both stacks that assembles contract-first resources, pagination, HATEOAS, async operations, versioning, soft delete, streaming and multi-protocol contracts into a single resource."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Assemble contract-first create and read, keyset pagination, HATEOAS, async operations, media-type versioning, soft delete and purge, NDJSON streaming and CloudEvents over Kafka onto one `Booking` resource without the mechanics interfering.
- Keep a REST response and a Kafka event in sync against one shared JSON Schema (`#/$defs/Booking`, `#/$defs/BookingEvent`) instead of two maintained shapes.
- Validate an Arazzo workflow document (`contracts/arazzo/booking-workflow.yaml`) against the OpenAPI operations it sequences.
- Scale a `verify.sh` contract gate to ten composed assertions while keeping every asynchronous wait bounded.
- Decide which patterns belong in nearly every REST API and which are situational, by naming the failure each one prevents.

## Why this matters

Each pattern is easy to demonstrate on its own resource. The harder question is whether they still work when they happen to the same resource. A `_links` map has to stay correct once the booking can also be paginated, versioned, soft-deleted and streamed. A background worker that flips a booking to `CONFIRMED` has to agree with whatever else reads or writes that booking at the same moment.

The answer is one `Booking`, built on Quarkus and FastAPI, carrying every capability. The contract is the same `contracts/schemas/shipping.schema.json` the earlier examples extended. The new part is the assembly: ten mechanics, each already correct in isolation, now sharing one `BookingStore`, one HTTP surface and one Kafka topic. The claim is that they compose.

The topology stays small. `docker compose up --build` starts three services under one project name: a single-node Kafka broker in KRaft mode, Quarkus on host port 8106 and FastAPI on 8025. Both applications keep bookings in memory. A Postgres container would fit the Compose convention, but nothing here tests it, and a failed assertion should point at protocol logic, not at a database. The two applications never talk to each other. They share the contract each implements and the topic each publishes to.

## The capability tour

| Capability | Behavior on `Booking` |
|---|---|
| Contract-first create and read | `POST /bookings` validates a `BookingRequest`, creates a `Booking` in `PENDING` and answers `201 Created` with `Location`. `GET /bookings/{id}` reads it back. Both bodies validate against `#/$defs/Booking`. |
| Keyset pagination | `GET /bookings?limit=&cursor=` walks the collection by cursor, not offset. Enough bookings force a second page whose cursor differs from the first. |
| HATEOAS `_links` | Every `Booking` and `BookingCollection` carries `_links` driven by the lifecycle state machine. `PENDING` exposes `confirm` and `cancel`, `CONFIRMED` only `cancel`, and `IN_TRANSIT`, `DELIVERED` and `CANCELLED` only `self`. |
| Async confirmation | `POST /bookings/{id}/confirmation` returns `202 Accepted` with `Location: /operations/{opId}`. Polling returns `200` with `RUNNING` until a background worker completes (a scheduled executor on Quarkus, `asyncio.create_task` on Python), then `303 See Other` to the `CONFIRMED` booking. |
| Media-type versioning | `GET /bookings/{id}` honors `Accept`. `application/vnd.shipping.booking.v1+json` returns the frozen shape (`cargoDescription`, `price`) and `.v2+json` the current one (`cargo[]`, `quote`). |
| Soft delete and purge | `DELETE /bookings/{id}` returns `204` and hides the booking behind `404`. `?includeDeleted=true` still finds it as `CANCELLED` with `X-Audit-Deleted-At` and `X-Audit-Deleted-Reason`. `DELETE /bookings/{id}/purge` erases it, and the audit view then answers `404`. |
| NDJSON manifest | `GET /bookings/{id}/manifest/export` streams six `BookingEvent` lines, one about every 250 ms. On Quarkus, `application/x-ndjson` with a `String` return type needs the `NdjsonMessageBodyWriter` raw-bytes writer. |
| CloudEvents over Kafka | When a confirmation completes, the service publishes a CloudEvent to `shipping.bookings.lifecycle`: `specversion`, a generated `id`, `source`, `type`, `subject` (the booking id), `time`, `datacontenttype`, and a `data` payload validated against the shared schema. |

Each row reuses an established handler or store pattern, re-pointed at one aggregate. The new code is the glue that keeps them consistent. `OperationStore` calls `BookingEventPublisher` when a confirmation finishes, not when the request is accepted. `HateoasLinks` reflects the same state machine that `VersionMapper` and the soft-delete view respect. The manifest generator reuses the `BookingEvent` shape the Kafka publish sends.

The clearest handoff is the confirmation worker completing a booking and publishing its event in one step:

{% include codetabs.html langs="Quarkus|Python" %}

```java
private void completeConfirmation(String opId, BookingStore bookingStore) {
    OperationRecord record = operations.get(opId);
    if (record == null) {
        return;
    }
    synchronized (record) {
        Booking confirmed = bookingStore.confirm(record.bookingId);
        record.status.set(OperationStatus.SUCCEEDED);
        record.completedAt = nowUtc();
        record.resource = "/bookings/" + record.bookingId;
        if (confirmed != null && confirmed.status() == BookingStatus.CONFIRMED) {
            eventPublisher.publishConfirmed(confirmed, BookingStatus.PENDING);
        }
    }
}
```

```python
async def _complete_confirmation(op_id: str) -> None:
    await asyncio.sleep(CONFIRMATION_DELAY_SECONDS)
    record = _operations.get(op_id)
    if record is None:
        return
    confirmed = store.confirm(record.booking_id)
    record.status = OperationStatus.SUCCEEDED
    record.completed_at = _now_utc()
    record.resource = f"/bookings/{record.booking_id}"
    if confirmed is not None and confirmed.status == BookingStatus.CONFIRMED:
        events.publish_confirmed(confirmed, BookingStatus.PENDING)
```

The operation and the CloudEvent complete off the same `BookingStore.confirm()` call, which neither mechanic alone would need to get right.

{% include excalidraw.html file="27-complete-project" alt="A single Booking resource, on Quarkus and FastAPI, surrounded by every pattern in the series (contract-first create and read, keyset pagination, HATEOAS links, async confirmation, media-type versioning, soft delete and purge, an NDJSON manifest, and a background CloudEvents publish to Kafka) all reading and writing the one shared JSON Schema and the Arazzo workflow tying the request sequence together." caption="Figure 27.1: One Booking resource on both stacks with every pattern assembled around it." %}

## The shared-schema spine

`contracts/schemas/shipping.schema.json` ties the synchronous response to the asynchronous event. `#/$defs/Booking` is what `GET /bookings/{id}` validates against, and `#/$defs/BookingEvent` is what the CloudEvent's `data` validates against. Both reference the same `#/$defs/Location` for `origin` and `destination`, so a field added to a location reaches both representations without copying a type.

`contracts/openapi/shipping-api.yaml` and `contracts/asyncapi/shipping-events.yaml` both `$ref` into that file instead of inlining copies. The build fails if either stops naming `shipping.schema.json`. The `Booking` a REST caller reads and the `BookingEvent` a Kafka consumer reads can't drift on shared fields, because each field is declared once.

### The Arazzo workflow

`contracts/arazzo/booking-workflow.yaml` names the `bookAndConfirm` workflow: create the booking, request confirmation, poll the operation until it resolves, fetch the confirmed booking. That describes a client driving confirmation through `createBooking`, `requestConfirmation`, `getOperation` and `getBooking`.

The services reach the same outcome server-side: a background worker completes the confirmation and announces it over Kafka, with no polling client needed. Both are real. Arazzo documents the sequence for a caller that drives it, and the service publishes what happened for everyone else. `check_arazzo.py` runs among the static checks before any container starts and confirms that every step's `operationId` resolves against `shippingApi` and that the `sourceDescriptions` entry points back at the OpenAPI document.

## Deployment, tracing and testing

The Compose-to-minikube-to-OpenShift path is not repeated. Moving a container onto a Kubernetes `Service` or an OpenShift `Route` doesn't depend on how many capabilities it holds. The same Containerfiles, probes and `ConfigMap` and `Secret` wiring carry this `Booking` as they carried a narrower one.

Tracing isn't wired in either: the Compose tier already shows one `POST /bookings` producing a trace Tempo returns by a chosen id, and repeating it here would make a broad gate heavier without new coverage. The `lgtm` service is present behind `--profile observability` for pointing an exporter at while experimenting, and it's not part of the default `up` or the CI gate.

### Testing across the pyramid

`verify.sh` is the contract layer, scaled to ten assertions. Every response body is checked against its `#/$defs` entry, and every asynchronous wait is bounded:

| Wait | Bound |
|---|---|
| Confirmation operation poll | Twelve attempts |
| Kafka consumer | Twenty-second timeout, plus a non-empty-file guard, because the console consumer exits `0` on a silent timeout |
| NDJSON manifest | A minimum spread across per-line arrival times |

The spread check matters because a buffered export returns the right status, the right `Content-Type` and six valid `BookingEvent` lines, so every shape assertion passes. Only the per-line timing shows all six arrived in one burst instead of about 250 ms apart. Newman and kcat remain local-only end-to-end and load exercises against the running stack, because a correctness gate and a load run have different failure budgets.

### Repeatability

A ten-step flow over a shared Kafka topic can pass once and fail on the second run from leftover state. `verify.sh` ends with `docker compose down -v --remove-orphans`, and each Kafka consume uses a PID-suffixed consumer group so two runs in one CI matrix don't collide. Run `bash verify.sh` twice in a row: no container, network, volume or consumer group should survive, and the second run reads the same as the first.

## Which patterns to adopt

Name the failure a pattern prevents, then check whether your system can have it. If it can't, the pattern solves a future problem at a present cost in surface, documentation and learning.

| Pattern | Adopt it when |
|---|---|
| Contract-first request and response, a `Problem` body, pagination on any unbounded collection | Nearly always. Skipping them usually costs a rewrite later. |
| HATEOAS | A state machine complex enough that a client benefits from being told its options |
| Media-type versioning | More than one representation of a resource must coexist |
| Soft delete with a purge path | A legal retention or erasure requirement exists |
| NDJSON streaming | A payload is too large or too slow to buffer |
| Async operations | An operation runs long enough that a caller shouldn't hold a connection open |
| An event contract | A state change has a second audience beyond whoever asked for it |

## Build, run, observe

```bash
cd examples/27-complete-project && ./verify.sh
```

The script starts Kafka and both stacks with `docker compose` and drives one booking service through the full flow on each: create and read, pagination with an advancing cursor, HATEOAS links, async confirmation, versioning, soft delete and purge, the streamed manifest and the CloudEvent on Kafka. It ends in `PASS` for both stacks. Quarkus is on 8106 and FastAPI on 8025.

- Make the NDJSON export buffer its output: status, `Content-Type` and line count still pass, and the spread check fails.
- Point `shipping-events.yaml` at an inlined copy of `Booking`: the `shipping.schema.json` grep fails.
- Return the same cursor on the second page: the pagination assertion fails.

## For deeper coverage

- J. J. Geewax, *API Design Patterns* (Manning, 2021): the pattern catalog (pagination, long-running operations, soft delete) assembled here onto one resource.
- Arnaud Lauret, *The Design of Web APIs, Second Edition* (Manning, 2024): versioning and resource-design trade-offs at the scale of a complete API.
- Martin Kleppmann & Chris Riccomini, *Designing Data-Intensive Applications, Second Edition* (O'Reilly, 2026): keeping a synchronous response and an asynchronous event in sync against one schema.
- [CloudEvents specification](https://cloudevents.io/): the envelope the background Kafka publish conforms to.
