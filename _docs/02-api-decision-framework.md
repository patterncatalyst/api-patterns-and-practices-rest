---
title: "The API decision framework"
order: 2
part: "Foundations & the decision lens"
description: "The criteria axes for choosing a pattern, style, and transport: the lens applied in a Decision callout at the end of every chapter."
duration: "15 min read"
---

## Learning objectives

By the end of this chapter you can:

- Apply the seven decision axes (interaction shape, payload size & shape, latency & real-time need, cacheability, client diversity, evolution & versioning needs, operational constraints) to choose a pattern, style, and transport for a given interaction.
- Explain why forcing every interaction through one style produces a wrong design for at least one of four example interactions (booking creation, routing-confirmation polling, a live cargo-event feed, a customs webhook).
- Walk the booking-confirmation example through the axes to justify `202 Accepted` → poll → `303 See Other` over a blocking synchronous call.
- Recognize when an interaction should leave request/response altogether for a fire-and-forget event, such as notifying an unbounded set of downstream consumers.
- Write a Decision callout that places a chapter's own topic on these same seven axes.

## Why this matters

"Just use REST" and "just use gRPC" are wrong for the same reason: neither names the property of the interaction that makes it true. REST fits a browser fetching a booking by id because the interaction is a cacheable, resource-shaped request/response over a transport every corporate proxy understands. gRPC fits a routing engine calling a capacity-check service a thousand times a second because the interaction is latency-sensitive, strongly typed and server-to-server. Swap the two interactions and both answers invert.

The lens is a fixed set of axes you read off an interaction before picking its pattern, style and transport. Every later chapter closes with a short **Decision** callout that places its topic on these axes.

## Why one style fails

A shipping platform is not one interaction repeated at different URLs. Creating a booking, polling whether its routing finished, streaming a vessel's cargo events and pushing a webhook to a customs broker when a container clears inspection have four different shapes.

- Force routing confirmation through a synchronous call and the client blocks for the thirty seconds routing takes, or the API returns a premature `200`.
- Force the live cargo-event feed through polling and the client misses events between polls or hammers the server.
- Force the customs webhook through a client-initiated poll and a time-sensitive compliance event waits for the client to ask.

The fix is naming the property of each interaction that decides its style. An axis is a question about the interaction, not about the technology.

## The axes

| Axis | The question | Where it pushes |
|---|---|---|
| Interaction shape | One response, a sequence of values over time, or a signal nobody acknowledges in-line? | Request/response: REST, gRPC unary, GraphQL query. Streaming: Server-Sent Events, chunked transfer, WebSockets, gRPC streaming. Fire-and-forget: an event broker or webhook, not a REST call. |
| Payload size & shape | Few hundred bytes of JSON, tens of megabytes of binary, or a graph the client wants to project? | REST for small documents; `Range`, `HEAD` and chunked delivery for large ones. GraphQL for client-chosen shape. gRPC's Protocol Buffers for small, fixed-schema, high-frequency calls. |
| Latency & real-time need | Does correctness depend on a response inside a bound the caller can name? | An 80 ms lookup is fine over REST. A 5 ms correlation isn't: look at gRPC over HTTP/2 and whether HTTP/3 removes a bottleneck. |
| Cacheability | Is it read-heavy, idempotent, with the same request shape across many clients? | REST. A `GET` resource is cached and revalidated with `ETag` and `Cache-Control`. A GraphQL query over `POST` or a gRPC unary call has no such handle. |
| Client diversity | Who calls it: browsers, mobile apps and partners, or services your team owns? | Heterogeneous or external clients pull toward REST with an OpenAPI contract. Internal callers can afford generated stubs and shared `.proto` files. |
| Evolution & versioning | Does the shape change constantly, or do outside parties depend on it for years? | External consumers you can't upgrade in lockstep need REST's loose coupling and content negotiation. Services deployed together tolerate a strict typed contract. |
| Operational constraints | What does the network between caller and service allow? | Browsers don't expose the HTTP/2 trailer frames gRPC depends on, so they need a translating proxy. Firewalls pass plain HTTP and balk at WebSocket upgrades or binary protocols. A CDN caches REST by URL with no configuration. Infrastructure you don't control votes for REST over HTTP. |

{% include excalidraw.html file="02-decision-framework" alt="Seven labeled axes (interaction shape, payload size and shape, latency and real-time need, cacheability, client diversity, evolution and versioning needs, and operational constraints) each feeding into a central decision diamond that resolves to a chosen pattern, style, and transport such as REST, gRPC, GraphQL, WebSockets, or webhooks." caption="Figure 2.1: The decision axes, reused in every Decision callout that follows." %}

<div class="callout callout--warn"><p class="callout__title">Anti-pattern</p><p>Picking the style the team already knows and forcing every interaction through it is the same mistake as cargo-culting the newest one. Familiarity is not an axis. If none of the seven favor REST for an interaction, say so and reach for the style that fits.</p></div>

## A worked decision: confirming a booking

Should confirming a booking, which runs the routing engine and the capacity check, be a synchronous REST call, an asynchronous REST operation, or an event?

**Interaction shape.** Routing a multi-leg voyage against live capacity takes from one second to half a minute, too long to hold an HTTP connection. A plain `POST /bookings/{id}/confirmation` returning `200` with the confirmed booking is out.

**Payload, cacheability, latency.** Bodies are small, and a one-time state transition isn't worth caching. The caller can wait minutes in total as long as it isn't blocked the whole time, which points to decoupling acceptance from the result, not to a faster transport.

**Client diversity.** This decides it. Browsers, mobile apps and partner servers all already hold a REST relationship with this API.

**Evolution and operations.** Confirmation belongs to the same booking lifecycle as every other state transition, so staying on one contract avoids a second protocol. Whatever proxy lets these clients call `POST /bookings` lets them call this.

The axes land on REST, but the asynchronous kind: `POST /bookings/{id}/confirmation` returns `202 Accepted` with a `Location` header pointing at an `Operation`, the client polls it, and a `303 See Other` on completion redirects to the confirmed booking.

A second question hides behind the first. How do the warehouse system, the customs broker and the carrier's tracking feed learn the booking is confirmed? None asked for it, none is polling, and the number subscribed varies. Run interaction shape again: this is a fire-and-forget event, because the confirming service has no reason to know who is listening. An unbounded set of downstream consumers is the shape an event stream serves and a point-to-point REST call doesn't. The same state transition that produced `202`/poll/`303` for the caller who asked also emits a `BookingConfirmed` event that anything can subscribe to.

One transition, two correct answers, because two interactions were hiding inside one requirement. Name the interaction's shape, payload, latency need, cacheability, audience, lifecycle and network path first, and let the answers point at the style.

## The Decision callout

A Decision callout takes its topic, runs it against these seven axes and states in two or three sentences where it lands and why. It isn't a summary. It restates the conclusion in this shared vocabulary, so reading the callouts in sequence reconstructs the argument. When one says an interaction is "synchronous, resource-shaped, cache-friendly, and serves diverse clients," it invokes interaction shape, cacheability and client diversity by name.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>When the interaction is synchronous in the caller's mind, resource-shaped, cache-friendly and serves a diverse or external client population, REST wins outright. When the work can't finish inside one request/response cycle, REST still wins as the asynchronous operation pattern (202 → poll → 303), not a blocking call. When the requirement is notifying an unknown or unbounded set of downstream consumers rather than answering the caller who triggered the change, interaction shape says to leave request/response for an event stream, which composes with the REST contract instead of replacing it.</p></div>

> **🤖 Explore with your agent**
>
> "Using the seven decision axes, score `GET /bookings/{bookingId}`, `POST /bookings/{bookingId}/confirmation` and `GET /operations/{operationId}` from `contracts/openapi/shipping-api.yaml` in a table with one row per axis. Name the axis that decides each, and say which one interaction in the shipping domain should leave request/response for an event, and why."
>
> Check: each of the three endpoints is scored on all seven axes, and the answer names fire-and-forget as the shape for downstream notification, not another REST endpoint.

## For deeper coverage

- J. J. Geewax, *API Design Patterns* (Manning, 2021): a broader catalog of the trade-offs these axes compress into seven questions.
- Gough, Bryant & Auburn, *Mastering API Architecture* (O'Reilly, 2022): choosing between REST, gRPC, and GraphQL at the architecture level.
- Cloud Native Design Patterns, [Communications](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/02-communications.md): per-interaction style selection from the cloud-native side.
- Cloud Native Design Patterns, [Anti-patterns](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/13-anti-patterns.md): cargo-culting a single communication style.
