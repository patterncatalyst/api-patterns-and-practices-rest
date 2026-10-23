---
title: "Filtering, projection & pagination"
order: 8
part: "Collections at scale"
description: "Keep collection endpoints fast and safe under load: filter and project fields, choose the right pagination strategy among offset, keyset, and seek, and cap limit as a denial-of-service guard."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Cap `GET /bookings` with a sane default `limit` and a hard ceiling so an unbounded collection endpoint can't become a denial-of-service vector.
- Separate filtering (which items come back) from field projection (`fields=id,status`), and explain why a projected response isn't a schema-conforming `Booking`.
- Compare offset/limit, keyset/cursor, and seek pagination, and name the condition (concurrent inserts) that breaks offset's guarantee.
- Build a keyset cursor from the existing ULID-based `Booking.id` with no extra sequence column or index.
- Clamp an out-of-range `limit` instead of rejecting it, and surface the effective value in `page.limit`.

## Why this matters

Every chapter so far has sent `GET /bookings` back one of two ways: a single resource, or every booking the store happened to hold. That second shape works fine with five or seven seeded bookings in a demo. It stops working the moment the store holds five million, because `GET /bookings` with no limit on it is not "return the collection," it is "materialize the entire collection in memory, serialize all of it to JSON, and push the whole body down one HTTP connection," regardless of what the caller needed. A client asking for a list view that renders twenty rows on screen gets charged (in server memory, in serialization CPU, in network bytes, in time to first byte) for every row in the table. An unbounded collection endpoint is not a convenience feature; it is a liability with a request line, and a careless client can turn it into a denial-of-service vector without trying hard.

This chapter turns `GET /bookings` from "return everything" into something that stays fast and safe at any collection size: a `limit` with a sane default and a hard ceiling, three pagination strategies with different correctness properties under concurrent writes, and a sparse-fieldset projection that lets a caller ask for less than the full `Booking` representation. None of this is exotic (every production REST API that outlives its first demo builds some version of it), but the choices interact in ways that surface only once real traffic and concurrent writers show up.

## Sane defaults, not unbounded responses

The fix starts with a default nobody has to ask for. `GET /bookings` with no query parameters returns a `limit` of 20: enough to be useful, small enough that response time and memory footprint don't depend on how large the collection grows. A client that wants more asks for more, explicitly, via `?limit=`. That single decision separates "an endpoint that works at demo scale" from "an endpoint whose behavior doesn't change shape as the collection grows." The shared schema makes the default a contract fact, not an implementation detail: `#/$defs/PageMeta.limit` in `contracts/schemas/shipping.schema.json` declares `"default": 20` alongside the `minimum`/`maximum` bounds, so a client reading the contract knows the unparameterized shape without probing it.

A default page size solves the "forgot to ask" case. It does nothing for the client that asks for far more than is reasonable, which is where the limit cap, covered below, picks up the rest of the job.

## Filtering and field projection

Two orthogonal knobs shrink a collection response beyond what pagination alone does. **Filtering** narrows *which* bookings come back (by `status`, by origin, by any other queryable attribute) so a client asking for "my bookings still in transit" doesn't have to page through every `DELIVERED` and `CANCELLED` booking to find them. **Field projection** narrows *what each booking looks like* once selected: `GET /bookings?fields=id,status` returns objects carrying only `id` and `status`, not the full `Booking` representation with its nested `origin`, `destination`, `cargo` array, and `quote`. A mobile list view rendering a hundred rows of "booking id + status badge" has no use for a hundred full cargo manifests arriving underneath it; projection is the mechanism that lets the client say so.

The two compose (filter to a subset, then project each surviving item down to a few fields), but they solve different problems. Filtering changes cardinality (how many items); projection changes shape (how wide each item is). Both move less data than the unfiltered, unprojected collection, and both leave the full resource reachable at `GET /bookings/{id}` for a client that decides it needs the whole thing after all.

Projection comes with one sharp edge: a projected response is not a smaller version of the same thing, **it is not a schema-conforming `BookingCollection` body at all.** `#/$defs/Booking` requires `status`, `origin`, `destination`, `cargo`, and `createdAt`; a projection to `fields=id,status` is missing four of those five required properties, by design. `id` is always included in a projected item, whether the client asked for it or not, since it is how a follow-up `GET /bookings/{id}` would address that specific resource; every other field is included only on request. A server that tried to make a projected response validate against the full `Booking` schema would have to fabricate values for the omitted required fields or weaken the schema until it no longer means anything; this chapter does neither, and `verify.sh` routes projected and non-projected responses through two different assertions rather than forcing one validator to cover both.

## Three ways to page through a collection

Pagination answers a question filtering and projection don't: once a client has a page of results, how does it ask for the next one? There are three defensible answers, trading off differently under the one condition that breaks the naive version of all of them: rows being inserted into the collection while a client is still paging through it.

**Offset/limit** is the one every client already understands without being told how it works: `?limit=20&offset=40` means "skip the first 40 matching rows, then take the next 20." It is cheap to implement, cheap to reason about, and it is the only one of the three that supports "jump straight to page 7" without having walked pages 1 through 6 first. Its failure mode shows up only under concurrent writes, which a demo with a handful of seeded rows and no other traffic never exercises: offset is a *position* in a result set, not a reference to a particular row, so if a new booking is inserted between two page fetches and sorts ahead of the current offset window, every row downstream of that insertion point shifts by one slot. A client re-requesting the same `offset=2` after that insertion either re-sees a row it already had, or skips a row it never saw, and nothing about the response tells it which. The example's in-memory store makes this concrete: seed five bookings, fetch `?limit=2&offset=2` to get items 3 and 4, insert a sixth booking, then re-fetch the identical `offset=2`: the window has shifted by one, with no error and no signal in the response. Offset pagination is the right tool for "page 7 of a mostly static report" and the wrong tool for a feed being written to while clients are actively paging through it.

**Keyset (cursor) pagination** fixes the drift by changing what a page boundary *is*. Instead of a position counted from the start, each page carries `page.nextCursor`: an opaque token that encodes a value (concretely here, the id of the last booking returned on the current page) rather than a row count. The next request's `?cursor=` decodes back to that id, and the server returns everything sorted after it. Because a page's lower bound is "the highest key the client has already seen," not "how many rows came before it," an insert anywhere in the set never changes what an already-issued cursor means: walking `nextCursor` from the first page through to `null` visits every item exactly once, with no duplicates and no gaps, regardless of what else gets written to the store in between. The only requirement a cursor imposes is a stable, monotonic sort key to walk: this chapter already has one in the booking id itself, with no extra column required.

**Seek pagination** is the same keyset idea with the token made explicit instead of opaque: `?after_id=bkg_01H...&limit=2` means "items with `id` greater than this one," using a real id the client already holds rather than a cursor handed back from a previous response. It shares keyset's core property (stable under concurrent inserts, because a new row's id sorts before or after `after_id` and never changes what "after" means) but gives up the "resume an arbitrary walk with no other state" convenience of an opaque cursor. Seek fits when a client already has a specific id in hand for another reason, such as "load more bookings after the one I'm currently looking at," and doesn't need the full walk-to-the-end cursor machinery.

Keyset is the default for a reason: it is the only one of the three both stable under concurrent writes *and* requiring no state beyond "the last id I saw." Offset suits data that barely changes, where jump-to-page matters more than drift safety. Seek is the specialized case where the caller's starting point is a known id rather than the first page.

## Why the booking id works as a cursor key with no extra column

Making keyset pagination correct usually means adding infrastructure: a monotonic sequence number, a `created_at` index, something guaranteed never to repeat or go backward. This domain already has one, for a reason unrelated to pagination. Chapter 4 minted every `Booking.id` as `bkg_` followed by a 26-character ULID: a 48-bit millisecond timestamp encoded first, then 80 bits of randomness appended after it. Because the timestamp occupies the *leading* bits, lexicographic (plain string) sort order on the id is the same as chronological creation order for any two bookings created more than a millisecond apart, exactly the property a keyset cursor needs. No sequence column, no secondary index, no `created_at` field had to be added to make pagination correct; sorting the id that was already there is enough. A system with writers outside this one service would more commonly key on a compound `(createdAt, id)` pair in case two rows land in the same millisecond; this example keeps the cursor a single opaque string by using the id alone, sufficient for a single writer minting one id at a time.

Both stores return bookings sorted ascending by id, so every strategy (offset, keyset, and seek alike) walks the same order. Here is the keyset/cursor resolution on each side, including the opaque-cursor encode/decode that keeps the cursor's internal shape hidden from the client:

{% include codetabs.html langs="Quarkus|Python" %}

```java
// Keyset/cursor — the default/stable strategy. A null/blank cursor
// means "first page"; following page.nextCursor walks the whole set
// with no dupes or gaps, because each page's lower bound is the
// highest id actually returned by the page before it.
String afterKey = (cursor != null && !cursor.isBlank()) ? decodeCursor(cursor) : null;
List<Booking> candidates = (afterKey == null)
        ? visible
        : visible.stream().filter(b -> b.id().compareTo(afterKey) > 0).toList();
List<Booking> page = candidates.stream().limit(limit).toList();
String nextCursor = (candidates.size() > limit) ? encodeCursor(page.get(page.size() - 1).id()) : null;
return new PageResult(page, nextCursor);
```

```python
# Keyset/cursor — the default/stable strategy. A null/blank cursor
# means "first page"; following page.nextCursor walks the whole set
# with no dupes or gaps, because each page's lower bound is the highest
# id actually returned by the page before it.
after_key = _decode_cursor(cursor) if cursor else None
candidates = visible if after_key is None else [b for b in visible if b.id > after_key]
page_items = candidates[:limit]
next_cursor = _encode_cursor(page_items[-1].id) if len(candidates) > limit else None
return page_items, next_cursor
```

Both sides resolve the same precedence order: `offset` first, then `after_id` (seek), then `cursor` (keyset); so a request mixing paging parameters still has deterministic behavior. In practice a client sends only one of the three; the ordering exists so the server's behavior is fully specified even if it doesn't.

## `limit` as a denial-of-service guard

The default of 20 handles the client that didn't ask for a page size. It does nothing to stop the client that asks for `?limit=1000000` against a collection holding a million rows: a request that, honored literally, forces the server to materialize, serialize, and transmit an arbitrarily large body in one request/response cycle. That is the consequence of trusting a client-supplied size parameter without a ceiling. The fix both stacks apply is a hard maximum (100 here, matching `#/$defs/PageMeta.limit`'s `maximum: 100` in the shared schema) that the server enforces regardless of what the client asks for.

The more interesting decision is what happens when a request exceeds it: both stacks **clamp**, they do not **reject**. `?limit=1000` does not come back as a `400`; it comes back as a `200` whose `page.limit` reads `100`, silently smaller than what was asked for but fully discoverable in the response the client already has to read. Clamping keeps a naive client's request succeeding: it gets a smaller page than it asked for, not an error it has to branch on, while a client that cares precisely what limit was applied can always read `page.limit` back. Rejecting with a `400` would force every caller to pre-validate a bound the server was always going to enforce anyway, for a case where "give the caller a smaller page" is a perfectly serviceable answer. Here is the clamp on both stacks, next to the constant it enforces against:

{% include codetabs.html langs="Quarkus|Python" %}

```java
/** DoS guard: `limit` above this is CLAMPED, never honored unbounded
 * (matches `#/$defs/PageMeta.limit`'s `maximum: 100` in the shared
 * schema). An unbounded limit lets a client force the server to
 * materialize and serialize an arbitrarily large response in one shot. */
private static final int MAX_LIMIT = 100;

private int clampLimit(Integer requested) {
    int limit = (requested == null) ? DEFAULT_LIMIT : requested;
    if (limit < 1) {
        limit = 1;
    }
    if (limit > MAX_LIMIT) {
        limit = MAX_LIMIT;
    }
    return limit;
}
```

```python
_MAX_LIMIT = 100  # DoS guard: `limit` above this is clamped, never honored unbounded.

def _clamp_limit(limit: int | None) -> int:
    """DoS guard: `limit` above `_MAX_LIMIT` is CLAMPED, never honored
    unbounded (matches `#/$defs/PageMeta.limit`'s `maximum: 100` in the
    shared schema). An unbounded limit lets a client force the server to
    materialize and serialize an arbitrarily large response in one shot."""
    effective = _DEFAULT_LIMIT if limit is None else limit
    return max(1, min(effective, _MAX_LIMIT))
```

A limit below 1 is clamped up to 1 for the same reason: the server, not the client, owns the valid range, and every out-of-range value lands on the nearest valid one instead of an error path the client has to special-case. `page.count` (items returned) and `page.limit` (the effective, post-clamp limit) are both always present in the response, so a client can tell "the collection had fewer than `limit` items left" from "the server capped what I asked for" without guessing.

## Proof, not assertion

This chapter's example runs on ports `8088` (Quarkus) and `8008` (FastAPI), not the usual `8080`/`8000` pair, so it can run alongside ch04, ch06, and ch07 without a port collision.

`verify.sh` brings both services up, seeds seven bookings, and establishes a baseline: a default `GET /bookings` (limit 20, comfortably above the seeded count) returns all seven in a single page with `page.nextCursor` null, sorted ascending by id: the ground truth every other assertion checks against, rather than assuming seed order matches id order (ULIDs minted within the same millisecond aren't guaranteed to sort in creation order; only the server's own sorted view is authoritative). From there it walks the full keyset cursor chain at `limit=3`, collecting every id returned across all pages and asserting that ordered list is identical, item for item, to the baseline, proving no duplicates and no gaps across the walk, not just that each page call succeeded. It separately verifies offset pagination returns the expected slice at `offset=3`, seek pagination returns the expected slice after a known id, field projection returns exactly `{id, status}` per item with `origin` and `cargo` absent, and the limit cap holds: `?limit=1000` comes back with `page.limit` at or below 100. Every non-projected response is schema-validated against `contracts/schemas/shipping.schema.json`; the projected response is checked by hand, for the reason covered above. The run prints `PASS` only when every assertion holds on both stacks.

The example's README documents a drift probe worth running once: loosen the keyset filter's strict inequality (`b.id().compareTo(afterKey) > 0` to `>= 0`, or the Python equivalent) and re-run `./verify.sh`. The keyset walk assertion fails immediately, because the last item of each page gets re-included as the first item of the next one, exactly the duplicate a correct keyset implementation is supposed to make impossible. Revert the change and the run returns to green. The same probe works on the limit cap: drop the upper bound from either clamp function, and the limit-cap assertion catches the uncapped response on the next run. That round trip (break it, watch the gate catch it, fix it, watch it go green again) is the reason a 200 status code is never, on its own, proof that a pagination or resource-exhaustion guard is working.

{% include excalidraw.html file="08-pagination-strategies" alt="Three pagination strategies compared side by side against the same GET /bookings endpoint: offset/limit using a row count that drifts when a concurrent insert shifts the window, keyset/cursor using an opaque token over the monotonic booking-id sort key that stays stable under concurrent inserts, and seek using an explicit after_id with the same stability property, with a limit clamp shown capping all three to a maximum page size as a denial-of-service guard regardless of what the client requests." caption="Figure 8.1: Three pagination strategies, and why keyset is the stable default." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to the pagination choice. When the backing collection is effectively static relative to how fast clients page through it, and "jump to page 7" is a real requirement, <strong>offset/limit</strong> is the lower-cost correct answer: every client already expects it, and the drift failure mode never triggers because nothing is being inserted while clients page. The moment the collection is written to concurrently with clients paging through it (the common case for anything backed by live traffic), reach for <strong>keyset/cursor</strong> as the default: it costs an opaque token instead of an integer, and buys a walk provably free of duplicates and gaps regardless of what else is being written. Reach for <strong>seek</strong> when a caller already holds a concrete id for another reason and wants "more after this one" without the cursor-token machinery. Whichever strategy you pick, treat <code>limit</code> as untrusted input with a server-owned ceiling, not a client-owned preference: clamp it to a documented maximum on every request, expose the effective value in <code>page.limit</code>, and never let a caller turn a collection endpoint into unbounded server work just by asking for it.</p></div>

## Build, run, observe

```bash
cd examples/08-pagination && ./verify.sh
```

`verify.sh` brings both stacks up, seeds seven bookings, and checks offset, keyset-cursor, and seek pagination, sparse-fieldset projection, and the `limit` cap against each stack. It prints `PASS` once every assertion holds on both stacks; see `examples/08-pagination/README.md` for the full run output.

## For deeper coverage

- Lukasz Dynowski & Marcin Dulak, *Learning API Styles* (O'Reilly, 2025): collection design, including pagination and filtering, across multiple API styles.
- James Gough, Daniel Bryant & Matthew Auburn, *Mastering API Architecture* (O'Reilly, 2022): operating collection endpoints at scale.
- Justin Higginbotham, *Principles of Web API Design* (Addison-Wesley, 2021): resource and collection design principles.
- *Data* (Chapter 4, [Cloud Native Design Patterns](https://github.com/patterncatalyst/cloud-native-design-patterns)): read/write model separation, relevant to sizing a read model that serves a filtered, projected, paginated collection.
