---
title: "HTTP methods & the idempotency matrix"
order: 5
part: "Designing resources with a contract"
description: "Which methods are safe, which are idempotent and why it matters, with an idempotent PUT and a correct DELETE built in both stacks."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Define "safe" and "idempotent" per RFC 9110 §9.2, and explain why they are independent axes.
- Place every `/bookings` and `/bookings/{bookingId}` operation on the safe/idempotent matrix, including the two `405` "not applicable" cells.
- Spot a `PUT` that looks idempotent but isn't (one that mints a fresh random `Cargo.id` on every call) and fix it with a deterministic id derived from a seed.
- Return a correct `405` with an `Allow` header and a `Problem` body for an unsupported method and path.
- Explain why `DELETE /bookings/{id}` is idempotent even though its status code changes across repeated calls (`204`, then `404`, then `404`).

## Why this matters

A client that times out doesn't know whether the server acted. Whether it can safely retry depends on the method, and that is what safe and idempotent describe. The booking API as first built has a bug in exactly this promise: its `PUT` looks like an idempotent full replace but reminted the id of every `Cargo` item on every call. Safe and idempotent are defined below, each method is placed on the matrix they form, and the bug is fixed.

## Two properties, not one

**Safe** means a method's defined semantics don't change server state. `GET /bookings/{id}` is safe: however often a client fetches a booking, the booking is untouched. Safety lets a browser prefetch a link, a crawler walk a collection unattended, and a proxy retry after a timeout without asking permission.

**Idempotent** means *N* identical requests leave the resource in the same state as one request. The state converges, not the responses. `DELETE /bookings/{id}` shows the difference. The first call returns `204` and cancels the booking. The second returns `404`, because a cancelled booking now reads as missing. The status codes and bodies differ, yet the state after both calls is the same: gone. RFC 9110 §9.2.2 ties idempotency to "the intended effect on the server," not to the response.

Every safe method is idempotent, since nothing changes to repeat. That leaves three populated cells:

| | Safe | Not safe |
|---|---|---|
| **Idempotent** | `GET`, `HEAD` | `PUT`, `DELETE` |
| **Not idempotent** | none | `POST`, and `PATCH` in general |

A client that retries a `POST` or a relative `PATCH` blind can make things worse.

## The method matrix

The contract's two booking paths carry nine operations once the two `405` cases are counted:

| Method | Path | Safe | Idempotent | Behavior |
|--------|------|:----:|:----------:|----------|
| GET | `/bookings` | yes | yes | 200, `BookingCollection` (cancelled hidden) |
| POST | `/bookings` | no | **no** | 201; two identical calls mint **two distinct** bookings |
| PUT | `/bookings` | no | n/a | **405**: no "whole collection" state to replace; `Allow: GET, POST` |
| GET | `/bookings/{id}` | yes | yes | 200 `Booking` or 404 `Problem` |
| HEAD | `/bookings/{id}` | yes | yes | Same status as GET, no body |
| PUT | `/bookings/{id}` | no | **yes** | 200; two identical calls converge on the **same** state |
| PATCH | `/bookings/{id}` | no | no* | 200; merge-patch (RFC 7396) |
| DELETE | `/bookings/{id}` | no | **yes** | 204 then 404: same end state, different status |
| POST | `/bookings/{id}` | no | n/a | **405**: create belongs on the collection; `Allow: GET, PUT, PATCH, DELETE, HEAD` |

\* A merge-patch that sets a field to a literal value is idempotent. A custom `PATCH` written relative to current state, such as "add 5 kg", is not. `PATCH` makes no blanket promise either way.

`PUT /bookings` has no sensible semantics, because no single document means "make the whole set of bookings equal to this". `POST /bookings/{id}` fails because only the collection can decide whether a new identity is warranted. Both are "this verb has no business on this resource", and both get a `405`.

{% include excalidraw.html file="05-idempotency-matrix" alt="A two-axis matrix with safe and idempotent as the dimensions, placing GET as safe and idempotent, PUT and DELETE as idempotent but not safe, POST and the item-level PATCH as neither safe nor idempotent, and the two 405 cases marked not-applicable because the method has no supported semantics on that resource." caption="Figure 5.1: The idempotency matrix, with the booking operations placed." %}

## A PUT that looks idempotent and isn't

The first `replaceBooking` took the whole request body, kept what the request doesn't overwrite, and returned `200` with the new state. It also called the cargo-item builder that `POST` uses, which mints a random ULID for every `Cargo`. That is right for a create, which must never reuse an id, and wrong for a `PUT`. Two byte-identical `PUT` requests produced two different sets of `Cargo.id` values. `origin`, `destination` and `quote` converged; the cargo items didn't. The operation's own summary, "Replace a booking (idempotent full update)", promised something the code didn't deliver, and neither the status code nor the top-level shape would reveal it.

A replace is idempotent only if every piece of state it touches is a deterministic function of the input, including state the handler generates, such as a child's id. The id generator carries hidden state: the clock and a random source.

The fix hashes a seed with SHA-256 and encodes the first 17 bytes of the digest as 26 Crockford-Base32 characters. That is the same alphabet and length a random ULID uses, so the schema's `^[0-9A-HJKMNP-TV-Z]{26}$` pattern can't tell them apart. Each cargo item is seeded on `"{bookingId}:{index}"`:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@PUT
@Path("/{id}")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public Response replaceBooking(@RestPath String id, @Valid BookingRequest request) {
    Booking existing = store.getActive(id);
    if (existing == null) {
        return notFound(id);
    }

    // Deterministic (not random) cargo ids: PUT must be idempotent, so
    // replacing a booking with the SAME body twice has to produce the
    // SAME Cargo.id for each item both times; toCargoItems() below
    // mints a fresh random id every call, which POST correctly wants
    // but PUT must not.
    List<Cargo> cargoItems = toCargoItemsForReplace(id, request.cargo());
    Booking replaced = new Booking(
            existing.id(),
            existing.status(),
            request.origin(),
            request.destination(),
            cargoItems,
            QuoteCalculator.compute(cargoItems),
            request.requestedPickup(),
            existing.createdAt(),
            nowUtc());
    store.put(replaced);
    return Response.ok(replaced).build();
}
```

```python
@app.put("/bookings/{booking_id}")
def replace_booking(booking_id: str, payload: BookingRequest) -> JSONResponse:
    existing = store.get_active(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")

    # Deterministic (not random) cargo ids: PUT must be idempotent, so
    # replacing a booking with the SAME body twice has to produce the SAME
    # Cargo.id for each item both times; generate_ulid() below mints a
    # fresh random id every call, which POST correctly wants but PUT must
    # not.
    cargo_items = [
        Cargo(id=f"crg_{generate_deterministic_ulid(f'{booking_id}:{i}')}", **item.model_dump())
        for i, item in enumerate(payload.cargo)
    ]
    updated = Booking(
        id=existing.id,
        status=existing.status,
        origin=payload.origin,
        destination=payload.destination,
        cargo=cargo_items,
        quote=compute_quote(cargo_items),
        requestedPickup=payload.requestedPickup,
        createdAt=existing.createdAt,
        updatedAt=_now_utc(),
    )
    store.put(updated)
    return _json(200, updated)
```

The generator is `Ulid.deterministic(seed)` on Quarkus and `generate_deterministic_ulid(seed)` on FastAPI:

{% include codetabs.html langs="Quarkus|Python" %}

```java
/**
 * A deterministic, non-random "ULID-shaped" id derived from {@code seed}:
 * same seed in, same 26-char Crockford string out, every time.
 *
 * Used by PUT (full replace), NOT by POST: an idempotent replace must
 * converge on the SAME resource state (including sub-resource ids like
 * Cargo.id) when called twice with the same body, whereas a create must
 * mint a genuinely new id every call. Seeding on "{bookingId}:{index}"
 * gives each cargo slot in a given booking's replace a stable identity
 * across repeated identical PUTs, without needing real persistence.
 */
public static String deterministic(String seed) {
    try {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(seed.getBytes(StandardCharsets.UTF_8));
        // 26 Crockford chars encode 130 bits; 17 bytes (136 bits) is the
        // smallest whole number of hash bytes that covers that.
        byte[] truncated = Arrays.copyOf(hash, 17);
        BigInteger value = new BigInteger(1, truncated);
        return encodeBigInteger(value, 26);
    } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException("SHA-256 is a required JDK algorithm", e);
    }
}
```

```python
def generate_deterministic_ulid(seed: str) -> str:
    """A deterministic, non-random "ULID-shaped" id derived from `seed`:
    same seed in, same 26-char Crockford string out, every time.

    Used by PUT (full replace), NOT by POST: an idempotent replace must
    converge on the SAME resource state (including sub-resource ids like
    Cargo.id) when called twice with the same body, whereas a create must
    mint a genuinely new id every call. Mirrors
    ../quarkus/.../Ulid.java#deterministic bit for bit (SHA-256, first 17
    hash bytes -> 26 Crockford chars).
    """
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    value = int.from_bytes(digest[:17], "big")
    return _encode(value, 26)
```

Same seed, same hash, same 26 characters. `bookingId + ":" + i` and `f"{booking_id}:{i}"` are one derivation in two languages, so both stacks converge on byte-identical state rather than one passing by coincidence. `POST /bookings` and the add-cargo operation keep the random generator, because a create must mint a new id every call. The same two functions serve opposite requirements, chosen by the method.

## 405 with a body and an Allow header

A resource has three ways to refuse a method. The framework default leaves the response shape to the HTTP library, and RESTEasy Reactive's 405 and Starlette's differ. Silently accepting the method hides the caller's mistake behind a `200`. The third option is an explicit handler for every unsupported method and path pair, returning a `Problem` body and an `Allow` header naming what is supported. That keeps the error shape uniform across the API and tells the client what to do instead.

{% include codetabs.html langs="Quarkus|Python" %}

```java
/**
 * The collection resource doesn't support PUT (there's no single
 * "whole collection" state to replace): 405 with an {@code Allow}
 * header naming what it DOES support, and a {@code Problem} body
 * instead of an empty one, so a caller script doesn't have to special-
 * case this resource's error shape.
 */
@PUT
public Response replaceCollectionNotAllowed() {
    return methodNotAllowed(ALLOW_COLLECTION, "PUT is not supported on the /bookings collection; "
            + "PUT a specific item at /bookings/{id} instead");
}
```

```python
@app.put("/bookings")
def replace_collection_not_allowed() -> JSONResponse:
    """The collection resource doesn't support PUT (there's no single
    "whole collection" state to replace): 405 with an Allow header naming
    what it DOES support, and a Problem body instead of an empty one, so a
    caller script doesn't have to special-case this resource's error shape.
    """
    return _problem(
        405,
        "Method Not Allowed",
        "PUT is not supported on the /bookings collection; PUT a specific item at /bookings/{id} instead",
        headers={"Allow": _ALLOW_COLLECTION},
    )
```

`PUT /bookings` answers `405` with `Allow: GET, POST`. `POST /bookings/{id}` gets the mirror-image handler with `Allow: GET, PUT, PATCH, DELETE, HEAD`, because creation belongs on the collection, not on an id the client picked. The `Allow` value is part of the contract: a collection 405 that forgets `POST` is as wrong as a wrong status code.

`HEAD` needed different amounts of code. JAX-RS falls back from an unmatched `HEAD` to the matching `@GET` method and strips the body, so Quarkus needed none. FastAPI doesn't: its routes build their method set directly, bypassing the code in bare Starlette that adds `HEAD` next to `GET`, so an unrouted `HEAD` returns `405`. FastAPI needs an explicit `@app.head("/bookings/{booking_id}")` handler that mirrors the GET status with an empty body.

## DELETE: 204, then 404

`DELETE /bookings/{id}` is a soft delete. The booking's `status` flips to `CANCELLED`, the record stays for audit, and it leaves the default `GET /bookings` listing. A cancelled booking would otherwise still answer `GET /bookings/{id}` with `200`, a resource the client had just been told was gone. So `getActive(id)` and `get_active(booking_id)` treat a cancelled booking as missing for every single-item operation. `GET`, `PUT`, `PATCH`, `DELETE` and the cargo sub-resource all return `404 Problem` once a booking is cancelled.

That makes the `DELETE` row hold without a special case. The first call returns `204` and cancels. The second returns `404`, and so does a `GET` after either call. The client's view converges on "gone", the state RFC 9110 means by intended effect, even though the announcing status moves from `204` to `404`.

## Choosing a method

| Interaction | Use | Why |
|---|---|---|
| Reads only | `GET` or `HEAD` | Caches, proxies and crawlers can retry freely |
| Writes, and the client may retry | `PUT`, or a merge-patch that sets absolute values | Retry is a safe default |
| Every call must produce a new effect | `POST`, or a relative `PATCH` | Pair with an idempotency key if retries matter |

An implementation that only looks idempotent (same status, same top-level fields) is unverified until the full state, generated child ids included, is compared across repeated calls.

> **🤖 Explore with your agent**
>
> "In `examples/05-http-methods-idempotency/`, add `PUT /bookings/{id}/cargo/{cargoId}` on both the Quarkus and FastAPI stacks so that sending the same body twice returns identical bodies. Derive any generated id from a seed, not the clock or a random source, and answer `405` with an `Allow` header for `POST` on that path."
>
> Check: send the same `PUT` twice with `curl` and run `diff` on the two response bodies, ignoring `updatedAt`. The diff is empty.

## Build, run, observe

```bash
cd examples/05-http-methods-idempotency && ./verify.sh
```

The script starts both stacks and runs the method sequence against each. It prints `PASS` once two identical `POST` calls mint distinct ids, two identical `PUT` calls converge on identical state, unsupported methods return `405` with the correct `Allow` header, and a repeated `DELETE` yields `204`, `404`, `404`. `examples/05-http-methods-idempotency/README.md` has the full output.

Experiments:

- Switch the replace path back to the random generator. The `PUT` comparison fails with an id mismatch in the diff.
- Give `createBooking` a fixed id instead of a fresh ULID. The first `POST` distinctness check fails.

## For deeper coverage

- [RFC 9110 §9.2, HTTP Semantics: Common Method Properties](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2): the authoritative definitions of safe and idempotent.
- Gough, Bryant & Auburn, *Mastering API Architecture* (O'Reilly, 2022): method semantics and idempotency in the context of a full API architecture.
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): idempotent and safe method patterns, including retry safety.
- Cloud Native Design Patterns, [Appendix A: Protocols](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/14-appendix-a-protocols.md): the companion book's protocol-level reference for HTTP method semantics.
