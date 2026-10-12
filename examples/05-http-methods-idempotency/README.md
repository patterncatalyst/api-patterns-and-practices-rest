# Ch5 — HTTP methods & the idempotency matrix

Extends the [Ch4 contract-first anchor](../04-contract-first/) — same
shipping/cargo Booking resource, same `contracts/openapi/shipping-api.yaml` +
`contracts/schemas/shipping.schema.json`, same Quarkus (`quarkus/`, port
8080) + FastAPI (`python/`, port 8000) stacks, same `verify.sh` harness via
`examples/_lib/`. This chapter adds the full HTTP method matrix on
`/bookings` and `/bookings/{id}`, explicit `405 Method Not Allowed` for
methods a resource doesn't support, and proves — not just asserts — what
"safe" and "idempotent" mean for each method.

## Run it

```bash
cd examples/05-http-methods-idempotency
./verify.sh
```

Brings both services up with `docker compose`, waits for health, drives the
method matrix against `localhost:8080` (Quarkus) and `localhost:8000`
(FastAPI), schema-validates every response, and tears the stack down again.
Prints `PASS` only if every assertion holds for **both** stacks.

```bash
docker compose --profile observability up --build   # + Grafana LGTM, opt-in
```

## The method × safe/idempotent matrix

"Safe" means a method must not change server state (so it's free to retry,
cache, or prefetch). "Idempotent" means N identical calls leave the server
in the **same state** as 1 call — it says nothing about whether the
responses are byte-identical, only that the end state converges.

| Method | Path              | Safe? | Idempotent? | This example's behavior |
|--------|-------------------|:-----:|:-----------:|--------------------------|
| GET    | `/bookings`       | yes   | yes         | 200, `BookingCollection` (cancelled hidden) |
| POST   | `/bookings`       | no    | **no**      | 201; two identical calls mint **two distinct** bookings (different `id`) |
| PUT    | `/bookings`       | no    | n/a         | **405** — no "whole collection" state to replace; `Allow: GET, POST` |
| GET    | `/bookings/{id}`  | yes   | yes         | 200 `Booking` / 404 `Problem` |
| HEAD   | `/bookings/{id}`  | yes   | yes         | Same status as GET, no body |
| PUT    | `/bookings/{id}`  | no    | **yes**     | 200; two identical calls converge on the **same** resource state |
| PATCH  | `/bookings/{id}`  | no    | no*         | 200; merge-patch (RFC 7396) — not idempotent in general (full JSON Patch + its idempotency caveats land in Ch7) |
| DELETE | `/bookings/{id}`  | no    | **yes**†    | 204 then 404 — same END STATE every call, different status code |
| POST   | `/bookings/{id}`  | no    | n/a         | **405** — create belongs on the collection; `Allow: GET, PUT, PATCH, DELETE, HEAD` |

\* A merge-patch that sets a field to a literal value (`{"requestedPickup":
"2026-03-01"}`) is idempotent; one that's relative to current state (not
representable in merge-patch, but easy to write in a custom `PATCH` handler)
is not. This chapter doesn't need the distinction — Ch7 does.

† DELETE is the one row worth a second look: its *status code* is not
idempotent (204, then 404, then 404, ...) but its *resource state* is (gone,
then still gone, then still gone, ...). RFC 9110 §9.2.2 defines idempotency
in terms of the intended effect on server state, not the response — DELETE
qualifies.

## Why PUT needed a real fix, not just an assertion

The Ch4 anchor's `replaceBooking` / `replace_booking` minted a **fresh
random ULID** for every `Cargo` item on every `PUT`, inherited unchanged
from the create path. That's correct for POST (every create must get a new
id) and silently wrong for PUT: two byte-for-byte identical `PUT` bodies
produced two different `Cargo.id` values, so the "idempotent replace"
promised by the OpenAPI contract (`summary: Replace a booking (idempotent
full update)`) wasn't actually true. `verify.sh`'s byte-equality check over
the two `PUT` responses (updatedAt excluded) catches exactly this — see
"Prove it" below for the failure this produces.

The fix: `Ulid.deterministic(seed)` / `generate_deterministic_ulid(seed)`
(`Ulid.java` / `app/ulid.py`) derive a 26-char Crockford id from
`SHA-256(seed)` instead of timestamp+randomness. `replaceBooking` /
`replace_booking` seed each cargo item on `"{bookingId}:{index}"`, so
replacing the same booking with the same body always reproduces the same
cargo ids — while `createBooking` / `addCargo` keep using the random
generator, because a create (or a cargo-add) **must** mint a genuinely new
id every call. Same distinction, opposite requirement.

## DELETE semantics: soft-delete, but "gone" means gone

The contract marks `DELETE /bookings/{id}` as a soft-delete (`status ->
CANCELLED`, record retained for audit, hidden from `GET /bookings`). Ch4
left a cancelled booking visible via `GET /bookings/{id}` (200). This
chapter tightens that: `BookingStore.getActive(id)` /
`store.get_active(booking_id)` treat a cancelled booking the same as a
missing one for every single-item operation — `GET`, `PUT`, `PATCH`,
`DELETE`, and the cargo sub-resource all return `404 Problem` once a
booking is cancelled. Only the raw `get()` (not used by any route handler)
can still see the cancelled record, which is what a real audit/undo path
would call. This makes "second DELETE -> 404" and "GET after DELETE -> 404"
hold consistently, rather than needing a special case.

## 405s carry a body and an `Allow` header

Both stacks implement the "method not supported here" cases as **explicit**
routes rather than relying on the framework's built-in 405 (which differs
in shape between RESTEasy Reactive and Starlette/FastAPI) — each returns a
`Problem` body (`application/problem+json`) plus an `Allow` header listing
what the resource *does* support:

- `PUT /bookings` → 405, `Allow: GET, POST`
- `POST /bookings/{id}` → 405, `Allow: GET, PUT, PATCH, DELETE, HEAD`

## HEAD: free on one stack, not on the other

`HEAD /bookings/{id}` is in the JAX-RS spec's method-matching algorithm: if
no `@HEAD` method exists, the runtime falls back to the matching `@GET`
method and discards the entity body while keeping the headers. RESTEasy
Reactive implements this, so Quarkus needed zero extra code.

FastAPI does **not** do the equivalent. Bare Starlette's `Route.__init__`
auto-adds `"HEAD"` to a route's method set whenever `"GET"` is present, but
FastAPI's `APIRoute` builds `route.methods` directly
(`fastapi.routing._populate_api_route_state`) without going through that
code path — confirmed empirically here (an un-routed `HEAD` first came back
`405`, not `200`). The fix is `app/main.py`'s explicit
`@app.head("/bookings/{booking_id}")` handler, mirroring the equivalent
GET's status code with an empty body. Worth knowing before you assume a
framework "just handles" a method because the spec says a different
framework does.

## Prove it: breaking the idempotency and distinctness assertions on purpose

**Break PUT idempotency** — revert `toCargoItemsForReplace` (Quarkus) or
the `generate_deterministic_ulid(...)` call (Python) back to the random
generator used by POST:

```java
// quarkus/.../BookingResource.java, inside toCargoItemsForReplace(...)
String id = "crg_" + Ulid.generate(); // BUG: random id breaks PUT idempotency
```

Re-run `./verify.sh`. It fails on the second `PUT` of the sequence:

```
lib.sh: PUT responses diverged (ignoring updatedAt):
--- .../quarkus-put1-stable.json
+++ .../quarkus-put2-stable.json
@@ -7,7 +7,7 @@
         "weightKg": 800.0
       },
       "hazardous": false,
-      "id": "crg_01M4Q3FKZV8MYRQBSZNN4ZZMAT",
+      "id": "crg_01M4Q3FM2AMJDTN13BGTVKHQ5K",
       "type": "GENERAL"
     }
lib.sh: FAIL — quarkus two identical PUT /bookings/{id} calls produced DIFFERENT resource state — PUT must be idempotent
```

Revert the edit and re-run — back to `PASS`.

**Break POST distinctness** — make `create_booking` (Python) or
`createBooking` (Quarkus) mint a fixed id instead of a fresh ULID:

```python
# python/app/main.py, inside create_booking(...)
id="bkg_00000000000000000000000000",  # BUG: fixed id breaks POST distinctness
```

Re-run `./verify.sh`. It fails on the very first stack assertion:

```
lib.sh: FAIL — python two identical POST /bookings calls produced the SAME id (bkg_00000000000000000000000000) — POST must not be idempotent
```

Revert the edit and re-run — back to `PASS` for both stacks. Both round
trips were run while building this chapter; see git history / the exercise
above for the exact failure text each produces.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/05-idempotency-matrix.{svg,excalidraw}`) show the method
matrix: which verbs are safe, which converge under repetition, and where
the 405s sit.
