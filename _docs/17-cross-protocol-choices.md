---
title: "Cross-protocol choices"
order: 17
part: "Large payloads & streaming"
description: "When to leave REST: how REST and SSE compare with WebSockets, webhooks, and gRPC for moving data, and which interaction shapes each one fits."
duration: "22 min"
---

Chapter 15 stretched REST to carry large binary resources with `Range` requests. Chapter 16 stretched it further, carrying continuous and incremental data with the previous chapter's streaming modes. Both chapters answered the same question the same way: REST can be made to fit a surprising range of interactions, if you're willing to add the right header, the right status code, or the right content type. This chapter asks the question those two didn't: when is "make REST fit" the wrong move entirely, and a different protocol the right one?

Chapter 2 built the lens for exactly this decision — seven axes that read an interaction's shape before anyone picks a technology to serve it. This chapter applies that lens to four live tracking a booking from confirmation to delivery produces: a browser watching a booking's status change, a customs broker that needs to hear about a container clearing inspection the moment it happens, a live feed of a vessel's cargo events a dispatcher watches all day, and a routing engine calling a capacity-check service a thousand times a second. One interaction shape per example, four different right answers, and REST is the correct one for exactly one of the four.

## REST and its push ceiling

Start with what REST, plus the previous chapter's streaming modes, already covers well. A `GET /bookings/{id}` call is request/response: the client asks, the server answers once, and the exchange is over. Server-Sent Events extend that shape by one dimension — the server keeps the HTTP connection open and keeps writing events, so a client can watch a booking's status change from `CONFIRMED` to `IN_TRANSIT` to `DELIVERED` without polling. NDJSON streams a large result set as it's produced instead of buffering the whole thing first. Chunked transfer encoding lets a response start before its total size is known. All three are still, structurally, one request followed by a stream of server output over a single HTTP connection the client opened.

That structure is also the ceiling. SSE and chunked encoding are one-directional: the server pushes, and the client's only channel back to the server is to close the connection or open a new HTTP request. A dispatcher watching live cargo events over SSE cannot use that same connection to acknowledge an event, filter the stream, or send a command — every one of those needs is a separate `POST`, round-tripping through DNS, TLS, and connection setup again, layered awkwardly on top of a connection that's already open and already working in the other direction. For the dispatcher scenario, where the *watching* is the whole requirement, that one-directional limit is not a problem; the dispatcher doesn't need to talk back, only to watch. SSE is the right tool there precisely because it doesn't try to be more than a push channel.

REST's other strengths carry forward from every chapter before this one: it rides plain HTTP, which means every corporate proxy, CDN, and firewall already understands it; a browser opens an `EventSource` without a library; `GET` responses are cacheable by URL the moment they aren't continuous streams; and a public booking-status endpoint consumed by browsers, mobile apps, and partner systems needs nothing more exotic than a contract and a client diversity axis note from Chapter 2 says explicitly that REST is the lowest common denominator every heterogeneous client population already speaks. None of that changes here. What changes is the shape of the next three interactions, each of which breaks one of REST's assumptions badly enough that forcing it through REST produces a worse design than reaching for something else.

## WebSockets: when the client needs to talk back

A WebSocket connection starts as an HTTP request — the `Upgrade: websocket` handshake — and then stops being HTTP at all. What's left is a single, full-duplex, stateful TCP-like channel: either side can send a message at any time, independent of whether the other side is "answering" anything, and the connection stays open for the life of the session rather than the life of one exchange. That's a different interaction shape from request/response-with-a-push-tail, and it's the shape a live chat between a shipper and a carrier's support desk has: either party can type at any moment, neither is "requesting" from the other, and the connection needs to exist independent of any one message.

Run the Chapter 2 axes and the case for leaving REST is specific, not general. Interaction shape is the decisive one: bidirectional, low-latency, many-small-messages traffic where either side initiates is not request/response with a push tail, it's a conversation, and SSE has no channel for the client's half of that conversation. Latency matters too — a WebSocket message after the handshake pays no new connection setup, no new TLS negotiation, and no HTTP header overhead per message, which matters when messages are frequent and small. Set those two axes against the ones that now argue the other way. Cacheability disappears entirely — there's no URL to key a cache on once the handshake succeeds, because what follows isn't a sequence of addressable requests, it's a private channel. Client diversity gets harder: a corporate proxy that happily passes HTTP may terminate or refuse the `Upgrade` handshake, and some strict firewalls block it outright, which Chapter 2 already named as the kind of infrastructure vote that tends to favor REST. Operationally, a WebSocket is a long-lived stateful connection a load balancer has to keep pinned to one backend instance, which is a harder scaling problem than a REST server that can treat every request as independent and route it anywhere. A chat feature between a shipper and a support desk justifies absorbing those costs because the two-way, low-latency conversation is the entire point. A booking-status feed that only needs to be watched does not — SSE already serves it, at a fraction of the operational cost, which is why Chapter 16 reached for SSE and not WebSockets for exactly that case.

```
// Illustrative — not a running example
ws.send(JSON.stringify({ type: "message", text: "ETA on the NLRTM leg?" }));
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  // either side can arrive at any time, unprompted by a request
};
```

## Webhooks: push to an endpoint the client owns

A customs broker waiting to hear that a container cleared inspection has a different problem than a dispatcher watching a live feed. The dispatcher's system is online and connected, actively watching a stream; the broker's system might not have a connection open at all, and the event that matters — inspection clearance — happens on the shipping platform's schedule, not the broker's. Polling `GET /bookings/{id}` every few seconds until the status flips is the REST-native answer, and it's a bad one: most polls return nothing new, the broker pays the infrastructure cost of asking constantly, and there's an unavoidable lag between the event happening and the next poll noticing it.

A webhook inverts who initiates. The broker registers a URL on their own infrastructure; when the booking's customs status changes, the shipping platform makes an outbound `POST` to that URL carrying the event, with no open connection and no polling required on either side. This is the fire-and-forget event shape from Chapter 2's first axis, and it's the shape "notify the customs broker" actually has — the confirming service doesn't need to know who's listening or wait for an acknowledgment to proceed, it only needs to deliver a signal.

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

Webhooks trade REST's cacheability and uniform-interface guarantees for something REST's client-initiated model can't offer at all: push to a party the server can't keep a live connection to. That trade comes with three obligations a REST `GET` never had. First, fan-out — a customs-clearance event may have several subscribers (the broker, the carrier, an internal audit log), and the platform owns delivering to all of them, not just one. Second, delivery semantics — a `POST` to an endpoint that's down, slow, or returns a `500` has to be retried, which means the event is delivered *at least once* and the receiver has to tolerate and de-duplicate repeats (an idempotency key on the event, not the HTTP method, does that work here). Third, security — an endpoint that accepts unauthenticated `POST` requests from the internet is an open door, so a webhook payload needs a verifiable signature (the `X-Signature` header above, HMAC'd over the payload with a shared secret) so the receiver can confirm the shipping platform actually sent it and not an attacker who found the URL. None of those three is REST's fault to carry, because webhooks aren't REST — they're a convention layered on top of plain HTTP `POST`, and the convention has to supply what polling a cacheable `GET` would have gotten without any extra work.

## gRPC: when the caller and callee are both yours

The fourth interaction — a routing engine calling a capacity-check service a thousand times a second — is the one Chapter 2's worked example used to introduce the framework, and it's worth returning to now that streaming is on the table. Both ends of this call are services the same team deploys; there's no browser, no third-party partner, and no unknown client population, which removes the client-diversity axis that argues hardest for REST everywhere else in this book. What's left are the axes that argue against it: latency (a capacity check gating a routing decision needs single-digit-millisecond round trips a thousand times over), payload shape (small, fixed-schema messages where JSON's self-describing text format is pure overhead paid on every call), and now, specifically for this chapter, streaming shape — gRPC supports not just unary request/response but client-streaming, server-streaming, and full bidirectional streaming RPCs defined directly in the service contract.

```protobuf
// Illustrative — not a running example
service CapacityCheck {
  rpc CheckCapacity(CapacityRequest) returns (CapacityReply);
  rpc StreamVesselEvents(VesselQuery) returns (stream CargoEvent);
  rpc NegotiateRoute(stream RouteProposal) returns (stream RouteCounter);
}
```

That last RPC shape — bidirectional streaming, defined in the contract itself — is something none of REST, SSE, or webhooks offer, and it's the gRPC-specific answer to the same "both sides need to talk" problem WebSockets solve for browsers. The difference is what surrounds the connection: gRPC runs over HTTP/2, encodes messages as binary Protocol Buffers rather than JSON, and generates client and server stubs directly from the `.proto` file, which buys strong, compiler-checked contracts and low per-message overhead at the cost of the properties REST trades on. A gRPC payload isn't human-readable on the wire the way a REST JSON body is — debugging it means decoding the protobuf, not reading a response in a browser's network tab. Browser support is a bigger gap than it looks: browsers can't open a raw HTTP/2 connection with the trailers gRPC depends on, so browser clients need gRPC-Web and a translating proxy, which is exactly the "every arbitrary client speaks it natively" property REST has and gRPC doesn't. And a corporate proxy that passes REST's plain HTTP without a second thought often doesn't know what to do with gRPC's framing at all. None of that matters for a routing engine calling a capacity-check service it was deployed alongside — there's no browser and no uncontrolled proxy in that path — which is exactly why the client-diversity axis is the one that has to be checked first, every time, before reaching for gRPC.

## Matching interaction shape to protocol

The four examples above aren't exhaustive, but they cover the shapes that recur across a shipping platform, and the table below is the same Chapter 2 reasoning condensed to a lookup.

| Interaction shape | Example | Best fit | Why |
|---|---|---|---|
| Request/response, cacheable, diverse clients | Look up a booking by id | REST | Ubiquitous, cacheable by URL, no client-side tooling required |
| Server push over an open connection, one direction | Watch a booking's status change | REST + SSE (Ch16) | One-directional push is exactly what SSE adds to REST; no new protocol needed |
| Bidirectional, low-latency, either side initiates | Live chat between shipper and support | WebSockets | Full-duplex and stateful; justified when two-way *is* the requirement |
| Fire-and-forget event to a party with no open connection | Notify a customs broker of clearance | Webhooks | Server-initiated `POST` to a client-owned endpoint; no polling, at-least-once with signed payloads |
| High-frequency, low-latency, service-to-service, strongly typed | Capacity check from a routing engine | gRPC | Binary encoding, generated stubs, and native streaming RPCs where both ends are owned and HTTP/2 is available |

Read the table by its left column, not its right one: the shape of the interaction is the input, the protocol is the output, and the four rows that leave REST only do so because one of the seven axes — bidirectionality, an offline receiver, or a latency and client-ownership profile that removes REST's main advantage — forced the issue. REST stays the default for everything that doesn't trip one of those signals, which in most shipping-platform traffic is most of it: booking CRUD, cargo lookups, catalog queries, and anything a browser or an unknown third party needs to call.

This chapter doesn't attempt to teach WebSockets, webhooks, or gRPC in the depth this book teaches REST — each is wide enough to be its own book, and each is one, elsewhere in this series. What belongs here is the recognition moment: an interaction whose shape doesn't fit request/response-plus-push is not a failure of REST to try harder, it's a signal pointing at a different tool, and naming that signal is more valuable than forcing one more header onto a design that was never going to fit.

{% include excalidraw.html file="17-cross-protocol" alt="Four protocols compared side by side by direction, connection model, and best-fit use case: REST plus SSE shown as client-initiated request with optional one-directional server push over a short-lived HTTP connection for cacheable lookups and status watching; WebSockets shown as a full-duplex, stateful, long-lived connection for bidirectional low-latency conversation; webhooks shown as a server-initiated outbound POST to a client-owned endpoint with retry and signature verification for fire-and-forget events to offline receivers; gRPC shown as binary HTTP/2 request/response and streaming RPCs between service-to-service callers with generated contracts." caption="Figure 17.1 — REST, WebSockets, webhooks, and gRPC by interaction shape." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Run the Chapter 2 axes before reaching past REST. If the interaction is request/response or one-directional server push, cacheable, and reaches a diverse or external client population, stay on REST — with SSE, NDJSON, or chunked encoding from Chapter 16 if the push is continuous. Leave REST for WebSockets only when the interaction shape is truly bidirectional and low-latency, and both sides need to initiate at will. Leave REST for webhooks when the shape is a fire-and-forget event aimed at a receiver with no open connection, and budget for fan-out, at-least-once retries, and signature verification up front. Leave REST for gRPC only when client diversity drops out of the picture entirely — both caller and callee are services you own — and the latency or streaming-RPC needs outweigh giving up human-readable payloads and native browser support. Each of the other three gets its own book in this series for exactly that reason: each is a complete discipline once an axis points at it.</p></div>

