---
title: "Filtering, projection & pagination"
order: 8
part: "Collections at scale"
description: "Keep collection endpoints fast and safe under load: filter and project fields, choose among offset, keyset and seek pagination, and clamp limit as a denial-of-service guard."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Cap `GET /bookings` with a default `limit` and a hard ceiling so an unbounded collection can't become a denial-of-service vector.
- Separate filtering (which items come back) from field projection (`fields=id,status`), and explain why a projected response isn't a schema-conforming `Booking`.
- Compare offset/limit, keyset/cursor and seek pagination, and name the condition (concurrent inserts) that breaks offset.
- Build a keyset cursor from the ULID-based `Booking.id` with no extra sequence column or index.
- Clamp an out-of-range `limit` instead of rejecting it, and report the effective value in `page.limit`.

## Why this matters

An unbounded `GET /bookings` works with seven seeded bookings and fails with five million. Honored literally, it materializes the whole collection in memory, serializes it to JSON and sends it down one connection, whatever the caller needed. A list view that renders twenty rows pays, in memory, CPU, bytes and time to first byte, for every row in the table, and a careless client can turn the endpoint into a denial-of-service vector without trying.

Four controls fix it: a `limit` with a default and a ceiling, a pagination strategy that stays correct under concurrent writes, filters that narrow the collection, and sparse fieldsets that narrow each item.

## Sane defaults

`GET /bookings` with no parameters returns 20 items: enough to be useful, small enough that response time doesn't grow with the collection. A client that wants more asks with `?limit=`. The default is part of the contract: `#/$defs/PageMeta.limit` in `contracts/schemas/shipping.schema.json` declares `"default": 20` next to its `minimum` and `maximum`, so a client reads the unparameterized shape without probing.

## Filtering and field projection

Two independent controls shrink a response beyond what a page size does.

- **Filtering** changes cardinality. It narrows which bookings come back (by `status`, origin or another queryable attribute), so a client that wants bookings in transit doesn't page through every `DELIVERED` and `CANCELLED` one.
- **Field projection** changes shape. `GET /bookings?fields=id,status` returns objects with only those fields, not the full `Booking` with its nested `origin`, `destination`, `cargo` and `quote`.

They compose: filter, then project each survivor. The full resource stays reachable at `GET /bookings/{id}`.

A projected item is not a smaller `Booking`. `#/$defs/Booking` requires `status`, `origin`, `destination`, `cargo` and `createdAt`, and `fields=id,status` omits four of the five. `id` is always included, because it addresses the follow-up `GET /bookings/{id}`; every other field appears only on request. Making the response validate against `Booking` would mean fabricating values or weakening the schema, so validate projected and unprojected responses separately.

## Three ways to page

Once a client holds a page, how does it ask for the next one? The three answers differ under one condition: rows inserted while the client is still paging.

| Strategy | Request | Strength | Weakness |
| --- | --- | --- | --- |
| Offset/limit | `?limit=20&offset=40` | Familiar; jumps straight to page 7 | A position, not a row: inserts shift the window |
| Keyset/cursor | `?cursor=<token>` | Stable under inserts; needs only the last id seen | No random access |
| Seek | `?after_id=bkg_01H...&limit=2` | Stable under inserts; starts from any id the client holds | Caller supplies the id; no opaque token |

Offset fails silently. Fetch `?limit=2&offset=2` over five bookings and you get items 3 and 4. Insert a sixth that sorts ahead of that window, repeat the request, and every row has shifted by one: the client re-sees a row or skips one, with no error and no signal in the response.

Keyset changes what a page boundary is. Each page carries `page.nextCursor`, an opaque token encoding the id of the last booking returned. The next request decodes it and returns everything sorted after that id. The lower bound is "the highest key already seen", not "how many rows came before", so an insert anywhere never changes what an issued cursor means. Walking `nextCursor` to `null` visits every item exactly once.

Seek is the same idea with the token made explicit: the client passes a real id it already holds. It fits "load more after the one I'm looking at".

Keyset is the default because it's the only strategy that is both stable under concurrent writes and needs no state beyond the last id. The server resolves a request that mixes parameters in a fixed order: `offset`, then `after_id`, then `cursor`.

## The booking id as the cursor key

Keyset normally needs infrastructure: a monotonic sequence or a `created_at` index. A `Booking.id` already works, because it is `bkg_` followed by a 26-character ULID: a 48-bit millisecond timestamp first, then 80 bits of randomness. With the timestamp in the leading bits, plain string order matches creation order for ids minted more than a millisecond apart. No new column or index is needed.

Two bookings minted in the same millisecond aren't guaranteed to sort in creation order, so the server's sorted view, not seed order, is the authority. A service with several writers keys on a compound `(createdAt, id)` instead. This one has a single writer, so the id alone keeps the cursor a single opaque string.

Both stores return bookings ascending by id, so every strategy walks the same order. The keyset resolution, including the opaque cursor, on each stack:

{% include codetabs.html langs="Quarkus|Python" %}

```java
// Keyset/cursor: the default/stable strategy. A null/blank cursor
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
# Keyset/cursor: the default/stable strategy. A null/blank cursor
# means "first page"; following page.nextCursor walks the whole set
# with no dupes or gaps, because each page's lower bound is the highest
# id actually returned by the page before it.
after_key = _decode_cursor(cursor) if cursor else None
candidates = visible if after_key is None else [b for b in visible if b.id > after_key]
page_items = candidates[:limit]
next_cursor = _encode_cursor(page_items[-1].id) if len(candidates) > limit else None
return page_items, next_cursor
```

## `limit` as a denial-of-service guard

The default of 20 doesn't help against `?limit=1000000` on a million-row collection. Trusting a client-supplied size forces the server to build and send an arbitrarily large body in one cycle. Both stacks enforce a hard maximum of 100, matching `maximum: 100` in `PageMeta.limit`.

When a request exceeds it, both stacks **clamp** instead of rejecting. `?limit=1000` returns `200` with `page.limit` set to `100`. A naive client gets a smaller page rather than an error to branch on, and a client that cares reads the applied value back. A `400` would make every caller pre-validate a bound the server enforces anyway. The ceiling is a constant on each stack (`MAX_LIMIT = 100`, `_MAX_LIMIT = 100`), and the clamp applies it:

{% include codetabs.html langs="Quarkus|Python" %}

```java
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
def _clamp_limit(limit: int | None) -> int:
    """DoS guard: `limit` above `_MAX_LIMIT` is CLAMPED, never honored
    unbounded (matches `#/$defs/PageMeta.limit`'s `maximum: 100` in the
    shared schema). An unbounded limit lets a client force the server to
    materialize and serialize an arbitrarily large response in one shot."""
    effective = _DEFAULT_LIMIT if limit is None else limit
    return max(1, min(effective, _MAX_LIMIT))
```

A `limit` below 1 clamps up to 1 for the same reason: the server owns the valid range, and every out-of-range value lands on the nearest valid one. `page.count` (items returned) and `page.limit` (the effective limit) are always present, so a client can tell "fewer than `limit` items remained" from "the server capped my request".

{% include excalidraw.html file="08-pagination-strategies" alt="Three pagination strategies against GET /bookings: offset/limit drifts when a concurrent insert shifts the window, keyset/cursor and seek stay stable over the monotonic booking id, and a limit clamp caps all three at a maximum page size." caption="Figure 8.1: Three pagination strategies, and why keyset is the stable default." %}

## When to use which

| Situation | Use |
| --- | --- |
| Data barely changes while clients page, and "jump to page 7" is a requirement | Offset/limit |
| Collection is written while clients page (live traffic) | Keyset/cursor, the default |
| Caller already holds an id and wants "more after this one" | Seek |
| Any collection endpoint | A server-owned `limit` ceiling, clamped, with the effective value in `page.limit` |

> **🤖 Explore with your agent**
>
> "In `examples/08-pagination`, `GET /bookings` takes `limit`, `offset`, `after_id`, `cursor` and `fields` but no filter. Add a `status` filter on both the Quarkus and FastAPI services so it combines with `cursor` and `fields=id,status`. Keep `id` in every projected item, keep `limit` clamped to 100, and don't change the keyset comparison."
>
> Check: `./verify.sh` still prints `PASS`, and `GET /bookings?status=PENDING&limit=2` returns only pending bookings, with a `nextCursor` that walks to `null` without duplicates.

## Build, run, observe

The Quarkus service listens on `8088` and FastAPI on `8008`, so it runs beside the earlier examples.

```bash
cd examples/08-pagination && ./verify.sh
```

It starts both stacks, seeds seven bookings, and prints `PASS` when offset, keyset, seek, projection and the `limit` cap all behave on each. See `examples/08-pagination/README.md` for the full run output. Every unprojected response is validated against `contracts/schemas/shipping.schema.json`; projected responses are checked by hand.

Experiments:

- Change the keyset filter's strict inequality to `>=` (`b.id().compareTo(afterKey) >= 0`, or the Python equivalent). The cursor walk fails, because the last item of each page reappears at the top of the next.
- Remove the upper bound from either clamp function. The limit-cap check fails on the uncapped response.

## For deeper coverage

- Lukasz Dynowski & Marcin Dulak, *Learning API Styles* (O'Reilly, 2025): collection design, including pagination and filtering, across multiple API styles.
- James Gough, Daniel Bryant & Matthew Auburn, *Mastering API Architecture* (O'Reilly, 2022): operating collection endpoints at scale.
- Justin Higginbotham, *Principles of Web API Design* (Addison-Wesley, 2021): resource and collection design principles.
- *Data* ([Cloud Native Design Patterns](https://github.com/patterncatalyst/cloud-native-design-patterns)): read/write model separation, relevant to sizing a read model that serves a filtered, projected, paginated collection.
