# Ch14 — Versioning

An API's resource shape changes. Clients pinned to the old shape can't be
broken the moment a new one ships. This chapter extends the Ch4
contract-first Booking + Cargo resource model with **two different
versioning strategies that both serve the SAME underlying booking in two
different representations**:

- **v2 (current)** — the `Booking` in
  `contracts/schemas/shipping.schema.json`: `quote` (a `Money`) + `cargo[]`
  (an array of cargo items). This is the shape every earlier chapter's
  example already serves.
- **v1 (frozen)** — `BookingV1` in
  `contracts/openapi/shipping-api-v1.yaml`: `price` (the same `Money`,
  renamed) + `cargoDescription` (a single string, not an array). v1 is a
  deliberately older shape, frozen as a stub so this chapter can show a
  real *breaking* change against v2, not a hypothetical one.

There is **one stored booking, one store, one write path** — v1 is never
written to directly. It's a read-only projection computed from the v2
state at request time (`VersionMapper.toV1` / `_to_v1()`). That's the thing
worth internalizing: versioning is about the representation a client gets
back, not about forking the resource itself.

Quarkus (`quarkus/`, port 8094) and FastAPI (`python/`, port 8014)
independently implement both strategies against an in-memory store.
`verify.sh` creates one booking per stack, then reads it back through every
combination of strategy and version, schema-validating every v2 body and
hand-asserting every v1 body's fields (v1 isn't in the shared schema's
`$defs`).

## Run it

```bash
cd examples/14-versioning
./verify.sh
```

This brings both services up with `docker compose`, waits for health,
drives the sequence against `localhost:8094` (Quarkus) and `localhost:8014`
(FastAPI), and tears the stack down again. Prints `PASS` only if every
assertion holds for **both** stacks.

To poke at it by hand instead:

```bash
docker compose up --build

# Create a booking (v2 shape).
id=$(curl -s -X POST localhost:8094/bookings \
  -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
       "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":1000}}]}' \
  | jq -r .id)

# URI versioning — the URL pins the version.
curl -s localhost:8094/v2/bookings/$id | jq .   # quote + cargo[]
curl -s localhost:8094/v1/bookings/$id | jq .   # price + cargoDescription

# Media-type versioning — the Accept header picks the version; watch
# Content-Type and Vary in the response.
curl -sD - localhost:8094/bookings/$id \
  -H 'Accept: application/vnd.shipping.v1+json' -o /dev/null
curl -sD - localhost:8094/bookings/$id \
  -H 'Accept: application/vnd.shipping.v2+json' -o /dev/null

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## Four versioning strategies — which two this chapter implements, and why

| Strategy | Where the version lives | Implemented here? |
|---|---|---|
| **URI versioning** | The path: `/v1/bookings/{id}`, `/v2/bookings/{id}` | **Yes** |
| **Media type (content negotiation)** | The `Accept` header: `application/vnd.shipping.v{1,2}+json` | **Yes** |
| **Query parameter** | A query string: `?version=1` | No — see below |
| **Custom header** | A bespoke header: `X-API-Version: 1` | No — see below |

URI and media-type versioning are the two strategies worth drilling into
because they sit at opposite ends of a real trade-off:

- **URI versioning** is simple, cache-friendly (two different URLs are
  trivially two different cache keys — no `Vary` needed), and visible in
  every log line and bookmark. Its cost: the version is baked into
  *identity* — `/v1/bookings/{id}` and `/v2/bookings/{id}` look like two
  different resources even though they describe the same booking, which
  sits awkwardly with REST's "a resource has one URI" idea.
- **Media-type (content negotiation) versioning** keeps one URI per
  resource (`/bookings/{id}`) — more aligned with REST's resource model —
  but pushes the version into a header most tooling treats as an
  afterthought, and it has a caching cost of its own (see below).

Query-parameter and custom-header versioning are real, widely used
strategies (not implemented here, to keep this example to two focused
comparisons): a query parameter (`?version=1`) is URI versioning's easy
cousin — same cache-key benefit, but the version reads as request
*configuration* rather than part of the address, and it's easy to drop
accidentally when a client builds a URL by hand. A custom header
(`X-API-Version: 1`) is media-type versioning's simpler cousin — no need to
register (or remember) a vendor MIME type — but it invents a contract the
HTTP spec doesn't already define semantics for, where `Accept` +
`Content-Type` + `Vary` already have well-understood, cache-aware meaning.

## The v1 ↔ v2 shape diff

```
v2 (current, #/$defs/Booking)        v1 (frozen, BookingV1)
──────────────────────────────       ──────────────────────────────
id                                   id
status                               status
origin                               origin
destination                          destination
cargo: [ {description, type,         cargoDescription: string
          dimensions, hazardous,                        │
          id}, ... ]  ───────────────────────────────────┘ (lossy join)
quote: {currency, amount}  ───────── price: {currency, amount}  (renamed)
requestedPickup                      (doesn't exist in v1)
createdAt                            createdAt
updatedAt                            (doesn't exist in v1)
```

Two differences make v1 → v2 a **major**, breaking change rather than a
compatible extension: a renamed field (`price` → `quote`) and a shape
change (`cargoDescription` string → `cargo[]` array) are both changes an
old client's deserializer cannot shrug off — unlike, say, v2 adding a new
*optional* field, which an old client would just ignore.

The v1 projection (`VersionMapper.toV1` in Quarkus, `_to_v1()` in FastAPI)
builds `cargoDescription` by joining every v2 cargo item's `description`
with `"; "`. That join is **lossy and one-way**: v1 has no way to recover
individual cargo items, weights, or hazardous flags from that string alone.
That's the real cost of carrying an old representation forward — it can
only describe what its shape had room for, forever.

## Endpoints implemented (identically, in both stacks)

| Method | Path | Success | Representation | Notes |
|--------|------|---------|-----------------|-------|
| POST | `/bookings` | 201 | v2 (`Booking`) | creates the one stored booking |
| GET | `/v2/bookings/{id}` | 200/404 | v2 (`Booking`) | URI versioning — always current |
| GET | `/v1/bookings/{id}` | 200/404 | v1 (`BookingV1`) | URI versioning — always frozen |
| GET | `/bookings/{id}` | 200/404 | v1 or v2 | media-type versioning — `Accept` picks it |

`/bookings/{id}` without a vendor `Accept` (missing header, `*/*`, a bare
`application/json`, or the explicit v2 vendor type) defaults to v2 — "no
opinion" and "current version" behave the same way, matching what
unversioned `/bookings/{id}` meant before this chapter. Every other Ch4
operation (list, replace, patch, delete, cargo sub-resource) is still
present and still v2-only; versioning two read representations doesn't
require versioning the rest of the write surface.

Errors are always `Problem` (`application/problem+json`), same as Ch4: 404
not found.

## `Vary: Accept` — the caching implication

Media-type versioning means **one URL, more than one representation**. A
shared HTTP cache (a CDN, a reverse proxy, even a browser's own cache) keys
its stored entries by URL *by default* — it has no idea `/bookings/{id}`
can come back two different ways unless the response tells it so. Without
`Vary: Accept`, a cache that serves a v1 request first could happily hand
that same cached v1 body to the very next client that asked for v2 — silent
data corruption from the client's point of view, and it would look like a
cache *bug* when the real bug is a missing response header.

`Vary: Accept` on every `/bookings/{id}` response (regardless of which
version got negotiated) tells any RFC 9111-compliant cache: *"key your
cache entries for this URL on the Accept header too, not just the path."*
This is exactly why URI versioning sidesteps the problem entirely —
`/v1/bookings/{id}` and `/v2/bookings/{id}` are already different cache
keys by construction, no `Vary` needed. That's the trade-off from the table
above, made concrete: media-type versioning's single-URI elegance costs a
caching header you must remember to set, every time, on every negotiated
response.

## The drift probe

The whole point of this chapter is that `verify.sh` actually distinguishes
"a v1 endpoint returning the v1 shape" from "a v1 endpoint silently
returning the v2 shape" — a regression that would otherwise look completely
fine (200 OK, valid JSON) to anything that isn't checking the specific
fields. To see it happen, introduce one of these edits and re-run
`./verify.sh`:

**Option A — make the v1 URI endpoint return the v2 shape.**

In `python/app/main.py`'s `get_booking_v1`, change:

```python
return JSONResponse(
    status_code=200,
    content=_to_v1(booking).model_dump(mode="json", exclude_none=True),
    media_type=MEDIA_TYPE_V1,
)
```

to:

```python
return _json(200, booking)  # BUG: v2 shape on the v1 endpoint
```

(Or in `quarkus/.../V1BookingResource.java`, change
`VersionMapper.toV1(booking)` to just `booking` in the `Response.ok(...)`
call — same idea.)

Re-run `./verify.sh`. It fails at the v1 jq assertion for that stack, with
something like:

```
lib.sh: FAIL — python GET /v1/bookings/{id}: expected price + cargoDescription and NO quote/cargo, got {"id":"bkg_...","status":"PENDING",...,"quote":{"currency":"USD","amount":"2500.00"},...,"cargo":[...]}
```

**Option B — drop the `Vary: Accept` header from the negotiated endpoint.**

In `python/app/main.py`'s `get_booking`, remove
`headers={"Vary": "Accept"}` from the returned `JSONResponse` (or in
`quarkus/.../BookingResource.java`'s `getBooking`, remove the
`.header("Vary", "Accept")` call on either branch).

Re-run `./verify.sh`. It fails the `Vary` assertion for that stack:

```
lib.sh: FAIL — python GET /bookings/{id} (Accept: v1) Vary: expected '' to contain 'Accept'
```

Revert whichever edit you made and re-run `./verify.sh` — it goes back to
`PASS` for both stacks. That round trip is the thing worth internalizing:
a version regression that's invisible to a casual `curl | jq` (the status
is 200, the JSON parses) is exactly what a schema- and field-level
verification gate exists to catch mechanically, every time, on both
independently-written stacks.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/14-versioning-strategies.{svg,excalidraw}`) show the two
versioning strategies side by side: one stored booking, two read paths
(URI-pinned and content-negotiated), each producing one of the two
representations.
