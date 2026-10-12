---
title: "HTTP methods & the idempotency matrix"
order: 5
part: "Designing resources with a contract"
description: "Which methods are safe, which are idempotent, and why it matters — with an idempotent PUT and a correct DELETE built and verified in both stacks."
duration: "28 min"
---

Chapter 1 used the word "idempotent" once, in passing, about `PUT`, and promised the precise definition for later. Chapter 4 built the full `bookings` and `cargo` surface against the contract (every method the OpenAPI document declares, running in both stacks), but it built the surface with a bug in exactly that promise: a `PUT` that looked like an idempotent full replace was not, in fact, idempotent, because it reminted the ids of every `Cargo` item on every call. This chapter is where "later" arrives. It defines **safe** and **idempotent** precisely, places every method from the contract's `bookings` surface into the matrix those two properties form, and fixes the Chapter 4 bug as the chapter's centerpiece: not as a hypothetical, but as a real defect in a real example, caught by a real assertion in `verify.sh`.

## Two properties, not one

RFC 9110 §9.2 defines both terms in the same section, and the site's booking API is the clearest way to see why they're separate axes rather than two names for the same idea.

**Safe** means a method's defined semantics don't change server state when a client issues it. `GET /bookings/{id}` is safe: however many times a client fetches a booking, the booking itself is untouched. Safety is what lets a browser prefetch a link, a crawler walk a collection unattended, and a cache or proxy retry a request after a timeout without asking permission — none of that is defensible unless the method's contract promises nothing changes as a side effect of merely asking. Safety says nothing about idempotency, and idempotency says nothing about safety; they answer different questions about a method, and a method can land on any of the four combinations the matrix below lays out.

**Idempotent** means that *N* identical requests leave the resource in the same state as one request would — the state converges, not the responses. This is the clause worth reading twice: idempotency is a claim about the server's state after the fact, not about the wire-level content of what came back. `DELETE /bookings/{id}` is the sharpest illustration the booking API has. The first call returns `204` and cancels the booking. The second call, against the same id, returns `404`, because `getActive(id)` now treats a cancelled booking the same as a missing one. Two different status codes, two different response bodies — and yet `DELETE` is idempotent, because the booking's *state* is identical after both calls: gone. RFC 9110 §9.2.2 is explicit that idempotency is about "the intended effect on the server," not the response, and the DELETE row is where that distinction stops being a technicality and starts being the thing you have to internalize before the rest of the matrix makes sense.

Put the two properties together and four cells fall out. Safe methods are a subset of idempotent ones — if nothing changes, repeating the call trivially leaves the same state — so the only methods that can be safe-but-not-idempotent are none; that cell is empty by construction. The interesting cells are idempotent-but-not-safe (`PUT`, `DELETE`: they change state, but repeating them doesn't change it further) and neither (`POST`, and `PATCH` in the general case): every call is free to produce a new effect, and a client that retries blind can make things worse.

## The method matrix, with the booking operations placed

The contract's `/bookings` and `/bookings/{bookingId}` paths carry nine operations once the collection- and item-level 405s are counted. Placing each one on the safe/idempotent grid is the whole exercise:

| Method | Path | Safe? | Idempotent? | This example's behavior |
|--------|------|:-----:|:-----------:|--------------------------|
| GET | `/bookings` | yes | yes | 200, `BookingCollection` (cancelled hidden) |
| POST | `/bookings` | no | **no** | 201; two identical calls mint **two distinct** bookings (different `id`) |
| PUT | `/bookings` | no | n/a | **405** — no "whole collection" state to replace; `Allow: GET, POST` |
| GET | `/bookings/{id}` | yes | yes | 200 `Booking` / 404 `Problem` |
| HEAD | `/bookings/{id}` | yes | yes | Same status as GET, no body |
| PUT | `/bookings/{id}` | no | **yes** | 200; two identical calls converge on the **same** resource state |
| PATCH | `/bookings/{id}` | no | no* | 200; merge-patch (RFC 7396) — not idempotent in general |
| DELETE | `/bookings/{id}` | no | **yes**† | 204 then 404 — same end state every call, different status code |
| POST | `/bookings/{id}` | no | n/a | **405** — create belongs on the collection; `Allow: GET, PUT, PATCH, DELETE, HEAD` |

\* A merge-patch that sets a field to a literal value is idempotent on its own; one written to be relative to current state (easy to build in a custom `PATCH` handler, not representable in merge-patch itself) is not. The full JSON Patch story, including its own idempotency caveats, is Chapter 7's job — this chapter only needs that `PATCH` makes no blanket promise either way.

† Covered above: DELETE's status code moves (204, then 404, then 404...) while its resource state holds (gone, then still gone). That's what makes it idempotent despite looking, from the response alone, like it changes behavior on every call.

The two `n/a` cells matter as much as the filled ones. `PUT /bookings` has no sensible "whole collection, replaced" semantics (there's no single document a client could submit that means "make the entire set of bookings equal to this"), so the right answer isn't an idempotent no-op or a silent 200, it's a `405` that says so. `POST /bookings/{id}` fails for a different reason: creation is a collection-level concept, because only the collection can decide whether a new identity is even warranted, so a `POST` aimed at a specific id has nothing coherent to do. Both land in the same cell, "this verb has no business on this resource," and the example handles both the same way, which the 405 section below walks through.

{% include excalidraw.html file="05-idempotency-matrix" alt="A two-axis matrix with safe and idempotent as the dimensions, placing GET as safe and idempotent, PUT and DELETE as idempotent but not safe, POST and the item-level PATCH as neither safe nor idempotent, and the two 405 cases marked not-applicable because the method has no supported semantics on that resource." caption="Figure 5.1 — The idempotency matrix, with the booking operations placed." %}

## The trap: a PUT that looks idempotent and isn't

Chapter 4's `replaceBooking` / `replace_booking` did everything a full-replace handler is supposed to do: it took the entire request body, discarded nothing from the existing booking except what the request legitimately overwrites, and returned `200` with the new state. It also called the same cargo-item builder the create path uses (`toCargoItems` / the list comprehension around `generate_ulid()`), which mints a fresh random ULID for every `Cargo` on every invocation. That's exactly correct for `POST`: a create must never reuse an id. It's silently wrong for `PUT`, because it means two byte-for-byte identical `PUT` requests against the same booking produce two different sets of `Cargo.id` values. The booking's `origin`, `destination`, and `quote` converge across repeated calls; its cargo items don't. The contract's own operation summary, `"Replace a booking (idempotent full update)"`, was a promise the implementation wasn't keeping, and nothing in the status code or the top-level shape of the response would have revealed that.

This is worth sitting with, because "full replace" and "idempotent" feel synonymous and aren't automatically the same thing. A replace is idempotent only if *every* piece of state it touches — including state the handler generates rather than copies from the request, like a child resource's id — is a deterministic function of the input, not of when or how many times the call happens to run. A naive implementation almost always gets the top-level fields right (they come straight from the request body) and gets exactly this kind of generated child-identity wrong, because nothing about "read the request, write the response" forces you to notice that an id generator has its own hidden state: the clock and the random-number generator it reads from.

The fix is `Ulid.deterministic(seed)` / `generate_deterministic_ulid(seed)`: instead of mixing a timestamp with cryptographically random bytes, it hashes a `seed` string with SHA-256 and encodes the first 17 bytes of the digest as 26 Crockford-Base32 characters — the same alphabet and length a random ULID uses, so the shared schema's `^[0-9A-HJKMNP-TV-Z]{26}$` pattern can't tell the two apart. `replaceBooking` / `replace_booking` seed each cargo item on `"{bookingId}:{index}"`:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@PUT
@Path("/{id}")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public Response replaceBooking(@PathParam("id") String id, BookingRequest request) {
    Booking existing = store.getActive(id);
    if (existing == null) {
        return notFound(id);
    }
    Response invalid = validateBookingRequest(request);
    if (invalid != null) {
        return invalid;
    }

    // Deterministic (not random) cargo ids: PUT must be idempotent, so
    // replacing a booking with the SAME body twice has to produce the
    // SAME Cargo.id for each item both times — toCargoItems() mints a
    // fresh random id every call, which POST correctly wants but PUT
    // must not.
    List<Cargo> cargoItems = toCargoItemsForReplace(id, request.cargo());
    Booking replaced = new Booking(
            existing.id(), existing.status(), request.origin(), request.destination(),
            cargoItems, QuoteCalculator.compute(cargoItems), request.requestedPickup(),
            existing.createdAt(), nowUtc());
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
    # Cargo.id for each item both times — generate_ulid() mints a fresh
    # random id every call, which POST correctly wants but PUT must not.
    cargo_items = [
        Cargo(id=f"crg_{generate_deterministic_ulid(f'{booking_id}:{i}')}", **item.model_dump())
        for i, item in enumerate(payload.cargo)
    ]
    updated = Booking(
        id=existing.id, status=existing.status, origin=payload.origin,
        destination=payload.destination, cargo=cargo_items,
        quote=compute_quote(cargo_items), requestedPickup=payload.requestedPickup,
        createdAt=existing.createdAt, updatedAt=_now_utc(),
    )
    store.put(updated)
    return _json(200, updated)
```

The id generator itself is the part that does the real work, shown here next to the random generator it sits beside:

{% include codetabs.html langs="Quarkus|Python" %}

```java
/**
 * A deterministic, non-random "ULID-shaped" id derived from {@code seed}
 * — same seed in, same 26-char Crockford string out, every time. Used by
 * PUT (full replace), NOT by POST: an idempotent replace must converge on
 * the SAME resource state (including sub-resource ids like Cargo.id) when
 * called twice with the same body, whereas a create must mint a genuinely
 * new id every call.
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
    """A deterministic, non-random "ULID-shaped" id derived from `seed` —
    same seed in, same 26-char Crockford string out, every time. Used by
    PUT (full replace), NOT by POST: an idempotent replace must converge on
    the SAME resource state (including sub-resource ids like Cargo.id)
    when called twice with the same body, whereas a create must mint a
    genuinely new id every call.
    """
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    value = int.from_bytes(digest[:17], "big")
    return _encode(value, 26)
```

Same seed, same hash, same 26 characters, every time — `replaceBooking` calling `toCargoItemsForReplace` with `bookingId + ":" + i` and `replace_booking` building `f"{booking_id}:{i}"` are the same derivation in two languages, which is why `verify.sh`'s byte-equality assertion holds for both stacks rather than passing by coincidence on one of them. `createBooking` / `create_booking` and `addCargo` / `add_cargo` are untouched — they keep calling the random generator, because minting a fresh id on every call is exactly what a create is supposed to do. Same two functions, opposite requirement, decided by which HTTP method is asking.

## 405, with a body and an Allow header

A resource that doesn't support a method has three ways to say so, and two of them are worse than they look. Returning the framework's bare default 405 leaves the shape of that response up to whichever HTTP library is underneath, which is a problem the moment a client has to parse it the same way it parses every other error — and RESTEasy Reactive's default 405 and Starlette's default 405 don't produce the same body. Silently accepting the method and doing nothing sensible is worse: it hides a caller's mistake behind a `200` instead of surfacing it. The example picks the third option — an explicit handler, for every (method, path) combination the contract doesn't support, returning a real `Problem` body and an `Allow` header naming what *is* supported:

{% include codetabs.html langs="Quarkus|Python" %}

```java
/**
 * The collection resource doesn't support PUT (there's no single "whole
 * collection" state to replace) — 405 with an Allow header naming what it
 * DOES support, and a Problem body instead of an empty one, so a caller
 * script doesn't have to special-case this resource's error shape.
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
    "whole collection" state to replace) — 405 with an Allow header naming
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

`POST /bookings/{id}` gets the mirror-image handler with `Allow: GET, PUT, PATCH, DELETE, HEAD`, for the same reason: creation belongs on the collection, not on an id a client picked itself. `verify.sh` checks both the status code and the exact contents of the `Allow` header, so a 405 that forgot to list `POST` alongside `GET` on the collection row would fail the same way a wrong status code would.

HEAD is the one row where the two stacks needed different amounts of code, a useful check before assuming a framework "just handles" a method because another framework does. JAX-RS's method-matching algorithm falls back from an unmatched `HEAD` to the matching `@GET` method and strips the body, so RESTEasy Reactive needed zero extra code for `HEAD /bookings/{id}` — `getBooking` already covers it. FastAPI doesn't do the equivalent: bare Starlette's `Route.__init__` auto-adds `HEAD` next to a registered `GET`, but FastAPI's `APIRoute` builds its method set directly, bypassing that code path, so an un-routed `HEAD` against this app returns `405` rather than `200`. The fix is an explicit `@app.head("/bookings/{booking_id}")` handler in `python/app/main.py` that mirrors the GET's status code with an empty body — a few lines, but not zero, and a trap specifically for anyone porting a Quarkus habit to FastAPI without re-checking it.

## DELETE: 204, then 404, same resource both times

The contract marks `DELETE /bookings/{id}` as a soft-delete: the booking's `status` flips to `CANCELLED`, the record stays for audit, and it disappears from the default `GET /bookings` listing. Chapter 4 left a cancelled booking still visible through `GET /bookings/{id}` — a `200` for a resource the client had just been told was gone. This chapter tightens that: `BookingStore.getActive(id)` / `store.get_active(booking_id)` treat a cancelled booking exactly like a missing one for every single-item operation. `GET`, `PUT`, `PATCH`, `DELETE`, and the cargo sub-resource all return `404 Problem` the moment a booking is cancelled; only the raw, unused-by-any-route `get()` can still see it, which is where a real audit or undo feature would eventually reach in.

That one change is what makes the DELETE row of the matrix hold without a special case. `DELETE` on a live booking returns `204` and cancels it. `DELETE` on the same id a second time now correctly returns `404`, because `getActive` can no longer see a cancelled record as present. `GET` on that id after either `DELETE` call also returns `404`. The client's view converges on "the resource is gone" from the second call onward, which is the only sense in which `DELETE`'s idempotency claim was ever meant to hold — RFC 9110 ties idempotency to intended effect on state, and "gone" is a perfectly good state to converge on even though the HTTP status code that announces it changes from `204` to `404` along the way.

## Proof, not assertion

`verify.sh` runs the sequence that makes every claim above checkable rather than asserted: two identical `POST /bookings` calls, confirmed to mint distinct ids; two identical `PUT /bookings/{id}` calls against the same booking, diffed byte-for-byte (`updatedAt` excluded) to confirm the state converges; a `HEAD` against a live booking; a `PUT` on the collection and a `POST` on an item, each checked for `405`, a `Problem` body, and the exact `Allow` header value; and a `DELETE` → `DELETE` → `GET` sequence confirmed to land on `204`, `404`, `404`. The README documents two deliberate regressions worth running once: reverting the deterministic generator back to the random one fails the PUT-diff assertion with a visible id mismatch in the diff output, and giving `createBooking` a fixed id instead of a fresh ULID fails the very first POST-distinctness check. Both failures print the exact assertion that caught them, the same way Chapter 4's schema-drift probe did — a passing `verify.sh` here is not "the status codes looked right," it's "the state transitions this chapter defines actually hold."

```bash
cd examples/05-http-methods-idempotency
./verify.sh
```

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to method choice. When an interaction only reads, reach for a safe method — <code>GET</code> or <code>HEAD</code> — so caches, proxies, and crawlers can treat it as free to retry without asking. When an interaction writes and the client might ever retry it (a flaky connection, a timeout with an unknown outcome, a mobile client resending on reconnect), prefer an idempotent one — a full <code>PUT</code> over a creating <code>POST</code>, or a merge-patch written to set absolute values rather than apply a relative delta — because idempotency is what makes "just retry it" a safe default instead of a risk of duplicate state. Reserve <code>POST</code> and a relative <code>PATCH</code> for the cases where every call is meant to produce a new effect, and treat an implementation that merely looks idempotent — same status code, same top-level fields — as unverified until a test proves the full state, generated child ids included, actually converges across repeated calls.</p></div>
