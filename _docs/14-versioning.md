---
title: "Versioning"
order: 14
part: "Evolution & lifecycle"
description: "Evolve the API without breaking clients: compare URI, query, header and media-type versioning, serve an old and a new representation of one resource, and see what each choice does to caching."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Compare URI, query-parameter, custom-header and media-type (`Accept`) versioning and what each does to a resource's identity.
- Implement a read-only projection like `toV1`/`_to_v1` from one source of truth instead of maintaining parallel stores.
- Explain why `Vary: Accept` is required for media-type versioning and what a compliant cache does without it.
- Tell a reversible rename (`price` to `quote`) from a lossy shape collapse (`cargo[]` to `cargoDescription`).
- Apply `Deprecation` and `Sunset` headers to signal a version's retirement.

## Why this matters

`Booking` carries `quote` (a `Money`) and `cargo` (an array of items). An older shape of the same resource, `BookingV1`, carries `price` (the same `Money`, renamed) and `cargoDescription` (one string). A client built against `price` has no `quote` to fall back on, and one expecting a string can't ignore an array. That makes the change **breaking**. Adding an optional field is **additive**: an old client was never looking for it.

Breaking changes can't be avoided forever, since a model that never renames or restructures has stopped evolving. What can be avoided is forcing every client to absorb one on the day it ships. Versioning serves more than one shape of the same resource at once, so a client on the old contract keeps working while others move. One stored booking can serve two representations.

## Pattern: API Versioning

### The problem

The booking's shape changes in a way old clients can't parse. Forking the data to serve the old shape leaves two stores that drift: a cargo item added through the new API never shows up in an old read, and nobody notices until a client complains.

### The solution

**Version the representation, not the resource: keep one stored booking and project each supported version from it at read time.**

### How Quarkus and FastAPI model it

v1 is never written. It is a read-only projection of the current state:

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
    """Project the one stored (v2-shaped) booking into the frozen v1 shape.

    v1's single `cargoDescription` string is built by joining each v2
    cargo item's description -- a LOSSY, one-way projection: v1 has no way
    to recover individual cargo items, weights, or hazardous flags from
    that string alone. That's the real cost of carrying an old
    representation forward: it can only describe what its shape had room
    for.
    """
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

A v1 read is always a live view of the state a v2 read sees: stale in shape, never in data.

The two changes differ in kind. Renaming `price` to `quote` is reversible in both directions. Joining cargo descriptions with `"; "` is lossy and one-way: v1 can't recover individual items, weights or hazardous flags from a string. Carrying an old representation forward costs whatever its shape had no room for, and some breaking changes lose information, not just a name.

## Four places to put the version

| Strategy | Example | Identity | Caching |
|---|---|---|---|
| URI | `/v1/bookings/{id}` | Looks like two resources for one booking; a `self` link bakes the version in | Different URL, different cache key, nothing to configure |
| Query parameter | `?version=1` | One resource, accessed two ways | Different query string, different cache key; easy to drop by accident when a client builds a URL or a proxy strips parameters |
| Custom header | `X-API-Version: 1` | One URI | No cache knows the header; needs its own `Vary: X-API-Version`, and fewer caches honor `Vary` on a custom header |
| Media type | `Accept: application/vnd.shipping.v1+json` | One URI, version negotiated like language or format | Needs `Vary: Accept` on every response |

Query-parameter versioning is a simpler cousin of URI versioning, and header versioning of media-type versioning. URI and media-type versioning are the two worth building side by side, because they disagree on where the version belongs: in the identity, or negotiated on top of a stable identity.

### URI versioning

`GET /v2/bookings/{id}` returns the current `Booking`, and `GET /v1/bookings/{id}` returns `BookingV1`. The URL already says which version the caller wants, so the handler never consults `Accept`:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/{id}")
@Produces(VersionMapper.MEDIA_TYPE_V1)
public Response getBookingV1(@RestPath String id) {
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
    """URI versioning, v1 side: always the FROZEN BookingV1 shape (price +
    cargoDescription), regardless of any Accept header -- the URL itself is
    the version pin. Read-only: v1 is a frozen stub for teaching the
    breaking change, not a maintained write API (see README.md).
    """
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    return JSONResponse(
        status_code=200,
        content=_to_v1(booking).model_dump(mode="json", exclude_none=True),
        media_type=MEDIA_TYPE_V1,
    )
```

An unversioned `GET /bookings/{id}` defaults to v2, so a client that never thinks about versions gets the current shape.

### Media-type versioning

The unversioned `GET /bookings/{id}` reads `Accept`, uses the same projection, and sets `Vary: Accept` on every response whichever version it negotiated:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/{id}")
@Produces({ MediaType.APPLICATION_JSON, VersionMapper.MEDIA_TYPE_V1, VersionMapper.MEDIA_TYPE_V2 })
public Response getBooking(@RestPath String id, @RestHeader("Accept") String accept) {
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
    """MEDIA-TYPE (content-negotiation) versioning: the Accept header, not
    the URL, picks which representation of this ONE booking comes back.
    The response Content-Type always echoes the NEGOTIATED vendor type
    (never just whatever the client happened to send), and every response
    carries `Vary: Accept` -- a shared HTTP cache MUST treat this URL as
    having more than one representation, or it will serve a cached v1 body
    to a client that asked for v2 (see README.md).
    """
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

`Content-Type` always names the negotiated vendor type, even when the client sent a bare `application/json` or nothing, so the shape that arrived is never ambiguous. A missing header, `*/*`, `application/json` and the explicit v2 type all land on v2. "No opinion" and "current version" mean the same thing under both strategies.

### The caching cost of negotiation

A shared cache (a CDN, a reverse proxy, a browser) keys entries by URL by default. Without `Vary: Accept`, a cache that served a v1 request first hands that body to the next client asking for v2: no error, no log line, a `200` that looks correct. `Vary: Accept` tells a compliant cache (RFC 9111) to key this URL on `Accept` as well. Forget it on one response path and the client sees a parseable body in the wrong shape, which looks like an application bug.

URI versioning avoids the whole class by construction: two URLs are two cache keys. Media-type versioning's single URI is paid for with a header that must be right on every response, forever.

{% include excalidraw.html file="14-versioning-strategies" alt="A diagram comparing four versioning strategies against one stored booking: URI versioning routing /v1/bookings and /v2/bookings to distinct cache-friendly URLs, query-parameter versioning as URI versioning's cousin via ?version=, header versioning via a custom X-API-Version header, and media-type versioning negotiating one URL /bookings/{id} via the Accept header with a required Vary: Accept response header to prevent a cache from serving the wrong representation; alongside the v1 price+cargoDescription shape versus the v2 quote+cargo[] shape produced by the same underlying resource." caption="Figure 14.1: Four versioning strategies and their caching implications." %}

## Deprecation

Retiring v1 once clients have migrated is the usual plan. HTTP has headers for announcing it without pulling the endpoint out from under anyone: `Deprecation` marks a response as coming from an endpoint scheduled for removal, and `Sunset` names the date after which it stops answering. Neither is sent here. Add both once v1 stops being "the old one we still run" and becomes "the one we're about to shut off".

## When not to use it

| Situation | Strategy |
|---|---|
| Public clients, third-party integrators, CDNs and proxies that cache by URL | URI versioning: cacheable with no header discipline |
| One resource, one URI matters more than caching ergonomics (internal API, `self` links must not fork by version) | Media type, with `Vary: Accept` on every negotiated response |
| Version reads as request configuration | Query parameter |
| Negotiation semantics without a vendor MIME type | Custom header, with its own `Vary` |

Whichever wins, keep exactly one source of truth that every version projects from.

> **🤖 Explore with your agent**
>
> "In examples/14-versioning, add a `GET /v1/bookings` collection endpoint on both stacks that returns each booking through `toV1`/`_to_v1`, and make `GET /bookings` honor `Accept: application/vnd.shipping.v1+json` the same way. Set `Vary: Accept` on every response from the negotiated path, and add `Deprecation` and `Sunset` headers to every v1 response. Do not add a second store."
>
> Check: `curl -si -H 'Accept: application/vnd.shipping.v1+json' localhost:8094/bookings/<id>` shows `price` and `cargoDescription`, no `quote` or `cargo`, and a `Vary: Accept` header.

## Build, run, observe

```bash
cd examples/14-versioning && ./verify.sh
```

The script starts Quarkus on port 8094 and FastAPI on port 8014, creates a booking on each, and reads it back through `/v1`, `/v2` and both `Accept` types. It prints `PASS` when v2 bodies match the shared schema, v1 bodies have `price` and `cargoDescription` and no `quote` or `cargo`, and every negotiated response carries `Vary: Accept`.

- Make the v1 endpoint return the v2 shape. The response is still `200` with valid JSON, and the run fails on the v1 field set.
- Drop `Vary: Accept` from one negotiated branch. The body is unchanged and the run fails on the missing header.

## For deeper coverage

- J.J. Geewax, *API Design Patterns* (Manning, 2021): versioning strategies and API evolution.
- *Cloud Native Design Patterns*, appendix-b-versioning (same series, dedicated versioning appendix).
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022).
- [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): `Vary` and cache-key semantics.
- Lukasz Dynowski & Marcin Dulak, *Learning API Styles* (O'Reilly, 2025).
