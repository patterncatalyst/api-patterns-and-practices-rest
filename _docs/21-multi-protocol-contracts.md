---
title: "Multi-protocol contracts"
order: 21
part: "Multi-protocol contracts & framework deep-dives"
description: "OpenAPI, AsyncAPI, CloudEvents and Arazzo compose around one shared JSON Schema, with Apicurio Registry and OpenMetadata as the governance tier behind that reuse."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Reuse one JSON Schema's `$defs` (`Booking`, `BookingEvent`) across OpenAPI, AsyncAPI and CloudEvents contracts via `$ref`.
- Build a CloudEvents envelope (`specversion`, `type`, `subject`, `data`) around a schema-validated payload.
- Document a multi-step business outcome with an Arazzo workflow (`bookAndConfirm`) that chains `operationId`s.
- Tell an artifact registry (Apicurio, xRegistry) from a data catalog (OpenMetadata) by the question each answers.
- Decide when a service needs a second contract language beyond OpenAPI.

## Why this matters

The service that answers `POST /bookings` synchronously also tells billing, notifications and analytics, asynchronously, that a booking changed state. None of them call `GET /bookings/{id}` to find out. That second path is a promise to other teams as much as a status code is, and an unwritten one drifts the same way. Four specifications cover the contract surface: OpenAPI, AsyncAPI, CloudEvents and Arazzo. None replaces OpenAPI. They describe different axes of one domain, and they stay consistent only if their payloads share one schema.

{% include excalidraw.html file="21-multi-protocol-contracts" alt="A single shared JSON Schema feeds a synchronous REST path, where an OpenAPI endpoint and client exchange a Booking, and an asynchronous path, where a service emits a CloudEvents-enveloped BookingEvent to Kafka for a consumer. An Arazzo workflow spans booking, routing and tracking as one business process. A governance tier outside CI shows Apicurio Registry as the artifact registry beside OpenMetadata as a data catalog tracking schema history." caption="Figure 21.1: One schema, two protocol contracts, an Arazzo workflow across them, and a local-only governance tier." %}

## Four languages, four questions

| Specification | Question it answers | Artifact |
|---|---|---|
| OpenAPI | What does a client send and what comes back, on this connection? | `contracts/openapi/shipping-api.yaml` |
| AsyncAPI | What is published to which channel, regardless of who listens? | `contracts/asyncapi/shipping-events.yaml` |
| CloudEvents | What envelope lets a consumer identify an event it has never seen? | `contracts/cloudevents/booking-confirmed.example.json` |
| Arazzo | In what order must contracted operations be called for one outcome? | `contracts/arazzo/booking-workflow.yaml` |

**AsyncAPI** describes a broadcast: an unknown number of listeners, no response, and no guarantee that publisher and subscriber run at the same time. The contract names one channel, `shipping.bookings.lifecycle`, on a single-node KRaft Kafka broker, and one message, `BookingStateChanged`, whose `type` enum spans `confirmed`, `in_transit`, `delivered` and `cancelled`. The service publishes only the first transition; the contract is written for the whole lifecycle.

**CloudEvents** is the wrapper, not the channel or the payload. Its context attributes are `specversion`, `id`, `source`, `type` (reverse-DNS style), optional `subject`, `time` and `datacontenttype`; `data` is an open slot. Events here use structured mode: attributes and `data` travel as one JSON document, which needs no broker-specific header mapping.

**Arazzo** adds what OpenAPI can't: call order and data flow. OpenAPI lists operations in isolation and never says they must be called in sequence, with one response feeding the next request. The `bookAndConfirm` workflow chains `createBooking`, `requestConfirmation`, `getOperation` (polled until the long-running operation resolves) and `getBooking`. Each step names an `operationId` from the `shippingApi` source description, which points at `contracts/openapi/shipping-api.yaml`, instead of restating shapes. The booking service confirms on its own in the background and announces the result over Kafka; the workflow documents the poll-until-done sequence for a client that drives confirmation itself. Written down, the call order doesn't have to be reverse-engineered from a wiki diagram or five handlers' source.

## The spine: one schema, referenced from both sides

`contracts/schemas/shipping.schema.json` carries two `$defs` that matter here. `Booking` is what `GET /bookings/{id}` returns. `BookingEvent` is what a lifecycle event's `data` carries: `bookingId`, `status`, `previousStatus`, `origin`, `destination`, `occurredAt`. It is smaller than `Booking` because a state-change announcement needs enough for a subscriber to look up the rest.

`BookingEvent.origin` and `BookingEvent.destination` are the same `$defs/Location` reference that `Booking` uses. A renamed field or a new required property on `Location` propagates to the synchronous and asynchronous contracts without anyone editing two copies.

The OpenAPI document references `#/$defs/Booking`, `#/$defs/BookingRequest` and `#/$defs/Problem`. The AsyncAPI `BookingStateChanged` payload is a bare `$ref` to `#/$defs/BookingEvent`, with the same pointer syntax and resolution, because AsyncAPI schema objects are JSON Schema too. The `Booking` a REST client reads and the `BookingEvent` a Kafka consumer reads can't drift apart on shared fields, because each shared field is declared once. The build fails if either document stops referencing `shipping.schema.json`.

## One service, two paths

A booking service answers REST calls and publishes events from the same `Booking` row. If each path carries its own type definitions, the two agree until the first field change, then disagree silently. Both payloads derive from the shared schema instead, and the two paths are coupled by data, not by failure domain.

`POST /bookings` validates the request, creates a `Booking` in `PENDING` and answers `201 Created` with a `Location` header, as before. After the response is sent, off the request thread (`CompletableFuture.runAsync` on Quarkus, `BackgroundTasks` on FastAPI), the service sets the status to `CONFIRMED` and publishes a CloudEvents-enveloped `BookingEvent` to `shipping.bookings.lifecycle`. Both stacks build the envelope by hand, because the lesson is the envelope's shape rather than an SDK's convenience methods, to match `booking-confirmed.example.json` exactly: `source` is `/shipping/bookings`, `type` is `dev.patterncatalyst.shipping.booking.confirmed`, and `subject` is the booking id.

Each stack reaches Kafka through its idiomatic client. Quarkus injects an `Emitter<String>` bound to the `booking-events` channel of SmallRye Reactive Messaging. Python uses `confluent-kafka`, the librdkafka producer. Both wait for the broker ack with a bounded timeout (10 seconds). A failed publish is logged and swallowed, never returned as a 5xx for a response already sent: a Kafka outage degrades the event stream, not the REST API.

{% include codetabs.html langs="Quarkus|Python" %}

```java
Map<String, Object> envelope = new LinkedHashMap<>();
envelope.put("specversion", "1.0");
envelope.put("id", "evt_" + Ulid.generate());
envelope.put("source", "/shipping/bookings");
envelope.put("type", "dev.patterncatalyst.shipping.booking.confirmed");
envelope.put("subject", confirmed.id());
envelope.put("time", occurredAt);
envelope.put("datacontenttype", "application/json");
envelope.put("data", data); // data = #/$defs/BookingEvent

String json = mapper.writeValueAsString(envelope);
emitter.send(json).toCompletableFuture().get(10, TimeUnit.SECONDS);
```

```python
envelope = {
    "specversion": "1.0",
    "id": f"evt_{generate_ulid()}",
    "source": "/shipping/bookings",
    "type": "dev.patterncatalyst.shipping.booking.confirmed",
    "subject": confirmed.id,
    "time": occurred_at,
    "datacontenttype": "application/json",
    "data": data.model_dump(mode="json", exclude_none=True),  # #/$defs/BookingEvent
}
payload = json.dumps(envelope).encode("utf-8")

producer = _get_producer()
producer.produce(TOPIC, value=payload)
remaining = producer.flush(10)
```

The envelope and the payload are validated separately. CloudEvents guarantees the envelope is legible and says nothing about whether `data` is correct, so a `status` outside the `BookingStatus` enum passes the envelope check and fails the `BookingEvent` check, with the offending value named.

## Governance tier: a registry and a catalog answer different questions

Inside one repository a grep enforces schema reuse. Once a consumer without a checkout needs to discover and resolve contracts, a **registry** is needed. When a team needs the history of a schema, a **catalog** is. Both run locally behind opt-in compose profiles that `verify.sh` never touches.

| | Apicurio Registry | OpenMetadata |
|---|---|---|
| Kind | Artifact registry (xRegistry touchpoint) | Data catalog, not an xRegistry implementation |
| Answers | What does this artifact look like now, by coordinate? | What did it look like, when did it change, what is the diff? |
| Footprint | One container, embedded H2, healthy in about 15 seconds | MySQL, Elasticsearch, a migration job and a server with a 60 to 90 second warm-up |
| Start | `docker compose --profile registry up -d apicurio-registry` | The catalog profile in the README |

Publishing the shared schema, the OpenAPI document and the AsyncAPI document into a `shipping` group (artifact types `JSON`, `OPENAPI`, `ASYNCAPI`) returned `200` for all three. Listing the group returned all three, and resolving `shipping-schema` returned all 17 `$defs` intact.

In OpenMetadata, a `bookings` table whose columns mirror `#/$defs/Booking` comes back at version `0.1`. A `PATCH` adding a `requested_pickup` column produces version `0.2` with a structured `changeDescription`:

```json
"changeDescription": {
  "fieldsAdded": [{ "name": "columns", "newValue": "[{\"name\":\"requested_pickup\", ...}]" }],
  "previousVersion": 0.1
}
```

`GET /api/v1/tables/{id}/versions` returns both versions. That timeline is what a team needs when a downstream consumer breaks and the first question is what changed and when.

Both tools stay out of CI for weight and flakiness. Apicurio alone could run there, but OpenMetadata's multi-container bring-up would make an occasional slow run routinely flaky, for a capability the live REST, Kafka and CloudEvents path doesn't depend on.

## Decision rule

Start with OpenAPI alone and add a language when a second kind of promise exists.

| Add | When |
|---|---|
| AsyncAPI | Someone outside the service's own call graph needs to know what arrives on a topic and when it may change |
| CloudEvents | More than one event type or publisher needs an envelope a generic consumer can parse |
| Arazzo | An outcome depends on calling operations in order, with data flowing from one response into the next request |
| A registry | Consumers that can't check out this repository (an SDK pipeline, a portal, a partner) must resolve contracts |
| A catalog | More than one team owns parts of a shared schema and a disagreement needs a timeline |

Skip all four when OpenAPI already describes every promise anyone outside the team depends on.

> **🤖 Explore with your agent**
>
> "In `examples/21-multi-protocol-contracts`, add a `carrierId` field to `#/$defs/BookingEvent` in `contracts/schemas/shipping.schema.json`, populate it in the Quarkus `BookingEventPublisher` and the Python `events.py` envelope `data`, and update `contracts/cloudevents/booking-confirmed.example.json`. Then tell me which contracts reference `BookingEvent` and which should change with it."
>
> Check: `./verify.sh` passes.

## Build, run, observe

```bash
cd examples/21-multi-protocol-contracts && ./verify.sh
```

`verify.sh` confirms the OpenAPI and AsyncAPI documents both reference the shared schema and the Arazzo workflow is structurally sound. It then starts Kafka and both services, runs a `POST` and `GET` round trip on each stack, and consumes the event each one publishes within a 20-second bound, checking the envelope attributes and validating `data` against `#/$defs/BookingEvent`. It prints `PASS` when both stacks hold. The full output is in `examples/21-multi-protocol-contracts/README.md`.

- Change `status` in `BookingEventPublisher.java` to a value outside `BookingStatus`: the envelope check passes and the `data` check fails.

## For deeper coverage

- [AsyncAPI Specification](https://www.asyncapi.com/docs/reference/specification/latest): the channel and message contract behind `shipping-events.yaml`.
- [CloudEvents Specification](https://cloudevents.io/): the envelope attributes (`specversion`, `id`, `source`, `type`, `subject`).
- *Cloud Native Design Patterns*, event-driven (same series, the broader event-driven treatment behind the CloudEvents envelope).
- *Cloud Native Design Patterns*, api-registry (same series, the Apicurio and xRegistry governance question).
- *Cloud Native Design Patterns*, api-metadata (same series, the OpenMetadata catalog and lineage question).
