---
title: "APIs & patterns"
order: 1
part: "Foundations & the decision lens"
description: "RPC versus Web APIs, the REST constraints, and resource-oriented architecture: the mental model the later chapters build on."
duration: "15 min read"
---

## Learning objectives

By the end of this chapter you can:

- Distinguish an RPC-shaped operation (`confirmBooking`) from a resource-oriented one (`POST /bookings/{id}/confirmation`), and say what each costs at the boundary's edges.
- Name REST's five required constraints (client-server, stateless, cacheable, uniform interface, layered system) plus the optional code-on-demand, and what each one buys and costs.
- Explain the four parts of the uniform interface constraint, and why it's the one that separates REST most sharply from RPC.
- Distinguish a resource, a representation, and a state transfer using the `Booking` aggregate.
- Place an API on Richardson's maturity model (levels 0-3) and say where the shipping contract starts (level 2) and where it ends up (level 3, with hypermedia).

## Why this matters

An API is the boundary a client is allowed to touch. Everything behind it (the database schema, the routing engine, the overnight manifest reconciliation) can change on any schedule as long as the boundary holds still. API design decides what that boundary looks like, and so what "holds still" means and what the promise costs to keep for years.

There are two basic ways to shape it. Most of the friction teams feel when an API becomes hard to change traces back to picking one without noticing there was a choice.

## RPC: exposing procedures

An RPC API is a list of procedures a client invokes remotely. A client already knows how to call a function, so an API shaped like one needs no new mental model: name an operation, pass arguments, get a result. A booking confirmation looks like this:

```http
POST /confirmBooking HTTP/1.1
Content-Type: application/json

{"bookingId": "bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y"}
```

In a typed RPC framework it reads `confirmBooking(bookingId: "bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y") -> ConfirmationResult`.

Nothing in the contract says what `confirmBooking` does to server state, whether calling it twice is safe, or what else can be done with a booking. The contract is a menu of verbs (`confirmBooking`, `cancelBooking`, `addCargoToBooking`, `getBookingManifest`), and every new capability adds one the client must learn separately. gRPC, SOAP, and most hand-rolled HTTP layers over a service's public methods are RPC in this sense.

RPC is the right shape when the operation is a procedure: a calculation, a workflow trigger, a command with no durable state a client would look up later. It costs you at the edges. Every operation needs its own endpoint, its own request and response shape, and its own line in a client SDK, because nothing in the contract is predictable from one operation to the next. The work of writing and versioning each stub repeats instead of shrinking as the surface grows.

## Web APIs: exposing things

A Web API is a set of addressable things, resources, that a small fixed set of methods acts on. There's a noun for each kind of thing the system manages, and the operations come from a shared menu: fetch, replace, update part of, delete, create in a collection. REST is its most developed formalization. The same confirmation, as an action on a resource:

```http
POST /bookings/bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y/confirmation HTTP/1.1
```

This names a thing, the booking's confirmation, and asks the uniform `POST` method to create it. The booking has an identifier (`bkg_01HQZX...`), a representation (the JSON a `GET` on `/bookings/{bookingId}` returns), and a lifecycle other resources hang off: `/bookings/{bookingId}/cargo` for what it carries, `/bookings/{bookingId}/manifest` for the document listing it, `/bookings/{bookingId}/confirmation` for confirming it. A client that knows how `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` behave on one resource knows, to a first approximation, how they behave on all of them. The verbs stay fixed and small while the nouns grow to cover the domain.

That changes what a client must know in advance, what generic tools can do without custom code, and what breaks when the backend changes shape.

## The REST constraints

Roy Fielding's 2000 dissertation coined REST (Representational State Transfer). It proposed no file format or URL scheme. It described architectural constraints that together let a system scale to huge numbers of independent clients, let components evolve without coordinated releases, and let caches and proxies sit in the request path without understanding the application. Each constraint buys something and costs something.

| Constraint | What it says | What you get | What dropping it costs |
|---|---|---|---|
| Client-server | Client and server are separate concerns joined only by the interface. | Independent evolution: the Quarkus implementation can be rewritten without a client noticing. | A client that reaches into the database makes a distributed monolith that deploys in lockstep. |
| Stateless | Every request carries everything needed to process it; the server keeps no session. | A request works on any instance. Horizontal scaling without sticky sessions, easy recovery from a crash. | Session state on one instance ties you to it and breaks free load balancing. |
| Cacheable | Responses declare whether and how long they can be cached. | `Cache-Control` or an `ETag` lets a cache or the client skip the round trip, at zero server CPU. | Every client pays a full round trip for data that hasn't changed. |
| Layered system | A client can't tell whether it talks to the origin, a proxy, a CDN or a gateway. | Caching, rate limiting, TLS termination and auth at any layer, with no change to the application. | Assuming a direct connection loses deployability behind real infrastructure. |
| Code-on-demand (optional) | The server ships executable logic to the client, as a browser runs JavaScript. | New client behavior without a release. | Irrelevant for a server-to-server client such as a batch job polling an operation. |

The uniform interface does the most work and separates REST from RPC most sharply. It has four parts:

- Resources are identified by URIs.
- Resources are manipulated through representations: the client sends and receives a document, not the server's internal object.
- Messages are self-descriptive: `Content-Type` and the status code say how to process a response without out-of-band knowledge.
- Hypermedia drives state transitions: the next steps are discoverable from the response instead of hard-coded in the client.

The payoff is leverage. A generic HTTP client, cache, proxy or tooling library works against any resource without knowing anything about bookings or cargo, so the shipping API's clients need no custom SDK. Break uniformity, for example by putting a non-standard verb in a request body instead of using the method, and you're back to bespoke client code per endpoint: the RPC tax by another name.

{% include excalidraw.html file="01-rest-constraints" alt="An RPC-style API as a flat list of named procedure calls, each with its own request and response shape, beside a Web API as five HTTP methods acting uniformly on a booking, its cargo and its confirmation. Below, the five REST constraints as labeled bands, with uniform interface emphasized." caption="Figure 1.1: The REST constraints, and the uniform interface that makes them pay off." %}

These constraints describe an architecture, not a protocol. HTTP implements them well, which is why the two are often treated as synonyms.

## Resources as nouns

With the uniform interface as the organizing idea, the design question changes from "what operations does this system need" to "what things does it manage, and what does it mean to look at, replace, partially change or delete one."

A **resource** is a noun with an identifier. A booking is addressable at `/bookings/bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y`, and a cargo item within it at `/bookings/{bookingId}/cargo/{cargoId}`. Neither identifier contains a verb. The URI names a thing, and the method (`GET`, `PATCH`, `DELETE`) carries the action.

A **representation** is what goes over the wire to describe a resource's current state, almost always a JSON document matching a schema defined once in the OpenAPI contract. The resource is the durable thing with identity and a lifecycle; the representation is a snapshot of it. One resource can have several representations, such as JSON for most clients and a PDF for the manifest.

A **state transfer** is a client sending or receiving a representation through a uniform method. `GET` transfers the booking's current state to the client. `PUT` on the same URI transfers a client-supplied representation to the server, which makes its copy match; `PUT` is idempotent, so a retry leaves the same state. `POST /bookings` transfers a representation with no identity yet into the collection, which assigns one and returns it in `Location`:

```json
{
  "id": "bkg_01HQZX3K2M8N7P6R5T4V3W2X1Y",
  "status": "PENDING",
  "origin": "USNYC",
  "destination": "NLRTM"
}
```

A booking isn't an operation you invoke. It's a thing with a state machine: `PENDING` → `CONFIRMED` → `IN_TRANSIT` → `DELIVERED`, with `CANCELLED` reachable from the first two. Its cargo items are sub-resources under `/bookings/{bookingId}/cargo` because they have no meaning without a parent booking. The confirmation is a resource one level down, rather than a verb bolted onto the booking, because confirming triggers routing and capacity checks that don't finish within one request. A client needs something to `POST` to and a `202` with a `Location` pointing at an operation to poll. An RPC-shaped `confirmBooking()` offers neither.

## REST is a spectrum

Richardson's maturity model treats "RESTful" as levels:

| Level | Shape |
|---|---|
| 0 | One URI and one method, usually `POST`, with the operation named in the body. RPC with HTTP as transport. |
| 1 | Resources: different URIs for different things, but one overloaded method. |
| 2 | The uniform interface: methods carry their standard meaning and status codes report the outcome, instead of `200` with a success flag in the JSON. |
| 3 | Hypermedia: links describe valid next actions, so a client discovers them from the response. |

Most APIs that call themselves REST sit at level 2: resources, methods and status codes, no hypermedia. That's a durable place to be. The shipping API is level 2 from its first contract and reaches level 3 once the booking lifecycle is rich enough to justify links. Adding hypermedia before then applies a constraint for its own sake.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Reach for REST when the interaction is <em>resource-shaped</em>: a durable noun with an identity, a lifecycle, and a representation a client might fetch, cache or revisit. Lean on the uniform interface when you want generic HTTP infrastructure (caches, proxies, gateways, off-the-shelf clients) to work without custom code per endpoint. If the operation has no durable state, isn't cacheable, and reads naturally as a verb, keep looking instead of forcing it into a resource.</p></div>

> **🤖 Explore with your agent**
>
> "Read `contracts/openapi/shipping-api.yaml`. For each path, classify it as resource-shaped or RPC-shaped using the uniform-interface rule (the URI names a noun, the method carries the action). Place the contract on Richardson's levels and cite one path and one response that justify the level. Then propose, without editing the file, how `POST /bookings/{bookingId}/confirmation` would look as `confirmBooking` RPC, and list two things a generic client would lose."
>
> Check: every path in the reply exists in `grep -nE '^  /' contracts/openapi/shipping-api.yaml`, and the RPC version contains a verb in the URI.

## For deeper coverage

- Roy T. Fielding, [*Architectural Styles and the Design of Network-based Software Architectures*](https://www.ics.uci.edu/~fielding/pubs/dissertation/top.htm) (doctoral dissertation, UC Irvine, 2000): the primary source for REST and its constraints.
- Leonard Richardson & Mike Amundsen, *RESTful Web APIs* (O'Reilly, 2013): the REST constraints and the maturity model, from the authors who named it.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): resource naming and representation design.
- Cloud Native Design Patterns, [Communications](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/02-communications.md): the companion book's broader survey of API styles beyond REST.
