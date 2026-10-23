---
title: "Versioning"
order: 14
part: "Evolution & lifecycle"
description: "Evolve the API without breaking clients: compare URI, query, header, and media-type versioning, serve an old and a new representation of the same resource, and reason about what each choice does to caching."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Compare URI, query-parameter, custom-header, and media-type (`Accept`) versioning strategies and what each does to a resource's identity.
- Implement a read-only projection like `toV1`/`_to_v1` from one source of truth instead of maintaining parallel stores.
- Explain why `Vary: Accept` is required for media-type versioning and what an RFC 9111-compliant cache does without it.
- Distinguish a reversible rename (`price` → `quote`) from a lossy shape collapse (`cargo[]` → `cargoDescription`).
- Apply `Deprecation` and `Sunset` headers to signal a version's planned retirement.

## Why this matters

Chapter 2's evolution axis named the problem without solving it: some interactions change shape constantly, and REST's independent resources are supposed to absorb that change without forcing every client to upgrade in lockstep. This chapter is where that promise gets tested against a real shape change rather than a hypothetical one. `contracts/schemas/shipping.schema.json`'s `Booking` (the shape every earlier chapter's example has served) carries `quote` (a `Money`) and `cargo` (an array of cargo items). `contracts/openapi/shipping-api-v1.yaml` freezes an older shape of the same resource, `BookingV1`, which carries `price` (the same `Money`, renamed) and `cargoDescription` (a single string, not an array). Those two differences are not cosmetic. A client's deserializer built against `price` has no field called `quote` to fall back on, and a client expecting one string where an array now arrives can't just ignore the extra structure; it has to be rewritten. That is what makes v1 → v2 a **breaking** change rather than an **additive** one: adding a new optional field to `Booking` is something an old client can shrug off entirely, because it was never looking for that field in the first place, while renaming or reshaping a field an old client already depends on breaks it the moment that client parses the response.

Breaking changes are not avoidable forever: a domain model that never renames a field or restructures an array is a domain model that stopped evolving, which is its own kind of failure. What's avoidable is forcing every client to absorb a breaking change on the same day the API ships it. Versioning is the mechanism that buys that separation: a way for an API to serve more than one shape of the same resource at once, so a client on the old contract keeps working while new clients, and clients that choose to upgrade, get the new one. This chapter's example (`examples/14-versioning/`) builds exactly that for the booking resource (one stored booking, two representations) and uses it to make four versioning strategies, and their very different relationships with HTTP caching, concrete.

## Four places to put the version

A version has to live somewhere a request carries it, and there are four conventional places to put it.

**URI versioning** puts it in the path: `/v1/bookings/{id}` versus `/v2/bookings/{id}`. It is the most visible option (the version shows up in every log line, every bookmark, every curl command a developer pastes into a support ticket) and it is the simplest to implement, because routing on a path segment is something every web framework and every piece of network infrastructure already knows how to do. Its cost is conceptual: REST's resource model says a resource has one URI, and `/v1/bookings/{id}` plus `/v2/bookings/{id}` look like two different resources even though they describe the exact same booking. A client following a `self` link from a v1 collection has no structural reason to expect that link to still resolve once v1 is retired, because the link baked the version into the resource's identity rather than treating the version as a detail of how that identity gets represented.

**Query-parameter versioning** puts it in the query string: `?version=1`. It shares URI versioning's cache-key benefit (a URL with a different query string is, by default, a different cache entry) without the identity problem, because most people read `/bookings/{id}?version=1` as one resource accessed two ways rather than two resources. The trade-off moves elsewhere: a query parameter reads as request *configuration*, the same bucket as `?limit=20` or `?sort=createdAt`, not as part of the address, which makes it easy to drop by accident when a client builds a URL by hand or a proxy strips "unrecognized" query parameters without knowing the request depends on one of them.

**Custom-header versioning** puts it in a bespoke header: `X-API-Version: 1`. It keeps the URI clean the way media-type versioning does, without requiring a vendor MIME type registration or the slightly unusual sight of `Accept: application/vnd.shipping.v1+json` in a request. The cost is that `X-API-Version` is an invention with no pre-existing HTTP semantics behind it: no cache, proxy, or piece of middleware knows what it means or that it should affect cache-key selection, so it inherits none of the infrastructure support `Accept`, `Content-Type`, and `Vary` already have built in.

**Media-type versioning** (content negotiation) puts the version in the `Accept` header using a vendor-specific media type: `Accept: application/vnd.shipping.v1+json` versus `application/vnd.shipping.v2+json`. It keeps the strongest claim to being RESTful of the four: one URI per resource, `/bookings/{id}`, with the representation negotiated the same way HTTP has always negotiated representations (language, encoding, format) rather than inventing a new axis for version specifically. The cost, covered in detail below, is that negotiated content needs an explicit signal to caches that one URL now has more than one valid cached form.

This chapter's example implements the two ends of that trade-off (URI and media-type) because they're the pair that disagrees about where version belongs: baked into identity, or negotiated on top of a stable identity. Query and header versioning are real, common strategies worth knowing, but they're each a simpler cousin of one of the two implemented here (query of URI, header of media-type) rather than a separate axis of its own, which is why the example spends its code on the comparison that teaches the most.

## URI versioning: two routes, two shapes, no ambiguity

`V2BookingResource` in Quarkus and `get_booking_v2` in FastAPI both answer `GET /v2/bookings/{id}` with the current `Booking` shape, unconditionally: no `Accept` header is consulted, because the URL already said which version the caller wants. `V1BookingResource` and `get_booking_v1` answer `GET /v1/bookings/{id}` the same way, except what comes back is `BookingV1`, projected from the identical stored booking:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/{id}")
@Produces(VersionMapper.MEDIA_TYPE_V1)
public Response getBookingV1(@PathParam("id") String id) {
    Booking booking = store.get(id);
    if (booking == null) {
        return notFound(id);
    }
    return Response.ok(VersionMapper.toV1(booking)).build();
}
```

```python
@app.get("/v1/bookings/{booking_id}")
def get_booking_v1(booking_id: str) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return JSONResponse(
        status_code=200,
        content=_to_v1(booking).model_dump(mode="json", exclude_none=True),
        media_type=MEDIA_TYPE_V1,
    )
```

Both handlers are almost suspiciously plain, and that's deliberate: URI versioning's whole appeal is that the routing layer does the disambiguation, so the handler never has to ask "which version did the caller mean?" The answer is already encoded in which method got invoked. `GET /bookings/{id}` without a version prefix also defaults to v2 in this example, and that detail matters: URI versioning and "no version pin at all" agree on what "current" means, so a client that never thinks about versioning gets the same answer as a client that explicitly asks for v2.

## Media-type versioning: one URL, negotiated on `Accept`

The unversioned `GET /bookings/{id}` implements the second strategy: the `Accept` header, not the path, picks the representation. `BookingResource.getBooking` in Quarkus and `get_booking` in FastAPI both read the header, delegate to the same v1 projection URI versioning uses, and, critically, set `Vary: Accept` on every response regardless of which version got negotiated:

{% include codetabs.html langs="Quarkus|Python" %}

```java
public Response getBooking(@PathParam("id") String id, @HeaderParam("Accept") String accept) {
    Booking booking = store.get(id);
    if (booking == null) {
        return notFound(id);
    }
    if (VersionMapper.wantsV1(accept)) {
        return Response.ok(VersionMapper.toV1(booking))
                .type(VersionMapper.MEDIA_TYPE_V1)
                .header("Vary", "Accept")
                .build();
    }
    return Response.ok(booking)
            .type(VersionMapper.MEDIA_TYPE_V2)
            .header("Vary", "Accept")
            .build();
}
```

```python
@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str, request: Request) -> JSONResponse:
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    accept_header = request.headers.get("accept")
    if _wants_v1(accept_header):
        body = _to_v1(booking)
        media_type = MEDIA_TYPE_V1
    else:
        body = booking
        media_type = MEDIA_TYPE_V2

    return JSONResponse(
        status_code=200,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type=media_type,
        headers={"Vary": "Accept"},
    )
```

Notice two things the Java and Python handlers agree on beyond the negotiation itself. First, the response's `Content-Type` always echoes the *negotiated* vendor type (`application/vnd.shipping.v1+json` or `application/vnd.shipping.v2+json`), never just whatever the client happened to send in `Accept`; a client that sent a bare `application/json` or no header at all still gets back a `Content-Type` that names exactly which shape arrived, so nothing about the response is ambiguous even when the request was unopinionated. Second, defaulting: a missing header, `*/*`, a bare `application/json`, and the explicit v2 vendor type all take the same branch, landing on v2. That mirrors URI versioning's default exactly: "no opinion" and "current version" mean the same thing on both strategies, which is what makes `/bookings/{id}` with no `Accept` header and `/v2/bookings/{id}` interchangeable in practice, even though they arrived at that shape through different mechanisms.

## The caching cost media-type versioning doesn't avoid

Chapter 2's cacheability axis treated REST's resource model as something a cache handles with almost no extra work: a `GET` on a stable URL is a natural cache key. Media-type versioning quietly breaks that assumption, because now one URL (`/bookings/{id}`) can legitimately return two different bodies depending on a request header the cache has no reason to inspect unless it's told to. A shared HTTP cache (a CDN, a reverse proxy, even a browser's own cache) keys its stored entries by URL by default. Without `Vary: Accept`, a cache that happens to serve a v1 request first can hand that exact same cached body to the very next client that asks for v2, with no error, no log line, and a `200` status that looks entirely correct. That's not a hypothetical edge case; it's the default behavior of RFC 9111-compliant caching applied to a URL the cache was never told has more than one representation.

`Vary: Accept`, present on every response from `getBooking`/`get_booking` above, is the fix: it tells any compliant cache to key its stored entries for this URL on the `Accept` header too, not just the path. Set it once, on every negotiated response, and the cache does the right thing automatically from then on. Forget it on even one response path, and the failure mode is silent data corruption from the caller's point of view: a client sees a `200` with a parseable body in the wrong shape, which looks like an application bug rather than the missing-header problem it actually is.

URI versioning sidesteps this entire class of failure by construction. `/v1/bookings/{id}` and `/v2/bookings/{id}` are different URLs, so they're different cache keys the instant they exist: no `Vary` header, no cooperating cache behavior, nothing to forget. That's the trade-off from the strategy comparison above, made concrete: media-type versioning's single-URI elegance is bought with a caching header that has to be set correctly on every response, forever, while URI versioning's two-URIs-for-one-resource awkwardness buys clean caching with no extra effort at all. Query-parameter versioning inherits URI versioning's side of this trade (a different query string is already a different cache key by default) while header versioning inherits media-type versioning's side, needing its own `Vary: X-API-Version` to avoid the identical silent-corruption failure, with the added problem that fewer caches reliably honor `Vary` on an arbitrary custom header the way they honor it on `Accept`.

## One stored booking, two representations

The detail that keeps both strategies accurate rather than a shortcut is that there is exactly one stored booking, one store, one write path. v1 is never written to directly: it's a read-only projection computed from the v2 state at request time, in both stacks, by the same logic:

{% include codetabs.html langs="Quarkus|Python" %}

```java
public static BookingV1 toV1(Booking booking) {
    String cargoDescription = booking.cargo().stream()
            .map(Cargo::description)
            .collect(Collectors.joining("; "));
    return new BookingV1(
            booking.id(),
            booking.status(),
            booking.origin(),
            booking.destination(),
            cargoDescription,
            booking.quote(),
            booking.createdAt());
}
```

```python
def _to_v1(booking: Booking) -> BookingV1:
    return BookingV1(
        id=booking.id,
        status=booking.status,
        origin=booking.origin,
        destination=booking.destination,
        cargoDescription="; ".join(item.description for item in booking.cargo),
        price=booking.quote,
        createdAt=booking.createdAt,
    )
```

`cargoDescription` is built by joining every v2 cargo item's `description` with `"; "`, and that join is lossy and one-way: v1 has no way to recover individual cargo items, their weights, or their hazardous flags from that single string. That's the real, permanent cost of carrying an old representation forward rather than a theoretical one: v1 can only ever describe what its shape had room for, and no amount of clever mapping recovers structure a string never had. A field rename like `price` → `quote` is reversible in both directions; a shape collapse like `cargo[]` → `cargoDescription` is not, which is worth internalizing as its own category of breaking change: some breaks lose a field's name, and some lose information the new shape has to actively discard to fit the old one.

Projecting from one source of truth rather than maintaining two parallel stores is also what keeps the two representations from drifting apart silently. If v1 were written independently, nothing would force a cargo item added through the v2 API to ever show up in a v1 read, and nothing would catch that gap until a v1 client complained. A single store with one projection function means a v1 read is always a live view of the same state a v2 read sees: stale in shape, never stale in data.

## Deprecation etiquette

Freezing v1 forever is rarely the actual plan: the usual intent is to retire it once enough clients have migrated to v2. HTTP has headers purpose-built for signaling that intent without pulling the endpoint out from under anyone without warning: `Deprecation`, which marks a response as coming from an endpoint scheduled for removal, and `Sunset`, which names the date after which it stops answering. Neither header is exercised in this chapter's example (the full deprecation lifecycle, and the question of what a client should do when it sees one, is a chapter of its own) but worth knowing they exist the moment a version stops being "the old one we still run" and becomes "the one we're about to shut off."

## Proof

The script brings up Quarkus on port `8094` and FastAPI on port `8014`, creates one booking per stack through the ordinary v2-shaped `POST /bookings`, then reads it back through every combination this chapter covers: `GET /v2/bookings/{id}` and `GET /v1/bookings/{id}` for the URI strategy, and `GET /bookings/{id}` with `Accept: application/vnd.shipping.v1+json` and `Accept: application/vnd.shipping.v2+json` for the media-type strategy. Every v2 body is schema-validated against `contracts/schemas/shipping.schema.json`; v1 isn't in that shared schema's `$defs`, so `verify.sh` hand-asserts its fields instead: specifically checking that a v1 response has `price` and `cargoDescription` and does **not** have `quote` or `cargo`, which is the check that catches a v1 endpoint quietly starting to leak the v2 shape. It also asserts `Vary: Accept` is present on every negotiated response. Both failure modes documented in the example's README (a v1 endpoint returning v2's shape, and a missing `Vary` header) produce a `200 OK` with valid JSON, which is exactly why a schema- and field-level check, not a status-code check, is the only thing that proves this chapter's claims hold.

{% include excalidraw.html file="14-versioning-strategies" alt="A diagram comparing four versioning strategies against one stored booking: URI versioning routing /v1/bookings and /v2/bookings to distinct cache-friendly URLs, query-parameter versioning as URI versioning's cousin via ?version=, header versioning via a custom X-API-Version header, and media-type versioning negotiating one URL /bookings/{id} via the Accept header with a required Vary: Accept response header to prevent a cache from serving the wrong representation; alongside the v1 price+cargoDescription shape versus the v2 quote+cargo[] shape produced by the same underlying resource." caption="Figure 14.1: Four versioning strategies and their caching implications." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to the choice of versioning strategy. When client diversity is high and operational constraints matter (public clients, third-party integrators, CDNs and corporate proxies that cache by URL without configuration), reach for URI versioning: it costs the least cleverness, and cacheability holds by construction with no header discipline required. When REST's one-resource-one-URI property matters more than caching ergonomics (an internal API where every response already flows through application-aware caching, or a domain where `self` links must never fork by version), reach for media-type versioning instead, and treat `Vary: Accept` as non-negotiable infrastructure, not an optional nicety, on every negotiated response. Query-parameter versioning is a reasonable URI-versioning substitute when the version reads as request configuration rather than identity; custom-header versioning is a reasonable media-type substitute when a team wants negotiation semantics without registering a vendor MIME type. Whichever strategy wins, the evolution axis still applies underneath it: version the representation, not the resource, and keep exactly one source of truth that every version projects from: forking the data itself to serve a frozen shape is how a system ends up unable to prove its old and new clients are even looking at the same booking.</p></div>

## Build, run, observe

```bash
cd examples/14-versioning && ./verify.sh
```

`verify.sh` brings up Quarkus and FastAPI with `docker compose`, creates a booking on each stack, then reads it back through both the URI (`/v1`, `/v2`) and media-type (`Accept: application/vnd.shipping.v{1,2}+json`) versioning strategies, asserting the v1 and v2 field sets and the `Vary: Accept` header. It prints `PASS` once every assertion holds for both stacks; the full run output is in `examples/14-versioning/README.md`.

## For deeper coverage

- J.J. Geewax, *API Design Patterns* (Manning, 2021): versioning strategies and API evolution.
- *Cloud Native Design Patterns*, appendix-b-versioning (same series, dedicated versioning appendix).
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022).
- [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): `Vary` and cache-key semantics.
- Lukasz Dynowski & Marcin Dulak, *Learning API Styles* (O'Reilly, 2025).
