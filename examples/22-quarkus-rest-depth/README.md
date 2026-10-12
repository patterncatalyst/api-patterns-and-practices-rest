# Ch22 — Quarkus REST in depth

This is the chapter's single-stack (Quarkus-only) deep-dive: unlike the
cross-stack chapters, there is no `python/` counterpart here on purpose.
The chapter's thesis is specific to Quarkus REST (formerly RESTEasy
Reactive): parameter bindings like `@RestHeader` and `@RestQuery` are
resolved at **build time**, via a bytecode-generating Quarkus processor —
not by `java.lang.reflect.Method`/`Parameter` introspection on every
request, the way classic JAX-RS's `@HeaderParam`/`@QueryParam` work. That
difference is invisible on the wire (same status codes, same header/query
semantics as classic JAX-RS) — it shows up in cold-start time and
allocation profile, not in anything `curl` can see directly. What *is*
observable, and what this example demonstrates plus `verify.sh` asserts:

| Feature | Endpoint | What it proves |
|---|---|---|
| `@RestHeader` | `GET /tenant` | Binds the `X-Tenant` request header; falls back to a documented default when absent |
| `@RestQuery` | `GET /bookings/events/export?limit=N` | Binds the `limit` query param, and that value genuinely DRIVES the response (record count), clamped as a DoS guard |
| Reactive NDJSON | same endpoint | A Mutiny `Multi<String>` streams records INCREMENTALLY, not as one buffered blob |

- `contracts/schemas/shipping.schema.json` — `#/$defs/BookingEvent`
  (`bookingId`, `status`, `previousStatus`, `occurredAt`, plus optional
  `origin`/`destination` this example leaves unset). Reused unchanged from
  the same shared schema Ch16's streaming deep-dive emits — every streamed
  record is validated against this type.

Quarkus (`quarkus/`, port 8102→8080) runs an in-memory, deterministic event
generator behind two endpoints. `verify.sh` drives both the header and
query-param behavior, validates every streamed record against the shared
schema, and proves the NDJSON export's delivery *timing* is genuinely
incremental.

## Run it

```bash
cd examples/22-quarkus-rest-depth
./verify.sh
```

This brings the Quarkus service up with `docker compose`, waits for
health, drives the `@RestHeader`/`@RestQuery` sequence against
`localhost:8102`, and tears the stack down again. Prints `PASS` only if
every assertion holds.

To poke at it by hand instead:

```bash
docker compose up --build

curl -s localhost:8102/tenant | jq .                          # {"tenant":"public","defaulted":true}
curl -s -H 'X-Tenant: acme-shipping' localhost:8102/tenant | jq .   # {"tenant":"acme-shipping","defaulted":false}

curl -s 'localhost:8102/bookings/events/export?limit=3'        # 3 NDJSON lines
curl -s 'localhost:8102/bookings/events/export?limit=999'       # clamped to 20 lines, not 999
curl -N 'localhost:8102/bookings/events/export?limit=5'          # watch lines arrive ~200ms apart

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default (the app
doesn't ship telemetry yet):

```bash
docker compose --profile observability up --build
```

## `@RestHeader` — zero-reflection header binding

```java
@GET
@Path("/tenant")
@Produces(MediaType.APPLICATION_JSON)
public Map<String, Object> tenantInfo(@RestHeader("X-Tenant") String tenant) {
    boolean defaulted = tenant == null;
    ...
}
```

`org.jboss.resteasy.reactive.RestHeader` is Quarkus REST's drop-in
replacement for classic JAX-RS's `@HeaderParam` (see the [migration
guide](https://quarkus.io/guides/rest-migration#request)). On an absent
header it injects `null` for a reference type, same as `@HeaderParam` — so
the default ("public") is applied explicitly in code, not via
`@DefaultValue` (which only ever supplies a fixed string literal).
`verify.sh` sends the header and checks it round-trips; omits it and
checks the fallback.

## `@RestQuery` driving a reactive NDJSON export

```java
@GET
@Path("/bookings/events/export")
@Produces("application/x-ndjson")
public Multi<String> exportEvents(@RestQuery("limit") @DefaultValue("5") int limit) {
    int effectiveLimit = EventGenerator.clampLimit(limit);
    return Multi.createFrom().ticks()
            .startingAfter(Duration.ofMillis(EventGenerator.STREAM_INTERVAL_MILLIS))
            .every(Duration.ofMillis(EventGenerator.STREAM_INTERVAL_MILLIS))
            .onItem().transform(Long::intValue)
            .select().first(effectiveLimit)
            .onItem().transform(i -> toJsonLine(EventGenerator.eventFor(EventGenerator.SAMPLE_BOOKING_ID, i)));
}
```

`limit` isn't just accepted and ignored — it controls exactly how many
`BookingEvent` records the stream emits, clamped to `[1, MAX_LIMIT=20]` as
a DoS guard (an unbounded limit would let a client force an arbitrarily
long-lived connection). `verify.sh` requests `limit=3` and `limit=8` and
checks the record counts actually differ, checks the omitted case uses the
documented default (5), and checks `limit=999` comes back clamped to 20
rather than honored literally.

### The NDJSON double-encoding pitfall

Returning `Multi<String>` from a `@Produces("application/x-ndjson")`
method is not enough on its own. Without a dedicated writer for that exact
media type, `quarkus-rest-jackson`'s Jackson provider — registered broadly
enough to catch media types it doesn't specifically recognize — wins the
writer lookup for `String` and serializes each line as a JSON **string
value** (wrapped in quotes, its embedded newline escaped to `\n`) instead
of writing the line's bytes as-is. That turns newline-delimited JSON into
one giant escaped string and breaks `validate_response.py` outright
(`"{...}\n" is not of type 'object'"`). `NdjsonMessageBodyWriter.java`
fixes this with a narrowly-scoped `@Provider` that wins the lookup for
exactly `application/x-ndjson` + `String` and writes the pre-serialized
line's raw bytes untouched. This is the same pitfall (and fix) documented
in Ch16's streaming deep-dive — reused verbatim here.

## Proving incremental delivery (not just a status code)

Same technique as Ch16's SSE endpoint: a response that returns the right
status code, the right `Content-Type`, and even the right bytes — just all
of them at once, right before the connection closes — would pass every
status-code/body check here and still not be streaming. `verify.sh` opens
the export a second time and reads it line-by-line through a plain bash
loop piped straight from `curl -N` (no internal buffering), timestamping
each line as it's actually received:

```bash
while IFS= read -r line; do
  [[ -z "$line" ]] && continue   # NDJSON records are followed by a blank line
  printf '%s|%s\n' "$(date +%s.%N)" "$line" >> "$timed_file"
done < <(curl -sS -N --max-time 8 "$base/bookings/events/export?limit=5")
```

With `limit=5` and a 200ms tick interval, the ideal first-line-to-last-line
spread is `(5-1) * 200ms = 800ms`. `verify.sh` asserts `spread >= 0.5s`
(62% of ideal, enough margin for CI jitter, far above what a buffered
implementation — generate everything internally, write it all in one
burst — would produce, which is ≈0s). A real run:

```
lib.sh: NDJSON timing — first line read at 1791820219.933814842, last line read at 1791820220.737206368, spread 0.803s
lib.sh: ok — NDJSON spread 0.803s >= 0.5s floor — delivery is genuinely incremental
```

## The drift probe

To see the timing gate actually catch a regression, edit
`RestDepthResource.java`'s `exportEvents` to collect the whole sequence
before emitting anything, e.g. replace the ticking `Multi` with:

```java
public Multi<String> exportEvents(@RestQuery("limit") @DefaultValue("5") int limit) {
    int effectiveLimit = EventGenerator.clampLimit(limit);
    StringBuilder all = new StringBuilder();
    for (int i = 0; i < effectiveLimit; i++) {
        try {
            Thread.sleep(EventGenerator.STREAM_INTERVAL_MILLIS); // still "takes time"...
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        all.append(toJsonLine(EventGenerator.eventFor(EventGenerator.SAMPLE_BOOKING_ID, i)));
    }
    return Multi.createFrom().item(all.toString()); // ...but now it's ONE buffered write
}
```

Re-run `./verify.sh`. The status code, `Content-Type`, line count, and
per-line schema validity are all still correct — but the timing assertion
catches it immediately, reporting a spread near 0s and failing with "these
lines look BUFFERED (all arrived in one burst), not delivered
incrementally." Revert the edit and `./verify.sh` goes back to `PASS`.
That round trip — break it, watch the gate catch it, fix it, watch the
gate go green again — is the thing worth internalizing: a streaming
endpoint's correctness includes its delivery *timing*, not just its final
bytes.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/22-quarkus-rest-in-depth.{svg,excalidraw}`) show Quarkus
REST's build-time parameter-binding path alongside the reactive NDJSON
export's tick-driven, item-at-a-time delivery to the client.
