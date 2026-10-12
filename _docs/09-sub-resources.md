---
title: "Sub-resources"
order: 9
part: "Collections at scale"
description: "When nesting a resource under a parent expresses real ownership — and when it's a trap: the caching cost of nesting, the redundant-endpoint pitfall, and how to decide."
duration: "22 min"
---

Chapter 3 introduced `/bookings/{bookingId}/cargo` as the shipping contract's one example of nesting and named the test for whether one belongs there: a sub-resource nests under a parent when the child has no meaning, no identity, and no lifecycle outside that parent. It deferred the rest of the trade-off — what nesting costs once the API is serving real traffic, and the specific way teams get it wrong even when the ownership call was right. This chapter picks that up. Nesting is still the correct shape for cargo. It is also, structurally, a decision that trades away something: a URI that encodes a parent's identity inside a child's address couples the two forever, and that coupling has a price measured in caching behavior and in how many places a client can reach the same thing.

The shape of this chapter follows the shape of the trade-off. First, the ownership test again, this time run against a case where it says no — reference data that looks nestable but isn't. Then the two costs nesting imposes even when the test says yes: cache locality and the temptation to expose the same resource at two addresses. Then a look at the real handlers behind `/bookings/{bookingId}/cargo` in the committed examples, because the contract's shape is easiest to evaluate against code that serves it. Last, a rule of thumb for how deep a nesting chain is allowed to get before it stops being a design and starts being a path copied from a database join.

## The ownership test, and where it fails

The test from Chapter 3 is short: does the child have an identity or a lifecycle apart from the parent? Cargo fails that question in the useful direction — a cargo item is created when a booking requests it, travels when the booking travels, and is never listed, searched, or referenced independent of the booking that owns it. There is no `/cargo` top-level collection in the shipping contract, and there shouldn't be one; a cargo item divorced from its booking is not a thing a client would ever ask for. Nesting it under `/bookings/{bookingId}/cargo` says exactly that in the URI: this collection exists because this booking exists, and stops existing the moment the booking does.

Run the same question against `Location` (the UN/LOCODE-identified ports and terminals a booking's `origin` and `destination` reference) and it comes out the opposite way. A location has its own identity (`USNYC`, `NLRTM`) that predates every booking that will ever reference it and outlives every booking that currently does. Thousands of bookings point at the same `USNYC` location simultaneously; none of them own it, and none of them would notice if it were fetched through a completely different booking's path. A hypothetical `/bookings/{bookingId}/locations/{unLocode}` would still technically work: the server could resolve it, return the right `Location` object, respond with a `200`, but it would be lying about ownership on every single call. It tells a client that this port belongs to this booking's address space, when in fact the reverse holds: the booking merely references a location that belongs to nobody. A client that took that nesting at face value would have no way to discover `USNYC` except by first finding some booking that happens to use it, which is backwards for data whose entire reason to exist is being looked up directly, searched, and reused across the whole system.

The tell, in practice, is usually simpler than reasoning through the aggregate boundary from scratch: ask whether a client would ever want to browse or cache this data independent of the specific parent in front of them. A port catalog is exactly the kind of thing a client wants to fetch once, cache for a day, and reuse across a hundred different bookings. The moment that's true of a piece of data, nesting it under any one parent is the wrong move regardless of how convenient it is for the one screen that happens to need it alongside a booking.

## Caching trade-offs: a nested URL caches only as well as its parent

A `GET` response is cacheable by its URL, full stop — an HTTP cache (a browser, a CDN, a reverse proxy) keys its store on the request URI, and the freshness and reuse of a cached entry depend entirely on that key being stable and shared across callers who want the same thing. Nesting a resource folds the parent's identity into that key whether or not the child's actual content has anything to do with the parent's volatility, and that has a direct cost for cargo.

`GET /bookings/bkg_01H9XZ.../cargo` is a distinct cache entry for every single booking, by construction — there's no way for a cache to recognize that the cargo items under `bkg_01H9XZ...` and the cargo items under some other booking might overlap in shape or even in content, because the URL gives it no shared key to collapse them on. That's fine here, because cargo doesn't overlap across bookings at all; each booking's cargo list is its own thing, and a cache entry scoped to one booking is exactly the granularity a client wants anyway. But the same mechanism turns punishing the moment the nested child *is* shared data. A hypothetical `/bookings/{bookingId}/locations/USNYC` produces a distinct cache entry per booking for a `Location` representation that is byte-identical no matter which booking asked for it — a hundred bookings referencing the same port populate a hundred separate cache entries holding the same bytes, each with its own expiry, each invalidated independently, and none of them shared with a client that fetched `USNYC` through a different booking or no booking at all. An independently addressable `/locations/USNYC` collapses all of that into one cache entry that every caller shares, invalidates once, and reuses regardless of which booking sent them looking for it.

There's a second layer to this cost beyond cache-entry multiplication: invalidation scope. A reverse proxy or CDN that wants to purge a stale `Location` after a port's details change has to know, and iterate, every booking URL that ever nested it (an unbounded and not reliably enumerable set), or fall back to a short TTL that undersells how rarely port data changes. Purging `/locations/USNYC` once, because it's the one URL that representation ever lives at, is a cache invalidation a reverse proxy can express directly. This is the caching argument for the ownership test stated in its own terms: nest the child only when the parent's volatility is a cost the child should legitimately inherit, because the child really does live and die with that specific parent. Cargo should inherit the booking's cache lifetime: a cargo list is stale exactly when its booking is stale, no more and no less. Reference data should not, because its own lifetime is longer and its own audience is broader than any one booking's.

## The redundant-endpoint pitfall

Related and distinct from the caching cost is a correctness trap: making the same resource reachable at two different URL shapes. It shows up most often as exactly the nesting question above, solved halfway — a team nests a resource under a parent for the convenience of browsing it alongside that parent (`/bookings/{bookingId}/cargo/{cargoId}`), then also exposes a flat, independently addressable shape (`/cargo/{cargoId}`) because some other part of the system wants to fetch a cargo item without knowing which booking it belongs to. Both endpoints resolve to the same underlying record. Nothing enforces that they return the same representation, because they're two independent handlers that happen to read the same row today.

The failure mode isn't hypothetical or slow to arrive. The two handlers get touched by two different changes over time — someone adds a field to the flat endpoint's response and forgets the nested one exists, someone fixes a validation bug in the nested `POST` and the flat equivalent (if one exists for writes too) keeps the old behavior — and the two addresses silently drift apart. A client caching one of them under its URL per the previous section now has a second, equally valid-looking address for the same conceptual resource that can return different data at the same instant. Worse, a client that discovers both shapes independently (one from a `Location` header, one from a different team's documentation) has no way to know they name the same thing unless someone tells it; REST's uniform interface promises that a URI identifies a resource, and two URIs that happen to identify the same resource without declaring that relationship violates the promise a client is entitled to rely on.

The shipping contract sidesteps this by construction rather than by discipline: there is no top-level `/cargo` collection anywhere in `contracts/openapi/shipping-api.yaml`, so there is no second shape to drift from the nested one. `POST /bookings/{bookingId}/cargo` returns a `201` with a `Location` header naming `/bookings/{bookingId}/cargo/{cargoId}` — that nested path is the cargo item's one and only canonical address, reserved by the contract even though no `GET` is wired up to read a single cargo item back directly yet. A client reads cargo today either through the list (`GET /bookings/{bookingId}/cargo`) or embedded in the parent (`GET /bookings/{bookingId}` returning the `Booking` with `cargo` inline), and both of those reads go through the same nested path prefix, so there's exactly one place in the URL space a cargo item's data can be found and exactly one place it can go stale. If a single-item read is ever added, the address it has to use already exists — nobody has to choose between two competing shapes, because only one was ever registered.

The general form of the rule: when a parent owns a child outright, resist the urge to also expose the child flat "for convenience," even when some caller would prefer not knowing the parent's id. If that caller's need is real, the right fix is a query capability on the flat side of a resource that *is* independently addressable (find a location by code, not a cargo item by id), not a second entry point into one that isn't. One canonical address per resource is worth more than the marginal convenience of a shortcut path, because the shortcut is exactly the seam where two representations quietly stop agreeing.

## The cargo sub-resource in the running example

The nested cargo collection isn't theoretical — both stacks already implement `GET` and `POST` on `/bookings/{bookingId}/cargo` as part of the pagination example from Chapter 8, and the handlers are short enough to read in full. `listCargo` doesn't do anything beyond resolving the parent and returning its embedded array; the nesting is enforced entirely by looking the booking up first and returning `404` if it doesn't exist, before cargo even enters the picture. `addCargo` does the same parent lookup, then appends the new item, recomputes the booking's quote from the updated cargo list, and returns `201` with a `Location` pointing at the newly reserved nested address:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/{id}/cargo")
@Produces(MediaType.APPLICATION_JSON)
public Response listCargo(@PathParam("id") String id) {
    Booking booking = store.get(id);
    if (booking == null) {
        return notFound(id);
    }
    return Response.ok(booking.cargo()).build();
}

@POST
@Path("/{id}/cargo")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public Response addCargo(@PathParam("id") String id, CargoRequest request) {
    Booking booking = store.get(id);
    if (booking == null) {
        return notFound(id);
    }
    // validation omitted here — see examples/08-pagination for the full method
    Cargo cargo = new Cargo("crg_" + Ulid.generate(), request.description(), request.type(),
            request.dimensions(), request.hazardousOrDefault());
    List<Cargo> newCargoList = new ArrayList<>(booking.cargo());
    newCargoList.add(cargo);
    Money quote = QuoteCalculator.compute(newCargoList);

    Booking updated = new Booking(
            booking.id(), booking.status(), booking.origin(), booking.destination(),
            newCargoList, quote, booking.requestedPickup(), booking.createdAt(), nowUtc());
    store.put(updated);

    return Response.status(Response.Status.CREATED)
            .header("Location", "/bookings/" + id + "/cargo/" + cargo.id())
            .entity(cargo)
            .build();
}
```

```python
@app.get("/bookings/{booking_id}/cargo")
def list_cargo(booking_id: str) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return JSONResponse(
        status_code=200,
        content=[c.model_dump(mode="json", exclude_none=True) for c in booking.cargo],
    )


@app.post("/bookings/{booking_id}/cargo")
def add_cargo(booking_id: str, payload: CargoRequest) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    cargo = Cargo(id=f"crg_{generate_ulid()}", **payload.model_dump())
    new_cargo_list = [*booking.cargo, cargo]
    updated = booking.model_copy(update={
        "cargo": new_cargo_list,
        "quote": compute_quote(new_cargo_list),
        "updatedAt": _now_utc(),
    })
    store.put(updated)
    return _json(201, cargo, headers={"Location": f"/bookings/{booking_id}/cargo/{cargo.id}"})
```

Neither handler reaches for a separate `CargoStore` or a second identity space — the booking's in-memory record is the single source of truth, and the nested path is a view onto one field of it, not a parallel resource with its own storage to keep in sync. That's the ownership test showing up in the implementation, not just the URL: there's only one place this data lives, which is exactly what makes the one-canonical-address property from the previous section free rather than something the handlers have to work to maintain. Both `addCargo` and `add_cargo` also recompute the booking's `quote` on every addition, which is the caching argument from the earlier section in miniature — adding a cargo item changes something about the parent too, so a cache entry keyed on the parent's URL is exactly the granularity that needs to go stale, and a cache entry keyed on the cargo item alone would miss that the quote moved.

No new example ships with this chapter — the contract and the running service already exist from Chapter 8. Exercise the sub-resource directly against `examples/08-pagination` (or the earlier `examples/04-contract-first`, which has the same two endpoints without the pagination additions):

```bash
cd examples/08-pagination
./verify.sh
```

`verify.sh` creates a booking, lists its cargo, adds a second item, and asserts the `201` response's `Location` header matches the nested shape above on both stacks — the same behavioral check this site uses everywhere, not a glance at the status code alone.

## How deep is too deep

Cargo nests one level under booking, and that's as deep as this contract's nesting goes. That's not an accident of a small domain — it's close to a hard ceiling for any domain: a URL path that nests three or more levels of ownership (`/a/{aId}/b/{bId}/c/{cId}`) almost always means the design copied a foreign-key chain out of a database schema rather than asking the ownership question at each level independently. Even when every individual link in that chain is a sound ownership relationship, the combination creates a client that has to hold three identifiers just to address the innermost thing, a cache key that goes stale whenever any of the three ancestors change, and a URL that breaks the moment any one of the three resources gets exposed independently later — which eventually, every reference-shaped node in a deep chain does.

The practical fix when a domain seems to demand three levels is almost always to flatten the innermost one back out to its own top-level collection, addressed by its own identity, with a back-reference field pointing at its true owner instead of carrying that owner in the path. A `Leg` belonging to a `Route` belonging to a confirmed `Booking` could in principle live at `/bookings/{bookingId}/routes/{routeId}/legs/{legId}`; it's a better design to give `Route` its own top-level address once it's introduced in Chapter 12, because a route — unlike cargo — is the kind of thing a carrier-side system wants to query and update independent of which booking it currently serves. One level of nesting, chosen by the ownership test and re-checked against the caching and redundant-endpoint costs above, is the right default for this contract and most contracts like it; reaching for a second or third level should feel like a decision that needs its own justification, not a default extension of the same pattern that worked once.

{% include excalidraw.html file="09-sub-resources" alt="Two parallel URL trees contrasted: on the left, Booking owning Cargo at /bookings/{id}/cargo, shown as a solid containment arrow because cargo has no identity outside its booking, with a single canonical address and a cache key scoped correctly to the parent; on the right, Location data shown NOT nested under any booking, reachable instead at its own top-level /locations/{unLocode} address shared and cached across every booking that references it, with a crossed-out hypothetical /bookings/{id}/locations/{unLocode} path and a second crossed-out flat /cargo/{cargoId} path illustrating the redundant-endpoint pitfall of the same resource reachable at two drifting addresses." caption="Figure 9.1 — Nest when the parent owns the child; don't nest shared reference data." %}

<div class="callout callout--warn"><p class="callout__title">Anti-pattern</p><p>Exposing the same resource at two URL shapes — a nested nicety for one caller's convenience alongside a flat address for another's — looks harmless at launch because one handler currently backs both. It stops being harmless the first time either shape is edited without the other, and nothing in the system catches the drift because nothing declared the two addresses were ever supposed to agree. If two callers truly need different access patterns to the same data, give the data one canonical address and let both callers reach it through that address, rather than registering a second entry point into the same resource.</p></div>

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to nesting. Nest a collection under a parent only when the child fails the independence test — no identity, no lifecycle, no cacheable audience apart from that one parent — exactly as cargo fails it under booking. The moment a client would reasonably want to fetch, search, or cache the child without first knowing its parent, as with locations or any future reference data, give it its own top-level address instead, even if that means one more root-level collection in the contract. Keep every resource reachable at exactly one canonical URL: a nested shape and a flat shape for the same data are two independent surfaces to keep in sync, and the redundant one will eventually drift. And treat anything past one level of nesting as a design that needs its own justification — a chain of two or three owned-by relationships is a signal to flatten the innermost resource back to a top-level collection with a back-reference, not to extend the path another segment.</p></div>
