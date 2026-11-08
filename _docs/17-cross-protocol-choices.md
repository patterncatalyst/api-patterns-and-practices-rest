---
title: "Cross-protocol choices"
order: 17
part: "Large payloads & streaming"
description: "When to leave REST: how REST and SSE compare with WebSockets, webhooks, and gRPC for moving data, and which interaction shapes each one fits."
duration: "22 min"
---

## Learning objectives

By the end of this chapter you can:

- Compare REST+SSE, WebSockets, webhooks, and gRPC against the interaction-shape axes.
- Identify when a full-duplex `Upgrade: websocket` connection is justified over a one-directional SSE feed.
- Design a signed webhook (`X-Signature`, HMAC) with at-least-once delivery and fan-out.
- Recognize when gRPC's streaming RPC shapes (`stream CargoEvent`, `stream RouteProposal`) beat REST for service-to-service calls.
- Map an interaction shape to the right protocol with a lookup table.

## Why this matters

REST with `Range` requests carries large binary resources, and REST with SSE, NDJSON and chunked encoding carries continuous data. REST fits a wide range of interactions if you add the right header, status code or content type. It stops fitting when the interaction needs something HTTP request/response can't give.

Seven axes read an interaction's shape before anyone picks a technology: among them interaction shape, latency, payload shape, cacheability and client diversity. Four interactions on a shipping platform show the lens at work:

- A browser watching a booking's status change.
- A customs broker that must hear a container cleared inspection the moment it happens.
- A dispatcher watching a vessel's cargo events all day.
- A routing engine calling a capacity-check service a thousand times a second.

Four shapes, four different answers, and REST is the right one for one of them.

{% include excalidraw.html file="17-cross-protocol" alt="Four protocols compared side by side by direction, connection model, and best-fit use case: REST plus SSE shown as client-initiated request with optional one-directional server push over a short-lived HTTP connection for cacheable lookups and status watching; WebSockets shown as a full-duplex, stateful, long-lived connection for bidirectional low-latency conversation; webhooks shown as a server-initiated outbound POST to a client-owned endpoint with retry and signature verification for fire-and-forget events to offline receivers; gRPC shown as binary HTTP/2 request/response and streaming RPCs between service-to-service callers with generated contracts." caption="Figure 17.1: REST, WebSockets, webhooks, and gRPC by interaction shape." %}

## REST and its push ceiling

`GET /bookings/{id}` is request/response: one question, one answer. SSE adds a push tail. The server keeps the connection open and writes events, so a client sees `CONFIRMED`, `IN_TRANSIT`, `DELIVERED` without polling. NDJSON and chunked encoding stream a result as it is produced. All three are one client request followed by server output on one connection.

That structure is also the ceiling. The only way back to the server is to close the connection or open a new request. A dispatcher who wants to acknowledge an event, filter the stream or send a command needs a separate `POST`, with its own connection setup. If watching is the whole requirement, there's no problem: SSE is right because it doesn't try to be more than a push channel.

REST also brings what the rest of the toolchain already understands. Every proxy, CDN and firewall passes plain HTTP, a browser opens an `EventSource` without a library, and a `GET` is cacheable by URL. A public booking-status endpoint for browsers, mobile apps and partners needs a contract and nothing more. The next three interactions each break one of these assumptions.

## WebSockets: the client needs to talk back

A WebSocket starts as an HTTP request with an `Upgrade: websocket` handshake and then stops being HTTP. What remains is one full-duplex, stateful channel. Either side sends at any time, and the connection lives for the session, not for one exchange. A live chat between a shipper and a carrier's support desk has that shape: neither party is requesting from the other.

```
// Illustrative, not a running example
ws.send(JSON.stringify({ type: "message", text: "ETA on the NLRTM leg?" }));
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  // either side can arrive at any time, unprompted by a request
};
```

| Axis | Effect of choosing WebSockets |
|---|---|
| Interaction shape | Bidirectional, either side initiates. SSE has no channel for the client's half. |
| Latency | After the handshake, no new connection, TLS negotiation or per-message HTTP headers. |
| Cacheability | Gone. After the handshake there are no addressable requests to key a cache on. |
| Client diversity | Worse. A proxy that passes HTTP may refuse the `Upgrade`, and strict firewalls block it. |
| Operations | A long-lived stateful connection must stay pinned to one backend, which is harder to scale than independent requests. |

Chat justifies those costs because the two-way, low-latency conversation is the whole point. A status feed that is only watched does not, and SSE serves it at a fraction of the cost.

## Webhooks: push to an endpoint the client owns

A customs broker waiting for inspection clearance has no connection open, and the event happens on the platform's schedule. Polling `GET /bookings/{id}` every few seconds works and is wasteful: most polls return nothing new, the broker pays to ask constantly, and the lag is up to one poll interval.

A webhook inverts who initiates. The broker registers a URL on its own infrastructure. When the booking's customs status changes, the platform sends an outbound `POST`:

```json
POST https://broker.example.com/webhooks/shipping-events
Content-Type: application/json
X-Signature: sha256=4f0a...

{
  "event": "booking.customs_cleared",
  "bookingId": "bkg_01H9XZ...",
  "occurredAt": "2026-10-11T14:30:00Z"
}
```

The platform signals and moves on, with no connection held and no polling. Webhooks give up REST's cacheability and uniform interface for push to a party the server can't keep a connection to. They also carry three obligations a `GET` never had:

- **Fan-out.** One event may have several subscribers, such as the broker, the carrier and an audit log, and the platform delivers to all of them.
- **At-least-once delivery.** A `POST` to an endpoint that is down, slow or returning `500` is retried, so receivers must tolerate repeats. An idempotency key on the event, not the HTTP method, de-duplicates.
- **Signatures.** An endpoint that accepts unauthenticated `POST`s from the internet is open to anyone who finds the URL. An HMAC of the payload under a shared secret, sent in `X-Signature`, lets the receiver verify the sender.

Webhooks aren't REST. They're a convention over plain `POST`, and the convention has to supply what a cacheable `GET` provides by default.

## gRPC: caller and callee are both yours

The routing engine and the capacity-check service are deployed by the same team. There's no browser, no partner and no unknown client population, so client diversity, the axis that argues hardest for REST, drops out. The remaining axes argue against it: single-digit-millisecond round trips a thousand times over, small fixed-schema messages where JSON's self-describing text is overhead on every call, and streaming defined in the contract:

```protobuf
// Illustrative, not a running example
service CapacityCheck {
  rpc CheckCapacity(CapacityRequest) returns (CapacityReply);
  rpc StreamVesselEvents(VesselQuery) returns (stream CargoEvent);
  rpc NegotiateRoute(stream RouteProposal) returns (stream RouteCounter);
}
```

gRPC supports unary, client-streaming, server-streaming and bidirectional RPCs. Bidirectional streaming in the contract is something REST, SSE and webhooks don't offer. gRPC runs over HTTP/2, encodes messages as binary Protocol Buffers, and generates client and server stubs from the `.proto` file. That gives compiler-checked contracts and low per-message overhead. The costs:

- Payloads aren't readable on the wire. Debugging means decoding protobuf, not reading a response in a network tab.
- Browsers can't open a raw HTTP/2 connection with the trailers gRPC needs, so browser clients need gRPC-Web and a translating proxy.
- Proxies that pass REST without a thought often don't understand gRPC framing.

None of that matters between two services you deploy together. Check client diversity first, every time, before reaching for gRPC.

## Matching interaction shape to protocol

| Interaction shape | Example | Best fit | Why |
|---|---|---|---|
| Request/response, cacheable, diverse clients | Look up a booking by id | REST | Ubiquitous, cacheable by URL, no client tooling |
| Server push, one direction | Watch a booking's status | REST + SSE | SSE adds one-directional push without a new protocol |
| Bidirectional, low-latency, either side initiates | Live chat, shipper and support | WebSockets | Full-duplex and stateful |
| Fire-and-forget event to a party with no open connection | Notify a customs broker | Webhooks | Server-initiated `POST`, at-least-once, signed |
| High-frequency, low-latency, service to service, typed | Capacity check from a routing engine | gRPC | Binary encoding, generated stubs, native streaming RPCs |

Read the table from the left. The interaction shape is the input and the protocol is the output. The three non-REST rows leave REST only because an axis forced it: bidirectionality, an offline receiver, or a latency and ownership profile that removes REST's main advantage. REST stays the default for booking CRUD, cargo lookups, catalog queries and anything a browser or unknown third party calls.

## When to leave REST

| Signal | Stay or leave |
|---|---|
| Request/response or one-way push, cacheable, diverse or external clients | Stay on REST, with SSE, NDJSON or chunked encoding for continuous push |
| Bidirectional, low-latency, either side initiates | WebSockets |
| Fire-and-forget event, receiver has no open connection | Webhooks, with fan-out, retries and signatures budgeted up front |
| Both ends are services you own, and latency or streaming RPCs outweigh readable payloads and browser support | gRPC |

An interaction that doesn't fit request/response plus push is a signal to pick another tool, not a reason to add one more header.

> **🤖 Explore with your agent**
>
> "Review the shipping platform's API surface in contracts/ and examples/16-streaming/. For each of `GET /bookings/{id}`, `GET /bookings/{id}/events`, a customs-clearance notification and a routing-engine capacity check, name the interaction shape and pick REST, SSE, WebSockets, webhooks or gRPC with a one-line reason. Flag any case where leaving REST isn't justified."
>
> Check: the reply keeps `GET /bookings/{id}` on REST and `/events` on SSE, and gives the customs notification a signed, retried webhook.

## Build, run, observe

No example of its own. The streaming example shows the SSE case that stays on REST:

```bash
cd examples/16-streaming && ./verify.sh
```

Experiments:

- Open the SSE feed and look for a way to acknowledge an event on the same connection. The protocol has none, which is the case for WebSockets.
- Sketch the webhook receiver for a `500` response. The platform retries, so the receiver sees the event twice and must de-duplicate on the event's idempotency key.

## For deeper coverage

- *Cloud Native Design Patterns*, appendix-a-protocols (same series, protocol comparison appendix).
- *Cloud Native Design Patterns*, appendix-c-websockets (same series, dedicated WebSockets appendix).
- *Cloud Native Design Patterns*, event-driven (same series, webhooks as fire-and-forget events).
- Clément Jean, *gRPC Go for Professionals* (Packt, 2023): streaming RPC shapes.
- Gough, Bryant & Auburn, *Mastering API Architecture* (O'Reilly, 2022): protocol selection across an API's lifecycle.
