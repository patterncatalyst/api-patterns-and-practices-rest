---
title: "Designing around resources"
order: 3
part: "Designing resources with a contract"
description: "Model the domain as resources: nouns not verbs, collections versus items, and why mirroring your database tables produces a chatty, leaky API."
duration: "18 min read"
---

## Learning objectives

By the end of this chapter you can:

- Turn a verb-shaped endpoint (`POST /confirmBooking`) into a noun-shaped resource (`POST /bookings/{bookingId}/confirmation`).
- Explain why exposing database tables directly (`GET /cargo_items?booking_id=...`) leaks the storage schema into the API contract.
- Distinguish a collection resource (`/bookings`) from an item resource (`/bookings/{bookingId}`), and what job each one does.
- Decide whether to nest a sub-resource, such as `/bookings/{bookingId}/cargo`, by testing whether the parent owns the child.
- Use the `Booking` aggregate's boundary to resolve the chatty-API versus extraneous-fetch trade-off instead of guessing field by field.

## Why this matters

Under deadline pressure the first instinct is to name an endpoint after the action a client wants: `/confirmBooking`, `/cancelBooking`, `/getActiveShipments`. Each is a verb wearing a URI as a costume, and each skips the step that comes first: deciding what the things are before deciding what happens to them.

Resource orientation is a design move you make against a real domain, here the booking and cargo model. Three decisions carry it: name the nouns, keep storage out of the contract, and draw each resource's boundary.

## Resources are nouns, methods are verbs

HTTP ships a verb set: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`. A resource-oriented API spends it on the actions those words mean (fetch, create, replace, modify, remove) and expresses everything else in the domain as the noun the verb applies to. The method answers "what kind of operation"; the URI answers "on what." Confirming a pending booking, two ways:

```
POST /confirmBooking
{ "bookingId": "bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4" }
```

```
POST /bookings/bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4/confirmation
```

The first is RPC over HTTP. The verb is in the path, the identifier is in the body, and nothing about it is cacheable or composes with other resources. The second names a resource, this booking's confirmation, and `POST` creates it. The response can return the created thing: an `Operation` for the asynchronous flow, or the confirmed `Booking` for a synchronous confirm. A client that understands `POST` understands this endpoint with no custom documentation. The verb set is small and known, so only the noun is left to learn.

Verbs are unbounded, because the business will always invent another (`/rushBooking`, `/splitBooking`). Nouns are bounded by the domain: bookings, cargo, routes, manifests. A noun-shaped API gets a new sub-resource, state transition or field for a new feature, not a new top-level path.

Not every operation maps cleanly onto five methods. "Confirm," "cancel" and "ship" are real lifecycle transitions, and forcing them into `PUT /bookings/{id}` with a changed `status` hides a business event inside a generic update. Find the noun hiding in the verb. "Confirm" becomes the `confirmation` sub-resource, created with `POST`. "Cancel" is `DELETE` on the booking, a soft deletion that doesn't erase the row.

## Don't mirror the database

The subtler trap looks like good design until the schema changes: one table, one endpoint. With a `bookings` table, a `cargo_items` table keyed back to it and a `booking_status_history` table, a schema-mirroring API publishes that structure:

```
GET  /cargo_items?booking_id=bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4
POST /cargo_items
GET  /booking_status_history?booking_id=bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4
```

It's fast to build, a thin pass-through over `SELECT * FROM cargo_items WHERE booking_id = ?`, and that is the problem. The contract now depends on a column named `booking_id` on a table named `cargo_items`. When storage splits cargo into `cargo_items` and `cargo_dimensions`, or moves it to another service, every client holding a `/cargo_items?booking_id=...` URL breaks, because the contract and the schema were never two things.

The leak also changes how clients think. A table-shaped API teaches them to join: fetch the booking, fetch its cargo by foreign key, fetch its history, and reassemble in client code what the server could assemble once. Design the resource from the client's side and let storage take whatever shape suits the storage team. In the shipping contract that resource is `Booking`, with its cargo inline:

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

The `Booking` type is defined once in `contracts/schemas/shipping.schema.json`. No table is named after it. The server may build it from one table, three, or a cache, and the contract makes that invisible, so the server can refactor behind it.

## Collections and items

A named resource takes two shapes.

`/bookings` is a collection. `GET /bookings` returns a page: the `BookingCollection` type, an `items` array plus pagination metadata. `POST /bookings` adds a booking; the server assigns the identity (a `bkg_`-prefixed ULID) and returns `201 Created` with a `Location` header for the new item. A collection enumerates and creates. It never identifies one member.

`/bookings/{bookingId}` is an item, addressed by the identity the collection assigned.

| Method | On the item |
|---|---|
| `GET` | Returns the full `Booking`. |
| `PUT` | Replaces it wholesale (idempotent). |
| `PATCH` | Applies a partial change (JSON Patch or JSON Merge Patch). |
| `DELETE` | Soft-deletes it. |

The split makes the item URI a stable, bookmarkable identity, independent of how many other bookings exist or which page listed it. A client that receives `Location: /bookings/bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4` holds a permanent handle for a `GET`, a `PATCH`, or a link shared with another service, however pagination and filtering evolve.

## Sub-resources: nesting with intent

`/bookings/{bookingId}/cargo` nests a collection inside an item, and the nesting is a claim about the domain: cargo has no existence outside a booking. There's no top-level `/cargo`, and you can't create a cargo item without a booking to contain it. That is why `addCargo` is `POST /bookings/{bookingId}/cargo` and not `POST /cargo` with a `bookingId` in the body. The first makes ownership part of the identity; the second makes it incidental metadata.

Nest only when the parent owns the child so completely that the child is meaningless alone. Cargo passes. `/bookings/{bookingId}/locations` fails. Locations (ports, terminals) are reference data reused across hundreds of bookings, so nesting them implies ownership that doesn't exist and forces a client browsing the location catalog to go through an arbitrary booking. The symptom of gratuitous nesting is a sub-resource path for data a client would want to address or cache independently of its parent. Nesting also has costs: a nested path is cached per parent, and a resource reachable at two shapes (nested and top-level) gives two endpoints that drift out of sync.

{% include excalidraw.html file="03-resource-model" alt="The Booking aggregate as a collection at /bookings, an item at /bookings/{id} with cargo embedded, and a sub-resource at /bookings/{id}/cargo, with a note that resources model client access patterns, not database tables." caption="Figure 3.1: The Booking aggregate as resources: collection, item, and sub-resource." %}

## Granularity: the chatty API and the extraneous fetch

Resource size is a dial with a failure mode at each end.

| Too fine | Too coarse |
|---|---|
| **Chatty API.** Rendering a booking with its cargo and quote takes three sequential round trips (`/bookings/{id}`, `/cargo`, `/quote`). A list of twenty bookings, each needing a cargo call, becomes twenty-one requests: the N+1 problem. | **Extraneous fetch.** Every booking request returns the full cargo manifest and every transition link, though a list row needs only the status. A metered mobile client pays for fields it never shows. |

The `Booking` representation embeds cargo because a client almost never wants a booking without knowing what it ships; the two are read together. `Location`, reused independently, stays its own addressable resource.

Embedding doesn't end over-fetching. A booking with forty cargo items inlines all forty on every `GET`, fine for a detail screen and wasteful for a dashboard that needs a count and a total. Field projection (a `fields` parameter asking for `id,status,quote`) and pagination for any list that can grow without bound keep the default from becoming a liability. Granularity is a dial the contract exposes to the client, so one resource serves both cases without two endpoints for the same data.

## Aggregate boundaries as the design unit

The rule underneath "embed cargo, keep location separate" comes from domain-driven design: the aggregate. An aggregate is a cluster of objects that change and load together, with one aggregate root as the only entry point from outside. `Booking` is the root. `Cargo` lives inside the boundary and is addressed, created and modified only through its booking. The URL structure, the embedded representation and the request validation (`minItems: 1` on cargo in a booking request) all reinforce that ownership.

Taking the aggregate as the unit turns "should this be its own endpoint?", asked field by field, into one question: does this belong inside the booking, or is it an independent thing the booking references? Cargo has no identity or lifecycle apart from the booking, so it's inside. `Location` is referenced by thousands of bookings and has its own lifecycle, so it's outside. A `Route` is planned and changed independently of any one booking, even though a confirmed booking links to one, so it's outside too.

Inside the boundary, embed: it's read and written as a unit anyway. Outside it, reference: a client that needs the thing alone has a resource to ask for. Draw the boundary wrongly, by splitting cargo out because it felt like its own table or inlining location data for one screen, and no projection or pagination repairs the mismatch between what the API exposes and what the domain owns.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the decision axes to resource granularity, not just pattern choice: model a resource around what clients act on and how they fetch it, not around your tables. Let the aggregate boundary (what has no identity or lifecycle outside its parent) settle the chatty-versus-coarse trade-off, and use field projection and pagination for the cases the boundary alone can't.</p></div>

> **🤖 Explore with your agent**
>
> "In `contracts/openapi/shipping-api.yaml`, add a way to split a booking into two without adding a verb to any path: model it as a noun using the 'find the noun in the verb' rule. Then decide, using the ownership test, whether a new `Location` lookup belongs under `/bookings/{bookingId}` or at the top level, and whether `Route` is inside or outside the `Booking` aggregate. Explain each answer in one sentence."
>
> Check: `grep -nE '^  /' contracts/openapi/shipping-api.yaml` shows no path segment that is a verb such as `split`, and `Location` is not nested under a booking.

## For deeper coverage

- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): resource modeling and collection/item design patterns.
- Arnaud Lauret, *The Design of Web APIs*, 2nd ed. (Manning, 2024): naming resources around client needs rather than storage schemas.
- Olaf Zimmermann, Mirko Stocker, Daniel Lübke, Uwe Zdun & Cesare Pautasso, *Patterns for API Design* (Addison-Wesley, 2022): aggregate and granularity patterns for resource boundaries.
- Cloud Native Design Patterns, [Composition](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/03-composition.md): the companion book's treatment of composing resources across service boundaries.
