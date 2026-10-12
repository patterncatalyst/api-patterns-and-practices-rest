# Ch8 — Filtering, projection & pagination

Extends the [Ch4 contract-first anchor](../04-contract-first/) — same
shipping/cargo Booking resource, same `contracts/openapi/shipping-api.yaml` +
`contracts/schemas/shipping.schema.json`, same `verify.sh` harness via
`examples/_lib/`. This chapter turns `GET /bookings` from "return everything"
into three real pagination strategies plus sparse fieldset projection.

Quarkus (`quarkus/`) and FastAPI (`python/`) run on **different ports here
than every other example** — 8088 and 8008, not 8080/8000 — so this stack
can run alongside ch04/ch06/ch07 without a port collision.

## Run it

```bash
cd examples/08-pagination
./verify.sh
```

Brings both services up with `docker compose`, waits for health, seeds 7
bookings, drives offset / keyset-cursor / seek pagination, field projection,
and the limit-cap assertion against `localhost:8088` (Quarkus) and
`localhost:8008` (FastAPI), schema-validates every non-projected response,
and tears the stack down again. Prints `PASS` only if every assertion holds
for **both** stacks.

```bash
docker compose --profile observability up --build   # + Grafana LGTM, opt-in
```

To poke at it by hand:

```bash
docker compose up --build

# seed a few bookings
for i in 1 2 3 4 5; do
  curl -s -X POST localhost:8088/bookings -H 'Content-Type: application/json' \
    -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
         "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":500}}]}' \
    | jq -r .id
done

curl -s 'localhost:8088/bookings?limit=2' | jq .                       # keyset, first page
curl -s 'localhost:8088/bookings?limit=2&offset=2' | jq .              # offset
curl -s 'localhost:8088/bookings?after_id=bkg_...&limit=2' | jq .      # seek
curl -s 'localhost:8088/bookings?fields=id,status' | jq .              # projection
curl -s 'localhost:8088/bookings?limit=1000' | jq .page.limit          # limit cap -> <= 100

docker compose down -v
```

## GET /bookings query parameters

| Parameter  | Example            | Strategy                                            |
|------------|---------------------|------------------------------------------------------|
| `limit`    | `?limit=20`         | Page size. Clamped to `[1, 100]` — see "The limit cap" below. |
| `cursor`   | `?cursor=Ymtn...`   | Keyset pagination. **The default/stable strategy.**   |
| `offset`   | `?offset=40`        | Classic offset pagination.                            |
| `after_id` | `?after_id=bkg_01H` | Seek pagination: items with `id` after the given id.  |
| `fields`   | `?fields=id,status` | Sparse fieldset projection (orthogonal to paging).    |

Precedence when more than one paging param is present: **`offset` >
`after_id` > `cursor`**. In practice a client only ever sends one of the
three — the precedence order just makes the server's behavior deterministic
rather than undefined if it doesn't.

`page.count` is the number of items in the returned page (not the total
collection size); `page.limit` is the *effective* (post-clamp) limit that
was actually applied.

## The three strategies compared

**Offset (`?limit=&offset=`)** — the one every client already understands:
skip N, take `limit`. Cheap to implement, cheap to reason about, and it
supports "jump to page 7" directly. Its failure mode is **drift under
concurrent inserts**: if a new booking is created between two page fetches
and sorts *before* the current offset window, every item downstream shifts
by one slot, and the client either re-sees an item it already had or skips
one it never saw. This example's in-memory store makes that easy to
demonstrate: seed 5 bookings, fetch `?limit=2&offset=2` (gets items 3-4),
insert a 6th booking, re-fetch the SAME `offset=2` — the window has silently
shifted by one. Offset pagination is fine for "page 7 of a mostly-static
report"; it is the wrong tool for a feed that's being written to while
clients are paging through it.

**Keyset/cursor (`?limit=&cursor=`) — the default/stable strategy.** Instead
of a position ("skip N"), the cursor encodes a value ("everything after
this key"). Concretely here: `page.nextCursor` is an opaque, base64-encoded
copy of the last booking `id` returned on the current page; the next
request's `cursor=` decodes back to that id, and the server returns
everything with `id` greater than it. Because each page's lower bound is
the highest key the client has *already seen* — not a row count — an insert
anywhere in the set never shifts an already-issued cursor's meaning. Walking
`nextCursor` from the first page to `null` visits every item exactly once,
with no dupes and no gaps, regardless of what else is being written to the
store concurrently. The only requirement is a **stable, monotonic sort key**
— here, the booking's ULID id, which is a 48-bit millisecond timestamp
followed by 80 bits of randomness, so sorting by id is (for all practical
purposes) sorting by creation time. A real system with external writers
would more commonly key on `(createdAt, id)` as a compound cursor, in case
two rows share a millisecond; this example uses the id alone to keep the
cursor a single opaque string. Clients cannot (and must not try to) decode
or construct a cursor themselves — it has no server-independent meaning,
only "give this back to me to continue."

**Seek (`?limit=&after_id=`)** — the same keyset idea, made explicit and
non-opaque: pass a known `id` directly instead of an opaque cursor token.
Useful when a client already holds a specific resource's id (e.g. "load
more bookings after the one I'm looking at") and doesn't need the full
walk-to-the-end cursor machinery. It shares keyset's core property (stable
under concurrent inserts — a new row's id either sorts before or after
`after_id`, it never shifts what "after" means) but gives up the "resume an
arbitrary stopped walk with no other state" convenience of an opaque
cursor, since the client has to already know a real id rather than being
handed a token.

## The limit cap: a DoS guard, not a courtesy default

`page.limit`'s *default* (20) is about ergonomics — a reasonable page size
when a client doesn't ask for one. `page.limit`'s *maximum* (100, matching
`#/$defs/PageMeta.limit`'s `maximum: 100` in the shared schema) is about
something else entirely: an **unbounded `limit` is a server resource
exhaustion vector**. A client that requests `?limit=1000000` against a
collection with a million rows forces the server to materialize, serialize,
and transmit an arbitrarily large response body in a single request/response
cycle — no different in effect from any other unbounded-work endpoint. Both
stacks clamp (never reject) an over-limit request: `?limit=1000` silently
becomes `page.limit=100` in the response, rather than a `400`. Clamping
instead of rejecting keeps a naive client's request succeeding (just with a
smaller page than it asked for, discoverable via `page.limit` in the
response) instead of forcing every caller to pre-validate a value the server
was always going to bound anyway.

## Field projection: sparse fieldsets

`?fields=id,status,origin` returns each item with **only** the requested
properties, plus `id` (always included, whether requested or not, since
it's how a client would address the specific resource for a follow-up
`GET /bookings/{id}`). This is a bandwidth/parsing-cost optimization for
clients that only need a few fields from a large collection — a mobile
list view that shows `status` and nothing else shouldn't have to receive
every cargo item's full `Dimensions` for every booking on the page.

**Projected responses are intentionally NOT schema-conforming
`BookingCollection` bodies.** `#/$defs/Booking` requires `status`, `origin`,
`destination`, `cargo`, and `createdAt`; a projection to `fields=id,status`
omits four of those five required properties by design. `verify.sh`
reflects this directly: every **non-projected** call is asserted with
`validate_body BookingCollection` (full contract conformance, the load-
bearing check this whole example series is built on); the **projected**
call instead asserts the field subset by hand (`origin`/`cargo` absent,
`id`/`status` present on every item) rather than running it through the
full-`Booking` validator, which would fail it for the right reason but the
wrong test.

## Why the ULID id works as the cursor key

Both stacks already mint `Booking.id` as `bkg_` + a 26-character
Crockford-Base32 ULID (`Ulid.java` / `app/ulid.py`, unchanged from Ch4): a
48-bit millisecond timestamp encoded first, then 80 bits of randomness.
Because the timestamp is the *leading* bits, lexicographic (string) sort
order on the id is the same as chronological creation order for any two
bookings created more than a millisecond apart. That's exactly the
"stable, monotonic sort key" a keyset cursor needs — no separate sequence
number or `createdAt` column was required to make pagination correct, just
sorting the existing id. `BookingStore.listVisible()` /
`store.list_visible()` now return bookings sorted ascending by id
specifically so every strategy above shares one sort order.

## The drift probe

To see `verify.sh` actually catch a pagination regression, introduce one of
these edits and re-run `./verify.sh`.

**Break the keyset walk — make a page repeat an item.**

In `python/app/main.py`'s `_compute_page`, change the keyset filter's
strict inequality to an inclusive one:

```python
candidates = visible if after_key is None else [b for b in visible if b.id >= after_key]  # BUG: >= not >
```

(Or in `quarkus/.../BookingResource.java`'s `computePage`, change
`b.id().compareTo(afterKey) > 0` to `>= 0`.)

Re-run `./verify.sh`. The keyset walk assertion fails immediately because
the last item of each page is now re-included as the first item of the
next page:

```
lib.sh: FAIL — python keyset walk (limit=3, 3 pages): item 3 differs — expected 'bkg_01H...D', got 'bkg_01H...C' (...)
lib.sh: FAIL — python keyset walk produced duplicate ids (collected 8, 7 unique)
```

Revert the edit and re-run — back to `PASS` for both stacks.

**Or: break the limit cap — stop clamping `limit`.**

In `python/app/main.py`'s `_clamp_limit`, drop the upper bound:

```python
def _clamp_limit(limit: int | None) -> int:
    effective = _DEFAULT_LIMIT if limit is None else limit
    return max(1, effective)  # BUG: _MAX_LIMIT no longer enforced
```

(Or in `quarkus/.../BookingResource.java`'s `clampLimit`, delete the
`if (limit > MAX_LIMIT)` block.)

Re-run `./verify.sh`. The limit-cap assertion fails:

```
lib.sh: FAIL — python limit cap: requested limit=1000 but page.limit=1000 (expected <= 100 — the cap was NOT enforced)
```

Revert the edit and re-run — back to `PASS` for both stacks. That round
trip (break it, watch the gate catch it, fix it, watch the gate go green
again) is the thing worth internalizing: an unbounded `limit` isn't a
correctness bug a type system would catch — it's a resource-exhaustion
vector that only an explicit assertion on the response shape, like
`verify.sh`'s, actually guards against.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/08-pagination-strategies.{svg,excalidraw}`) compare the
three pagination strategies and the field-projection path against the
shared `GET /bookings` endpoint.
