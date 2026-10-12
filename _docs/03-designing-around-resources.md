---
title: "Designing around resources"
order: 3
part: "Designing resources with a contract"
description: "Model the domain as resources — nouns not verbs, collections versus items, and why mirroring your database tables produces a chatty, leaky API."
duration: "18 min read"
---

A REST API is a set of nouns reachable by URI, manipulated by a small, fixed verb set. That sounds obvious until you watch a team design one under deadline pressure, where the first instinct is almost always to name an endpoint after the action a client wants to take: `/confirmBooking`, `/cancelBooking`, `/getActiveShipments`. Every one of those names is a verb wearing a URI as a costume — a sign the design process skipped the step this chapter is about: deciding what the things are before deciding what happens to them.

Chapter 1 named resource orientation as one of REST's defining constraints. Chapter 2 gave you the axes to decide whether REST is the right pattern at all. This chapter is where resource orientation stops being a definition and becomes a design move you make against a real domain — the booking and cargo model this site builds on.

## Resources are nouns, methods are verbs

HTTP already ships a verb set: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. A resource-oriented API spends that verb set on the handful of actions those words mean (fetch, create, replace, modify, remove) and expresses everything else about the domain as the *noun* the verb applies to. The method answers "what kind of operation"; the URI answers "on what."

Compare two ways of exposing the same capability in the shipping domain: confirming a pending booking.

```
POST /confirmBooking
{ "bookingId": "bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4" }
```

```
POST /bookings/bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4/confirmation
```

The first is RPC dressed up as HTTP. The verb lives in the path, the real identifier is buried in the body, and the only reason it travels over HTTP at all is that HTTP happens to move bytes between client and server. Nothing about this URI is cacheable, nothing composes with other resources, and nothing tells a new engineer what noun the system is built around. It could just as easily be a function name in an RPC stub, because that's exactly what it is.

The second names a resource: the confirmation of this specific booking. `POST` to that URI creates it — the HTTP method supplies the verb, the path supplies the noun, and the response can return a representation of the thing that was created (an `Operation`, in the async flow Chapter 10 covers, or the confirmed `Booking` itself for a synchronous confirm). A client that already understands `POST` creates things everywhere in this API understands this endpoint without reading custom documentation about what "confirm" means here. That's the payoff resource orientation is for: the verb set is small and already known, so the only thing left to learn is the noun.

This is what Chapter 1 meant by resource orientation as a REST constraint rather than a style preference. An API that grows a new endpoint for every verb a product manager thinks up (`/confirmBooking`, `/rushBooking`, `/splitBooking`) is an RPC API that happens to run over HTTP. It will keep growing new endpoints forever, because verbs are unbounded; the business will always invent a new one. Nouns are bounded by the domain. A shipping system has a finite, slowly-changing set of things worth naming — bookings, cargo, routes, manifests — and an API built around those things stops growing a new top-level path every time someone proposes a new feature. The feature becomes a new sub-resource, a new state transition, or a new field, not a new verb.

That doesn't mean every operation collapses neatly onto `GET`/`POST`/`PUT`/`PATCH`/`DELETE` without a thought. "Confirm," "cancel," and "ship" are real transitions in the booking lifecycle, and forcing them onto `PUT /bookings/{id}` with a `status` field changed in the body hides a meaningful business event inside a generic update. The resource-oriented answer is to turn the verb into a noun the verb set can act on. "Confirm" becomes the `confirmation` sub-resource; `POST` creates it. "Cancel" is a `DELETE` on the booking itself, since the domain treats cancellation as a soft-deletion (Chapter 13 covers why that `DELETE` doesn't erase the row). The discipline is: find the noun hiding inside the verb, then let an HTTP method act on it.

## Don't mirror the database

The second trap is subtler than RPC-flavored endpoints, because it looks like good design until the schema changes. It's the temptation to expose database tables as resources, one table, one endpoint.

Picture the storage behind the booking service: a `bookings` table, a `cargo_items` table with a foreign key back to `bookings`, maybe a `booking_status_history` table for an audit trail. A schema-mirroring API publishes that structure directly:

```
GET  /cargo_items?booking_id=bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4
POST /cargo_items
GET  /booking_status_history?booking_id=bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4
```

This is fast to build, because it's a thin pass-through over `SELECT * FROM cargo_items WHERE booking_id = ?`, and that speed is the problem. The API now has a hard dependency on a column named `booking_id` on a table named `cargo_items`. The moment the storage team normalizes further, splits cargo into `cargo_items` and `cargo_dimensions` for a hazardous-materials workflow, or moves cargo into a separate service with its own database, every client holding a `/cargo_items?booking_id=...` URL breaks, because the API contract and the storage schema were never two different things to begin with.

The deeper cost isn't the specific breakage; it's what the leak does to how clients think. A table-shaped API teaches its clients to think in joins: fetch the booking, separately fetch its cargo items by foreign key, separately fetch its status history, and reassemble the object in client code the server was better positioned to assemble once. That's not a resource model; it's a database client wearing HTTP as a transport. The fix is to design the resource from the client's point of view (what does a client of this API actually act on?) and let the storage schema be whatever shape serves the storage team, hidden behind that resource.

In the shipping contract, that resource is `Booking`, and the aggregate includes its cargo inline:

```json
{
  "id": "bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4",
  "status": "CONFIRMED",
  "origin": { "unLocode": "USNYC", "name": "New York" },
  "destination": { "unLocode": "NLRTM", "name": "Rotterdam" },
  "cargo": [
    { "id": "crg_01H9XZ8K3QJ7M2N4P6R8T0V2W5", "description": "Machine parts", "type": "GENERAL", "dimensions": { "weightKg": 1200.5 } }
  ],
  "quote": { "currency": "USD", "amount": "1250.00" }
}
```

That shape, defined once in `contracts/schemas/shipping.schema.json` as the `Booking` type, has no table named after it anywhere in storage, and doesn't need one. It's a representation the API promises to clients; how the server assembles it from one table, three tables, or a cache is an implementation detail the contract was designed to make invisible. That invisibility is the point of a resource: it's a boundary the server can refactor behind without anyone on the other side of the wire noticing.

## Collections and items

Once a resource is named, REST gives it two complementary shapes: the collection and the item.

`/bookings` is a collection resource. `GET /bookings` returns a page of bookings — the `BookingCollection` type in the contract, an `items` array plus pagination metadata (Chapter 8 covers the keyset pagination strategy behind that `page` object). `POST /bookings` creates a new booking by adding it to that collection; the server assigns the identity (a `bkg_`-prefixed ULID, per the domain glossary) and returns `201 Created` with a `Location` header pointing at the new item's URI. That's the uniform pattern a client can rely on everywhere: creation happens by `POST`-ing a representation to the collection that will contain it, and the collection's job is enumeration and creation, never identifying one specific member.

`/bookings/{bookingId}` is an item resource — one specific booking, addressed by the identity the collection assigned it. `GET` returns the full `Booking` representation; `PUT` replaces it wholesale (an idempotent full update, revisited in Chapter 5's idempotency matrix); `PATCH` applies a partial change (Chapter 7 covers JSON Patch and JSON Merge Patch); `DELETE` soft-deletes it. The item's job is everything that applies to one resource by identity, never enumeration across many.

That split — one URI shape for "the set," a different shape for "one member" — does more work than it looks like. It makes the URI a stable, bookmarkable identity for a single booking, independent of how many other bookings exist or what page a listing returned it on. A client that receives `Location: /bookings/bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4` from a `201` response has a permanent handle to that resource, usable in a `GET`, a `PATCH`, or a link shared with another service, regardless of how the collection's pagination or filtering evolves later.

## Sub-resources: nesting with intent

`/bookings/{bookingId}/cargo` nests a collection inside an item: the cargo items that belong to this specific booking. That nesting is a claim about the domain, not just a URL convention — it says cargo items don't have independent existence outside a booking. You can't `POST` a cargo item to the API without a booking to contain it, there's no `/cargo` top-level collection, and a cargo item's identity is meaningful only in the context of the booking that owns it. The contract backs that claim structurally: `addCargo` is `POST /bookings/{bookingId}/cargo`, not `POST /cargo` with a `bookingId` field in the body, because the first says ownership is part of the identity and the second says it's incidental metadata.

That's the test for whether nesting is justified: does the parent own the child in a way that makes the child meaningless on its own? A booking's cargo passes that test — no cargo item is ever listed, fetched, or reasoned about independent of the booking that requested it be shipped. Contrast that with a hypothetical `/bookings/{bookingId}/locations`: locations are reference data (ports, terminals) reused across hundreds of bookings, so nesting them under one booking's path would suggest an ownership relationship that doesn't exist, and force a client browsing the location catalog to go through an arbitrary booking to get there. Gratuitous nesting shows up as exactly that symptom: a sub-resource path for data a client would reasonably want to address or cache independent of the parent. Chapter 9 gives this trade-off full treatment, including the caching costs of nesting and the redundant-endpoint pitfall of letting one resource be reachable at two shapes that drift out of sync.

{% include excalidraw.html file="03-resource-model" alt="The Booking aggregate exposed three ways: as a collection at /bookings returning a page of bookings, as an item at /bookings/{id} returning one full booking with its cargo embedded, and as a sub-resource at /bookings/{id}/cargo for the owned cargo items, with a callout noting resources are nouns modeled on client access patterns, not a copy of the bookings and cargo_items database tables." caption="Figure 3.1 — The Booking aggregate as resources: collection, item, and sub-resource." %}

## Granularity: the chatty API and the extraneous fetch

Naming resources well is only half the design problem. The other half is deciding how big each resource is — a dial between two failure modes that sit on opposite ends of the same trade-off.

Make resources too granular and you get a **chatty API**: a client that wants to render one booking with its cargo and current quote has to make three round trips — `GET /bookings/{id}`, then `GET /bookings/{id}/cargo`, then `GET /bookings/{id}/quote` — because information that logically belongs together was split into tiny resources. Over a high-latency or mobile connection, that's three round trips stacked in sequence before the screen renders anything. This is sometimes called the N+1 problem, by analogy to the same failure in ORMs: one request for the booking, plus N more for each thing that should have come back with it. A listing screen showing twenty bookings, each needing a follow-up call for its cargo, turns one user action into twenty-one HTTP requests.

Make resources too coarse and you get the opposite failure, **extraneous fetch** (sometimes called over-fetching): every request for a booking drags back its full cargo manifest and every HATEOAS link for every transition the lifecycle supports, even when the client only needed the current status to render a list row. A mobile client on a metered connection pays for fields it will never display; a server pays the compute cost of assembling data nobody asked for.

The shipping contract's `Booking` representation answers the first failure without inviting the second. Cargo is embedded directly in the `Booking` object — `cargo: [{ ... }]` — because a client almost never wants a booking without knowing what it's shipping; those two pieces of information are read together often enough that separate round trips would be chatty for no benefit. That's the balance point this contract settles on for *this* aggregate: embed the sub-resource read together with its parent, and leave reference data reused independently (`Location`, by UN/LOCODE) as its own addressable thing.

That balance point isn't static; embedding doesn't solve over-fetching everywhere. A booking with forty cargo items inlines all forty on every `GET /bookings/{id}` call, fine for a detail screen and wasteful for a dashboard that only needs the booking count and total quote value. Chapter 8 covers the mechanisms that keep a sensible default from becoming a liability at scale: field projection (a `fields` query parameter letting a client ask for only `id,status,quote`, skipping the cargo array) and pagination for any list that could grow unbounded. Granularity isn't a decision made once at design time — it's a dial the contract exposes to the client, so one resource serves both the chatty-unsafe case and the fetch-everything case without two endpoints for the same data.

## Aggregate boundaries as the design unit

The pattern underneath "embed cargo in booking, but keep location separate" has a name from domain-driven design: the aggregate. An aggregate is a cluster of objects that change and load together, with one of them, the aggregate root, as the only entry point from outside the cluster. `Booking` is the aggregate root here; `Cargo` lives inside the boundary and is never addressed, created, or modified except through its owning booking. That's a stronger claim than "nested URL": it's a statement about ownership that the URL structure, the embedded representation, and the request validation (cargo requires `minItems: 1` on a `BookingRequest`; you can't create a booking with nothing to ship) all reinforce together.

Treating the aggregate as the unit of resource design keeps the chatty-versus-coarse trade-off from becoming a guessing game. The question stops being "should this be its own endpoint?" asked field by field, and becomes "does this belong inside the booking aggregate, or is it an independent thing the booking merely references?" Cargo is inside the boundary because it has no identity or lifecycle apart from the booking. `Location` is outside it because the same `USNYC` port is referenced by thousands of bookings with its own lifecycle unrelated to any one of them. A `Route`, introduced later for HATEOAS (Chapter 12), sits outside the aggregate too, for the same reason: it's planned and modified independent of any single booking, even though a confirmed booking links to one.

Get the boundary right and the granularity problem mostly resolves itself: everything inside it is safe to embed, because it's read and written as a unit anyway, and everything outside it is safe to leave as a reference, because a client that needs it independently has its own resource to ask for. Get the boundary wrong — split cargo out because it felt like its own table, or inline location data for one screen's convenience — and no amount of field projection or pagination fixes the mismatch between what the API exposes and what the domain actually owns.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to resource granularity, not just to pattern choice: model a resource around what clients act on and how they fetch it, not around your tables, and let the aggregate boundary — what has no identity or lifecycle outside its parent — settle the chatty-versus-coarse trade-off, with field projection and pagination (Chapter 8) handling the cases the boundary alone can't.</p></div>
