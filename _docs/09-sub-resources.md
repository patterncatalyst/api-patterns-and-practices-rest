---
title: "Sub-resources"
order: 9
part: "Collections at scale"
description: "When nesting a resource under its parent expresses real ownership and when it's a trap: the caching cost, the redundant-endpoint pitfall, and how deep is too deep."
duration: "22 min"
---

## Learning objectives

By the end of this chapter you can:

- Apply the ownership test (does the child have identity, lifecycle or a cacheable audience apart from its parent?) to choose between `/bookings/{bookingId}/cargo` and a top-level address.
- Explain how nesting folds a parent's identity into a cache key, and why that multiplies cache entries for shared reference data like `Location`.
- Recognize the redundant-endpoint anti-pattern, where one resource is reachable at a nested and a flat URL, and why the two addresses drift.
- Enforce ownership in a handler with a single parent lookup instead of a parallel store.
- Flatten the innermost resource when a path nests three or more levels.

## Why this matters

Cargo lives at `/bookings/{bookingId}/cargo` because a cargo item has no meaning, identity or lifecycle outside its booking. That is the right shape, and it still costs something. A URI that encodes the parent's identity in the child's address couples the two for good, and the price shows up in cache behavior and in how many places a client can reach the same thing.

## The ownership test, and where it fails

Does the child have an identity or lifecycle apart from the parent? Cargo answers no: it's created when a booking requests it, travels with the booking, and is never listed or searched independently. The shipping contract has no top-level `/cargo` collection, and shouldn't. Nesting says so in the URI: the collection exists because this booking exists.

`Location` (the UN/LOCODE ports and terminals that `origin` and `destination` reference) answers yes. `USNYC` and `NLRTM` predate every booking that references them and outlive them. Thousands of bookings point at `USNYC` and none own it. A hypothetical `/bookings/{bookingId}/locations/{unLocode}` would resolve and return the right object, but it misstates ownership on every call, and a client taking it at face value could find `USNYC` only by first finding a booking that uses it.

The practical tell: would a client browse or cache this data independent of the parent in front of it? A port catalog is fetched once, cached for a day and reused across a hundred bookings. Data like that doesn't nest, however convenient it is for the one screen that shows it beside a booking.

## Caching: a nested URL caches only as well as its parent

An HTTP cache keys on the request URI. Nesting folds the parent's identity into that key whether or not the child's content depends on the parent.

`GET /bookings/bkg_01H9XZ.../cargo` is a separate cache entry per booking. For cargo that's the right granularity, because no two bookings share cargo. For shared data it's punishing: `/bookings/{bookingId}/locations/USNYC` yields one entry per booking for a byte-identical `Location`, each with its own expiry and invalidation. A top-level `/locations/USNYC` is one entry that every caller shares.

Invalidation has the same shape. To purge a stale `Location`, a proxy or CDN would have to enumerate every booking URL that ever nested it, an unbounded set, or fall back to a short TTL that undersells how rarely port data changes. With one address, it purges one URL.

So nest a child only when it should inherit the parent's volatility. A cargo list is stale exactly when its booking is. Reference data has a longer life and a wider audience than any one booking.

## The redundant-endpoint pitfall

The second trap is making one resource reachable at two URL shapes. A team nests cargo under its booking for browsing (`/bookings/{bookingId}/cargo/{cargoId}`), then adds a flat `/cargo/{cargoId}` because another system wants an item without knowing the booking. Both resolve to the same record, but they are two handlers, and nothing forces them to return the same representation.

They drift. One change adds a field to the flat response and forgets the nested one; another fixes a validation bug in the nested `POST` and leaves the flat write on the old behavior. A client that cached one address now holds a second, equally valid-looking address that can return different data at the same instant. A client that found both shapes from different sources can't tell they name the same thing.

The shipping contract avoids this by construction: `contracts/openapi/shipping-api.yaml` has no top-level `/cargo`. `POST /bookings/{bookingId}/cargo` returns `201` with a `Location` header naming `/bookings/{bookingId}/cargo/{cargoId}`, the item's single canonical address, even though no single-item `GET` is wired yet. Clients read cargo through the list or embedded in `GET /bookings/{bookingId}`, both under the same prefix. If a single-item read is added, its address already exists.

When a parent owns a child outright, don't also expose the child flat for convenience. If a caller needs to find a cargo item without the booking, add a query capability on a collection that is independently addressable, not a second entry point into one that isn't.

## The cargo sub-resource in code

Both stacks implement `GET` and `POST` on `/bookings/{bookingId}/cargo`. Each handler looks up the parent first and returns `404` if it's missing; request validation runs before the handler (`@Valid` on Quarkus, the Pydantic model on FastAPI). `addCargo` then appends the item, recomputes the booking's quote and returns `201` with the nested `Location`:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/{id}/cargo")
@Produces(MediaType.APPLICATION_JSON)
public Response listCargo(@RestPath String id) {
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
public Response addCargo(@RestPath String id, @Valid CargoRequest request) {
    Booking booking = store.get(id);
    if (booking == null) {
        return notFound(id);
    }

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

There is no `CargoStore` and no second identity space. The booking record is the single source of truth, and the nested path is a view onto one of its fields. That is why one canonical address costs nothing to maintain. Recomputing `quote` on every addition shows the caching argument in miniature: adding cargo changes the parent, so a cache entry keyed on the parent's URL is the right unit to go stale, and an entry keyed on the cargo item alone would miss that the quote moved.

## How deep is too deep

Cargo nests one level, and that is close to a ceiling for any domain. A path like `/a/{aId}/b/{bId}/c/{cId}` usually means a foreign-key chain was copied from a database schema. Even when each link is a sound ownership relationship, the client must hold three identifiers to address the innermost thing, its cache key goes stale when any ancestor changes, and the URL breaks the day one of the three is exposed independently, as reference-shaped nodes eventually are.

When a domain seems to need three levels, flatten the innermost resource to a top-level collection addressed by its own identity, with a back-reference field to its owner. A `Leg` of a `Route` of a confirmed `Booking` could live at `/bookings/{bookingId}/routes/{routeId}/legs/{legId}`, but a route is something a carrier-side system queries and updates independent of its booking, so it gets its own address.

{% include excalidraw.html file="09-sub-resources" alt="Two URL trees: Booking owns Cargo at /bookings/{id}/cargo with one canonical address, while Location lives at its own top-level /locations/{unLocode}, shared and cached across bookings. Crossed-out /bookings/{id}/locations/{unLocode} and /cargo/{cargoId} paths show the nesting mistake and the redundant-endpoint pitfall." caption="Figure 9.1: Nest when the parent owns the child; don't nest shared reference data." %}

## Decision rules

| Question | Answer |
| --- | --- |
| Does the child lack identity, lifecycle and an audience apart from one parent? | Nest it, as cargo under a booking |
| Would a client fetch, search or cache it without knowing the parent? | Give it a top-level address, as with locations |
| Is it already reachable at one URL? | Don't add a second; one canonical address per resource |
| Is the path three or more levels deep? | Flatten the innermost resource and add a back-reference |

> **Anti-pattern:** a nested nicety for one caller alongside a flat address for another looks harmless while one handler backs both. It stops being harmless the first time either shape is edited alone, and nothing catches the drift because nothing declared the addresses must agree.

> **🤖 Explore with your agent**
>
> "In `examples/08-pagination`, review `listCargo` and `addCargo` (Quarkus `BookingResource.java`, FastAPI `app/main.py`) with the ownership test. Then add a single-item `GET /bookings/{bookingId}/cargo/{cargoId}` on both stacks that returns the same `Cargo` body as the list, with `404` for an unknown booking or cargo id, and no flat `/cargo` route."
>
> Check: a `GET` on the `Location` returned by `POST /bookings/{bookingId}/cargo` returns `200` with the same `Cargo`, and `GET /cargo/{cargoId}` returns `404`.

## Build, run, observe

No separate example ships for this topic. The same handlers serve `examples/04-contract-first` (ports `8080` and `8000`) and `examples/08-pagination` (ports `8088` and `8008`):

```bash
cd examples/04-contract-first && ./verify.sh
```

The script posts a cargo item to a booking on each stack and passes when the response is `201` with a `Location` header and a schema-valid `Cargo` body. To see the nested shape, start the stack with `docker compose up --build` and post one item by hand:

```bash
curl -si -X POST -H 'Content-Type: application/json' \
  -d '{"description":"Spare parts","type":"GENERAL","dimensions":{"weightKg":500,"volumeM3":1.0},"hazardous":false}' \
  http://localhost:8080/bookings/<bookingId>/cargo
```

Experiments:

- Post to an unknown booking id. Both stacks return `404` with a `Problem` body before any cargo is touched.
- Delete the `Location` header from `addCargo` or `add_cargo`. The `verify.sh` run fails on that stack's cargo step.
- Request `GET /cargo/{cargoId}` on either stack. It returns `404`: there is no flat route to drift from the nested one.

## For deeper coverage

- *Composition* ([Cloud Native Design Patterns](https://github.com/patterncatalyst/cloud-native-design-patterns)): where aggregation belongs, and how resource boundaries are decided when one API fans out to several back-ends.
- *Caching Patterns* (Appendix L, [Cloud Native Design Patterns](https://github.com/patterncatalyst/cloud-native-design-patterns)): cache-aside and invalidation-scope trade-offs that extend the caching-cost argument against nesting shared reference data.
- [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): the URL-keyed cache semantics behind why a nested address caches only as well as its parent.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): resource relationship and association patterns.
