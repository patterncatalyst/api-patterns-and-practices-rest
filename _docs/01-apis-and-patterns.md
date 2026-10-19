---
title: "APIs & patterns"
order: 1
part: "Foundations & the decision lens"
description: "RPC versus Web APIs, the REST constraints, and resource-oriented architecture — the mental model the later chapters build on."
duration: "15 min read"
---

## Learning objectives

By the end of this chapter you can:

- Distinguish an RPC-shaped operation (`confirmBooking`) from a resource-oriented one (`POST /bookings/{id}/confirmation`), and say what each costs at the boundary's edges.
- Name REST's five required constraints (client-server, stateless, cacheable, uniform interface, layered system) plus the optional code-on-demand, and what each one buys and costs.
- Explain the four parts of the uniform interface constraint, and why it's the one that separates REST most sharply from RPC.
- Distinguish a resource, a representation, and a state transfer using the `Booking` aggregate.
- Place an API on Richardson's maturity model (levels 0-3) and say where the shipping contract starts (level 2) and where it ends up (level 3, Chapter 12).

## Why this matters

An API is the boundary a client is allowed to touch. Everything behind it — the database schema, the routing engine that plans a voyage, the queue that reconciles a manifest overnight — is free to change on any schedule the team likes, as long as the boundary holds still. API design is the discipline of deciding what that boundary looks like, because the shape chosen determines what "holds still" means and how expensive that promise is to keep for years.

There are two fundamentally different ways to shape that boundary, and most of the friction teams feel when an API becomes hard to change traces back to picking one without noticing there was a choice at all.

## RPC: exposing procedures

The first shape treats the API as a list of procedures a client can invoke remotely. This is Remote Procedure Call, RPC, and it is the older, more natural idea: a client already knows how to call a function, so an API that looks like a remote function call needs no new mental model. Name an operation, pass it arguments, it does something and hands back a result.

A booking confirmation in an RPC-shaped API looks like a function call wearing a network costume:

```http
POST /confirmBooking HTTP/1.1
Content-Type: application/json

{"bookingId": "bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y"}
```

or, in a typed RPC framework, closer to:

```
confirmBooking(bookingId: "bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y") -> ConfirmationResult
```

The server-side implementation is whatever the operation's name says it is. Nothing in the contract tells the client what `confirmBooking` actually does to server state, whether calling it twice is safe, or what else exists to do with a booking. The contract is a menu of verbs: `confirmBooking`, `cancelBooking`, `addCargoToBooking`, `getBookingManifest`. Every new capability means a new verb, and every verb is its own island of meaning the client has to learn individually. gRPC, SOAP, and most hand-rolled "API" layers that are really just HTTP wrapping a service's public methods are RPC in this sense, whether or not anyone calls them that.

RPC is not wrong. It is the right shape when the operation is a procedure — a calculation, a workflow trigger, a command that doesn't correspond to a durable piece of state a client would want to look up later. Where it costs you is at the boundary's edges: every operation needs its own endpoint, its own request and response shape, and usually its own line in a client SDK, because nothing about the contract is predictable from one operation to the next. A client library generated against an RPC contract is a collection of bespoke stubs, one per verb, and the work of writing and versioning each one doesn't shrink as the surface grows — it just repeats.

## Web APIs: exposing things

The second shape treats the API as a set of addressable things — resources — that a small, fixed set of methods acts on. Instead of a verb for every operation, there is a noun for every kind of thing the system manages, and the operations come from a shared menu: fetch it, replace it, update part of it, delete it, create a new one in a collection. This is the Web API style, and REST is its most developed and most widely adopted formalization.

The same confirmation, reshaped as an action on a resource, looks like this against the shipping API's contract:

```http
POST /bookings/bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y/confirmation HTTP/1.1
```

Nothing here names a procedure. It names a thing — this booking's confirmation — and asks the uniform `POST` method to create it. The booking is a resource with an identifier (`bkg_01HQZX...`), a representation (the JSON body a `GET` on `/bookings/{bookingId}` returns), and a lifecycle other resources hang off: `/bookings/{bookingId}/cargo` for what it carries, `/bookings/{bookingId}/manifest` for the document listing it, `/bookings/{bookingId}/confirmation` for confirming it. A client that already knows how `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` behave on one resource here already knows, to a first approximation, how they behave on every other one. That's the trade RPC doesn't offer: the verbs stay fixed and small while the nouns grow to cover the whole domain.

This isn't a stylistic preference. It changes what a client needs to know in advance, what a generic tool can do without custom code, and what breaks when the backend changes shape. The sections below work out why, constraint by constraint.

## The REST constraints

Roy Fielding's 2000 dissertation, which coined REST (Representational State Transfer), didn't propose a file format or a URL scheme. It described architectural constraints that, applied together, produce the properties the modern web runs on: scale to enormous numbers of independent clients, let components evolve without coordinated releases, let infrastructure like caches and proxies sit in the request path without understanding the application running over them. Each constraint buys something specific, and — worth sitting with — each one costs something specific. Dropping a constraint isn't free and isn't automatically wrong; it's a trade a design should weigh, not stumble into.

**Client–server.** The client and server are separate concerns connected only by the interface between them. The server doesn't care whether the caller is a browser or another service; the client doesn't care whether bookings live in Postgres or get recomputed from an event log. You get independent evolution: the shipping API's Quarkus implementation can be rewritten in a different framework without a client noticing, as long as the contract holds. Blur this line (a client that reaches past the API into the database) and you lose that independence; the two sides become one distributed monolith that deploys in lockstep.

**Stateless.** Every request carries all the information needed to understand and process it; the server keeps no session state about where a client is in a multi-step interaction. A request to fetch a booking works identically whether it lands on the same server instance as the last request or a different one entirely. You get horizontal scalability without sticky sessions and trivial recovery from a crashed server. Drop it — session state tied to one instance — and you lose the ability to load-balance freely or survive a restart without the client noticing; a small convenience in request size buys a hard operational dependency.

**Cacheable.** Responses declare, implicitly or explicitly, whether and how long they can be cached. A `GET` on `/bookings/{bookingId}` is safe to cache until the booking changes; `Cache-Control` or an `ETag` lets a shared cache or the client skip a round trip entirely. You get fewer requests reaching the server — the cheapest optimization, because it costs zero server CPU. Skip it and every client pays the full round trip for data that hasn't changed, a missed saving that compounds at scale.

**Uniform interface.** This is the constraint that does the most work, and the one that separates REST from RPC most sharply. It has four parts: resources are identified by URIs; resources are manipulated through representations (the client sends and receives a document, JSON here, not the server's internal object); messages are self-descriptive (`Content-Type` and status code tell you how to process a response without out-of-band knowledge); and hypermedia drives state transitions (deferred to Chapter 12), so the next available steps are discoverable from the response itself rather than hard-coded into the client. Committing to this buys enormous leverage: a generic HTTP client, cache, proxy, or tooling library works against any resource without being told anything about bookings or cargo specifically. That's why the shipping API's clients don't need a custom SDK the way an RPC contract would demand. Break uniformity (a resource that accepts a non-standard verb in the request body instead of using the method) and you're back to bespoke client code per endpoint, the RPC tax by another name.

**Layered system.** A client can't tell, and shouldn't need to tell, whether it's talking directly to the origin server or to a load balancer, a reverse proxy, a CDN edge, or a gateway doing authentication in front of it — each layer only needs to understand the uniform interface, not the application behind it. You get to insert caching, rate limiting, TLS termination, or auth enforcement at any layer without touching the application or the client. Assume a direct connection instead and you lose deployability behind the infrastructure every production system sits behind.

**Code-on-demand (optional).** The only optional constraint: a server extends client behavior by shipping executable logic, the way a browser downloads and runs JavaScript. A machine-client REST API like the shipping one mostly skips this — a batch job polling `/operations/{operationId}` has no use for downloadable code — which is fine; Fielding marked it optional because it doesn't apply everywhere. Needing it without having it costs the ability to push new client behavior without a release, which matters for browsers and almost never for a server-to-server booking client.

{% include excalidraw.html file="01-rest-constraints" alt="A split diagram contrasting an RPC-style API, shown as a flat list of named procedure calls like confirmBooking and cancelBooking each with its own bespoke request and response shape, against a Web API shown as a small fixed set of HTTP methods — GET, POST, PUT, PATCH, DELETE — acting uniformly on addressable resources such as a booking, its cargo, and its confirmation; below the split, the five REST constraints are listed as labeled bands (client-server, stateless, cacheable, uniform interface, layered system) with the uniform interface band visually emphasized as the one that lets a single generic client work against every resource without a custom SDK." caption="Figure 1.1 — The REST constraints, and the uniform interface that makes them pay off." %}

Taken together, these constraints describe an architecture, not a protocol. HTTP happens to implement all of them well, which is why REST and HTTP are so often treated as synonyms, but the constraints are the actual point: a client that doesn't need custom code per endpoint, infrastructure that sits in the request path without understanding your domain, a server that evolves its internals without breaking every caller on the same day.

## Resources as nouns

Once the uniform interface is the organizing idea, the design question stops being "what operations does this system need" and becomes "what are the things this system manages, and what does it mean to look at, replace, partially change, or delete one." That's resource-oriented architecture, and Chapter 3 spends a full chapter on getting its three parts right.

A **resource** is a noun with an identifier. A booking is a resource — `bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y`, addressable at `/bookings/bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y` — and so is a cargo item within it, at `/bookings/{bookingId}/cargo/{cargoId}`. Notice what's absent: there's no verb in either identifier. The URI names a thing, never an action, which is what keeps the method (`GET`, `PATCH`, `DELETE`) doing the work a verb-shaped endpoint would otherwise carry in its own name.

A **representation** is what gets sent across the wire to describe a resource's current state — almost always a JSON document matching the shapes defined once in the shared schema and referenced by the OpenAPI contract. The representation is not the resource: the resource is the durable thing with identity and a lifecycle, the representation a snapshot of it, and the same resource can have multiple representations (JSON for most clients, a PDF for the manifest in Chapter 15) without changing what resource it is.

**State transfer** is what happens when a client sends or receives a representation through one of the uniform methods. A `GET` transfers the booking's current state to the client. A `PUT` on the same URI transfers a client-supplied representation to the server, making the server's copy match it — see Chapter 5 for what "idempotent" buys here, since `PUT` is meant to be idempotent. A `POST /bookings` transfers a representation with no identity yet into the collection, which assigns one and returns it via `Location`, per the contract:

```json
{
  "id": "bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y",
  "status": "PENDING",
  "origin": "USNYC",
  "destination": "NLRTM"
}
```

This is where the resource-oriented shape pays off: a booking is not an operation you invoke, it's a thing with a state machine (`PENDING` → `CONFIRMED` → `IN_TRANSIT` → `DELIVERED`, with `CANCELLED` reachable from either of the first two). Its cargo items are sub-resources nested under it, at `/bookings/{bookingId}/cargo`, because they don't make sense without a parent booking to belong to. The confirmation is itself modeled as a resource one level down — `/bookings/{bookingId}/confirmation` — rather than a verb bolted onto the booking, because confirming triggers routing and capacity checks that don't finish within one request, and Chapter 10 needs something to `POST` to and something to hand back a `202` with a `Location` pointing at the operation to poll. None of that falls out of an RPC-shaped `confirmBooking()` call; it falls directly out of asking what the noun is and what the uniform interface lets you do to it.

## REST is a spectrum, not a switch

"RESTful" gets used as a binary (an API either is or isn't), but Leonard Richardson's maturity model treats it as levels, a useful gut check for where an API actually sits. Level 0 tunnels everything through one URI and one method, usually `POST`, with the real operation named inside the body: RPC wearing HTTP as transport and nothing more. Level 1 introduces resources, different URIs for different things, but still overloads a single method to mean whatever the body says. Level 2 adds the uniform interface properly: methods carry their standard meaning, and status codes communicate outcome instead of everything replying `200` with a success flag buried in the JSON. Level 3 adds hypermedia, links describing valid next actions, so a client discovers what it can do next from the response itself rather than from out-of-band documentation.

Most APIs that call themselves REST today sit at level 2: proper resources, proper methods, proper status codes, no hypermedia. That's a durable place to sit, and it's where this book's contract starts. The shipping API is level 2 from Chapter 4 onward — authored contract-first, methods and status codes doing real work — and reaches level 3 in Chapter 12, once the booking lifecycle is rich enough to justify hypermedia instead of adding links nobody follows. Jumping straight to hypermedia before there's a reason is a constraint applied for its own sake rather than for what it buys; this book's sequencing is level 2 first, hypermedia once the domain justifies it.

## Where this goes next

Knowing the two shapes and the five constraints answers "what are my options," not "which one fits this interaction." That's Chapter 2: a decision framework with explicit criteria — resource-shaped or action-shaped, cacheable or not, does a generic client need to work against it unmodified — that turns this chapter's vocabulary into a repeatable call, and recurs as a Decision callout closing every concept chapter from here on. Chapter 3 takes resource-oriented architecture further: naming collections versus items, not mirroring a database schema, and the chatty-API anti-pattern that shows up when a resource boundary is drawn in the wrong place. Chapter 4 turns the design into an OpenAPI contract that CI validates both stacks against, the artifact every hands-on chapter after it builds from.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Reach for REST when the interaction is <em>resource-shaped</em> — there's a durable noun with an identity, a lifecycle, and a representation a client might want to fetch, cache, or revisit, rather than a one-off calculation or command. Lean on the uniform interface specifically when you want generic HTTP infrastructure — caches, proxies, gateways, off-the-shelf client libraries — to work against your API without custom code per endpoint. If the operation has no durable state of its own, isn't meaningfully cacheable, and reads naturally as a verb rather than a noun, that's a signal to keep looking rather than force-fit it into a resource; Chapter 2 turns this instinct into a repeatable framework.</p></div>

## For deeper coverage

- Roy T. Fielding, [*Architectural Styles and the Design of Network-based Software Architectures*](https://www.ics.uci.edu/~fielding/pubs/dissertation/top.htm) (doctoral dissertation, UC Irvine, 2000) — the primary source for REST and its constraints.
- Leonard Richardson & Mike Amundsen, *RESTful Web APIs* (O'Reilly, 2013) — the REST constraints and the maturity model this chapter applies, from the authors who named it.
- J. J. Geewax, *API Design Patterns* (Manning, 2021) — resource naming and representation design for the patterns this chapter introduces.
- Cloud Native Design Patterns, [Communications](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/02-communications.md) — the companion book's broader survey of API styles beyond REST.
