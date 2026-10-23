---
title: "Multi-protocol contracts"
order: 21
part: "Multi-protocol contracts & framework deep-dives"
description: "How OpenAPI, AsyncAPI, CloudEvents, and Arazzo compose around one domain through a single shared JSON Schema, with Apicurio Registry and OpenMetadata shown as the governance tier behind that schema reuse."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Reuse one JSON Schema's `$defs` (`Booking`, `BookingEvent`) across OpenAPI, AsyncAPI, and CloudEvents contracts via `$ref`.
- Build a CloudEvents envelope (`specversion`, `type`, `subject`, `data`) around a schema-validated payload.
- Document a multi-step business outcome with an Arazzo workflow (`bookAndConfirm`) that chains `operationId`s across responses.
- Distinguish an artifact registry (Apicurio/xRegistry) from a data catalog (OpenMetadata) by the question each answers.
- Decide, from the Chapter 2 axes, when a service needs a second contract language beyond OpenAPI.

## Why this matters

Every chapter so far has treated "the contract" as one document: `contracts/openapi/shipping-api.yaml`, describing the synchronous request/response shape a client sends and the server answers. That was never the whole shape of a real booking service. The same service that answers `POST /bookings` synchronously also tells the rest of the system, asynchronously, that a booking changed state: a billing system, a notification service, an analytics pipeline, none of which call `GET /bookings/{id}` to find out. That second path needs its own contract, because "what gets published, to which channel, in what shape" is as much a promise to other teams as "what status code this endpoint returns," and an unwritten promise drifts the same way an undocumented REST response does. This chapter covers the vocabulary for writing that second promise down, plus the two more that show up once a system has more than one call in its story: CloudEvents for the envelope an event travels in, and Arazzo for the multi-step sequence that ties several calls into one business outcome. None of the four replaces OpenAPI: each describes a different axis of the same domain, and the chapter's actual argument is that they compose around one piece of shared schema rather than multiplying into four unrelated vocabularies a reader has to reconcile by hand.

## Four languages, four different questions

OpenAPI answers "what does a client send, and what comes back, right now, on this connection." It is the vocabulary for the request/response exchanges this book has built since Chapter 4: a method, a path, a status code, a schema for the body. Reach for it whenever a client holds a connection open and waits for an answer: the synchronous REST path every chapter before this one has been about, and the default contract for any interaction shaped that way.

AsyncAPI answers a structurally different question: "what gets published, to which channel, and what does the message look like, independent of who's listening or when." A REST contract describes a conversation between exactly two parties, bounded by one request and one response. An event contract describes a broadcast with an unknown number of listeners, no response expected, and no guarantee the publisher and any subscriber are even running at the same time. `contracts/asyncapi/shipping-events.yaml` names one channel, `shipping.bookings.lifecycle`, backed by a single-node Kafka broker in KRaft mode, and one message type, `BookingStateChanged`, whose `type` enum spans the full lifecycle a booking can move through: `confirmed`, `in_transit`, `delivered`, `cancelled`. This chapter's example only drives the first of those four (a booking moves `PENDING` to `CONFIRMED` and stops there), but the channel and message contract are written for the whole lifecycle a production system would eventually publish, not just the one transition demonstrated end to end here.

CloudEvents answers a narrower, more mechanical question: "given that something is being published as an event, what does the envelope around it look like, so a consumer that has never seen this event type before can still tell what it's holding." It's not a channel contract and not a payload schema; it's the wrapper. Every CloudEvent carries a small, fixed set of context attributes: `specversion` (which CloudEvents version this is), `id` (unique per event), `source` (a URI-reference naming where it came from), `type` (a reverse-DNS-style string naming what kind of event this is), `subject` (optionally, which resource within that source it's about), `time`, and `datacontenttype` (the media type of whatever's inside `data`). `data` itself is just a slot: CloudEvents doesn't define what goes there, which is the hook this chapter's schema-reuse story depends on. This chapter's events travel structured-mode: the whole envelope, attributes and `data` together, as one JSON document on the wire (the simpler of CloudEvents' two transport modes, needing no broker-specific header mapping to carry the context attributes alongside the payload).

Arazzo answers a question none of the first three can: "in what order do several already-contracted operations have to be called to accomplish one business outcome." An OpenAPI document describes operations in isolation (`createBooking` exists, `requestConfirmation` exists, `getBooking` exists), but nothing in OpenAPI says a client has to call them in a particular sequence, pass output from one into the next, or retry one while polling for a state change. `contracts/arazzo/booking-workflow.yaml` names that sequence explicitly as a workflow called `bookAndConfirm`: create the booking, request its confirmation, poll the resulting long-running operation until it resolves, then fetch the now-confirmed booking. Each step references an `operationId` from `shippingApi` (the `sourceDescriptions` entry pointing at `contracts/openapi/shipping-api.yaml`) rather than restating shapes Arazzo would otherwise duplicate. Worth being precise here: the four operations strung together (`createBooking`, `requestConfirmation`, `getOperation`, `getBooking`) are the long-running-operations shape Chapter 10 built, sitting in the OpenAPI contract for a client that wants to drive confirmation through an explicit poll-until-done loop. This chapter's own Quarkus and Python services reach the same outcome a simpler way: a background task that flips the booking to `CONFIRMED` and publishes an event, with no polling endpoint to call. Both are real: Arazzo documents the sequence for a client that drives confirmation itself; this chapter's example has the server drive confirmation on its own and announce the result over Kafka. A workflow document is how a team writes down call order for operations that need one, so the next engineer doesn't reverse-engineer it from a wiki diagram or five handlers' source.

## The spine: one schema, `$ref`'d from both sides

None of the last three paragraphs would be more than four vocabularies sitting next to each other without something tying their payloads to the same definitions. That something is `contracts/schemas/shipping.schema.json`: the JSON Schema file this book has built out since Chapter 4, now carrying two `$defs` this chapter cares about: `Booking`, the shape a `GET /bookings/{id}` returns, and `BookingEvent`, the shape a lifecycle event's `data` carries. `BookingEvent` carries far fewer fields than `Booking` (`bookingId`, `status`, `previousStatus`, `origin`, `destination`, `occurredAt`) because an event announcing a state change doesn't need a booking's full cargo manifest and quote breakdown; it needs enough for a subscriber to know what happened and look the rest up if it cares. What matters is that `BookingEvent.origin` and `BookingEvent.destination` are the exact same `$defs/Location` reference `Booking.origin` and `Booking.destination` already use. A `Location` is a `Location` everywhere in this domain, one definition, so a field rename or a new required property on it propagates to every schema that references it, synchronous and asynchronous alike, without anyone touching two separate copies by hand.

`contracts/openapi/shipping-api.yaml` has `$ref`'d into this file since Chapter 4 (`#/$defs/Booking`, `#/$defs/BookingRequest`, `#/$defs/Problem`), keeping its schema objects pointed at one external source rather than inlining a copy. `contracts/asyncapi/shipping-events.yaml` does the identical thing for `#/$defs/BookingEvent`: the `BookingStateChanged` message's `payload` is a bare `$ref` into the same file, same JSON Pointer syntax, same resolution semantics, because AsyncAPI's schema objects are JSON Schema too, exactly the way Chapter 20 established OpenAPI's are. That's the central fact this chapter is built around: **the `Booking` a REST client reads back and the `BookingEvent` a Kafka consumer reads off `shipping.bookings.lifecycle` cannot drift apart on their shared fields**, because `origin`, `destination`, and every other field either type reuses is declared once and referenced from two protocol contracts that would otherwise have no reason to agree. `verify.sh` makes this a checked claim rather than a comment: Step 2 greps both documents for the literal string `shipping.schema.json`, failing the run if either stops `$ref`ing the shared file. "One schema, two protocol contracts" isn't an assertion a reader has to trust; it's grepped on every run.

## One service, two paths

The example this chapter documents (`examples/21-multi-protocol-contracts/`) is one booking service, built on both stacks, doing exactly what the spine above implies: answering REST synchronously and publishing events asynchronously, off the same underlying `Booking` row, with no duplicated type definitions in either path. `POST /bookings` behaves the way Chapter 4's version always has: the request is validated, a `Booking` is created in status `PENDING`, and the server answers immediately with `201 Created`, a `Location` header, and the `PENDING` booking body, validated against `#/$defs/Booking`. Nothing about that synchronous contract changes here.

What's new happens after that response has already gone out. Off the request thread (a `CompletableFuture.runAsync` on Quarkus, FastAPI's `BackgroundTasks` on Python), the service flips the booking's status to `CONFIRMED` and publishes a CloudEvents-enveloped `BookingEvent` to `shipping.bookings.lifecycle`. The envelope is built by hand in both stacks, because the point here is the shape of the envelope and its payload, not a CloudEvents SDK's convenience methods: `specversion: "1.0"`, a generated `id`, `source: "/shipping/bookings"`, `type: "dev.patterncatalyst.shipping.booking.confirmed"`, `subject` set to the booking's id, `time`, `datacontenttype: "application/json"`, and `data` carrying the `BookingEvent` payload (`bookingId`, the new `status`, the `previousStatus` it transitioned from, `origin`, `destination`, and `occurredAt`). That's the exact shape committed at `contracts/cloudevents/booking-confirmed.example.json`, reproduced byte-for-byte rather than approximated.

The two stacks reach Kafka through their idiomatic paths rather than a hand-rolled wire client. Quarkus uses SmallRye Reactive Messaging's Kafka connector: `BookingEventPublisher` injects an `Emitter<String>` bound to the `booking-events` channel and calls `emitter.send(json)`, blocking (bounded, 10-second timeout) until the broker acks. Python's `events.py` uses `confluent-kafka`, the librdkafka-backed producer this book reaches for: `producer.produce(TOPIC, value=payload)` followed by a bounded `producer.flush(10)`, the same "block until acked, bounded" shape, even though the libraries share nothing. Both publishers share one more property: a failed publish is logged and swallowed, never surfaced as a 5xx on the response already sent. The two paths are coupled by sharing the booking's data, not a failure domain: a Kafka outage degrades the event stream, not the REST API a caller is waiting on.

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

producer.produce(TOPIC, value=payload)
remaining = producer.flush(10)
```

`verify.sh` proves this end to end, not just that the code compiles. For each stack it runs the familiar `POST` → `Location` → `GET` round trip against `#/$defs/Booking`, then consumes from `shipping.bookings.lifecycle` with a bounded (20-second) `kafka-console-consumer.sh --from-beginning --max-messages N --timeout-ms 20000` run inside the broker container, filters for the CloudEvent whose `subject` matches the booking it just created, asserts the envelope carries `specversion`/`id`/`source`/`type`, then validates `data` against `#/$defs/BookingEvent` the same way every other response body in this book gets schema-checked. A missing event fails loudly inside that bounded window rather than hanging the gate forever: the same "bounded, not open-ended" discipline applied to every asynchronous wait since Chapter 10. The README's drift probe makes the payload-side failure mode concrete: corrupt `BookingEventPublisher.java`'s `status` field to a value outside the `BookingStatus` enum, and the envelope attributes still pass while `data` validation fails with the offending value named. CloudEvents guarantees the envelope is legible; it says nothing about whether what's inside is correct, which is why the envelope check and the `BookingEvent` schema check are two separate assertions.

{% include excalidraw.html file="21-multi-protocol-contracts" alt="A single shared JSON Schema feeds both a synchronous REST path, where an OpenAPI endpoint and client exchange a Booking, and an asynchronous event path, where a service emits a CloudEvents-enveloped BookingEvent to Kafka for a consumer; below that, an Arazzo workflow spans booking, routing, and tracking as one business process; at the bottom, a governance tier kept out of CI shows Apicurio Registry as the schema/artifact registry and xRegistry touchpoint beside OpenMetadata as a data catalog tracking schema and version history over time, explicitly not an xRegistry implementation." caption="Figure 21.1: One schema, two protocol contracts, an Arazzo workflow across them, and a local-only governance tier." %}

## Governance tier: a registry answers one question, a catalog answers another

Schema reuse inside this repository is enforceable with a grep, because every contract lives in one `contracts/` directory a CI job can read directly. That stops being true once contracts need publishing somewhere a consuming team can discover and resolve them without cloning this repository: the moment a schema/artifact **registry** becomes necessary, and a different moment again from when a **catalog** does. This chapter's example runs both, real and runnable, behind opt-in compose profiles `verify.sh` never touches, documented well enough in the README to reproduce by hand, the same "shown, not gated" treatment Chapter 19 gave HTTP/3.

Apicurio Registry is the **registry**, and specifically the **xRegistry** touchpoint: it answers "what are my artifacts, and how do I resolve one by coordinate, right now." `docker compose --profile registry up -d apicurio-registry` gets a registry with its own embedded H2 storage (no extra datastore to provision), healthy within about fifteen seconds. The README walks through publishing this chapter's three committed contracts into a `shipping` group: the shared schema, the OpenAPI document, and the AsyncAPI document, each posted with its own `artifactType` (`JSON`, `OPENAPI`, `ASYNCAPI`). Verified in that environment: all three came back `200` on publish, `GET /groups/shipping/artifacts` listed all three, and resolving `shipping-schema` back out (piped through `jq '.["$defs"] | keys'`) returned all 17 `$defs` intact, byte-identical to what was published. That round trip is the whole registry story: artifacts, groups, versions, content resolved by coordinate.

OpenMetadata is explicitly **not** an xRegistry implementation, a distinction that matters: it's a **data catalog**. A registry answers "what does this artifact look like right now." A catalog answers a question a registry structurally can't, "what did this used to look like, when did it change, what's the diff": version history and lineage, not just current content. The README walkthrough makes that concrete rather than asserting it: standing up OpenMetadata's full local stack (MySQL, Elasticsearch, a one-shot migration job, then the server) and logging in over its REST API, it creates a `DatabaseService` → `Database` → `DatabaseSchema` → `Table` named `bookings`, columns mirroring `#/$defs/Booking`'s fields. That table comes back at **version `0.1`**. It then simulates exactly the change a real connector run would detect (`PATCH`ing the table to add a `requested_pickup` column, mirroring `Booking.requestedPickup`), and the response comes back at **version `0.2`**, carrying a structured `changeDescription`:

```json
"changeDescription": {
  "fieldsAdded": [{ "name": "columns", "newValue": "[{\"name\":\"requested_pickup\", ...}]" }],
  "previousVersion": 0.1
}
```

`GET /api/v1/tables/{id}/versions` then returns **both** `0.1` and `0.2`, the later one carrying that exact diff. That's the catalog's job made visible: not "here is the current schema," which a registry already answers well, but "here is a timeline of how this schema changed, with a structured record of what was added between versions": the question a team asks when a downstream consumer breaks and the first thing anyone needs is *what changed and when*, not just what the shape is today.

Both tools stay behind compose profiles and out of the CI gate for the same two reasons: weight and flakiness. Apicurio alone is light enough to plausibly run in CI, but OpenMetadata's bring-up (two datastores, a migration chain, a Java server with a 60-to-90-second warm-up) is the kind of heavyweight, multi-container chain that turns an occasional slow CI run into a routinely flaky one, for a capability this chapter's integrative claim doesn't depend on. CI proves the live REST + Kafka + CloudEvents path, because that's the contract a broken deploy would violate; the registry and the catalog are proven once, locally, exactly like HTTP/3 in Chapter 19: real and runnable, never required for the gate to pass.

## Decision

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Start with OpenAPI alone, the way this book did through Chapter 19, and add a second contract language only when a second kind of promise exists to document. Add AsyncAPI the moment a service publishes to a channel other teams subscribe to independently of any request they made: the signal isn't "we use Kafka internally," it's "someone outside this service's own call graph needs to know what arrives on this topic and when it might change." Add CloudEvents specifically when more than one event type, or more than one publisher, needs a consistent envelope a generic consumer can parse without special-casing each producer; a single service publishing one event type to one topic that only its own team consumes can get away with an ad hoc JSON shape for a while, but that stops scaling the moment a second producer or a generic event-router enters the picture. Add Arazzo when a business outcome requires calling more than one operation in a specific order with data flowing from one response into the next request; not for every two-call sequence a client happens to use, but for the sequences the system's design depends on happening in that order, the way `bookAndConfirm` depends on a booking existing before its confirmation can be requested. A registry becomes worth running once contracts need to be resolved by a consumer that isn't this repository (a generated-SDK pipeline, a documentation portal, a partner team without checkout access to this codebase); a catalog becomes worth running once a team needs to answer "what changed and when" across a schema's history, not just see its current shape; typically once more than one team owns pieces of a shared schema's evolution and a disagreement needs a timeline to resolve, not just a diff against yesterday's copy. Skip all four, and skip the governance tier entirely, for a system where OpenAPI already describes every promise anyone outside the team depends on: adding contract languages nobody downstream needs just adds vocabulary a reader has to learn for no corresponding clarity gained.</p></div>

## For deeper coverage

- [AsyncAPI Specification](https://www.asyncapi.com/docs/reference/specification/latest): the channel/message contract behind `shipping-events.yaml`.
- [CloudEvents Specification](https://cloudevents.io/): the envelope attributes (`specversion`, `id`, `source`, `type`, `subject`) this chapter builds by hand.
- *Cloud Native Design Patterns*, event-driven (same series, the broader event-driven treatment this chapter's CloudEvents envelope draws on).
- *Cloud Native Design Patterns*, api-registry (same series, the Apicurio/xRegistry governance question).
- *Cloud Native Design Patterns*, api-metadata (same series, the OpenMetadata catalog/lineage question).
