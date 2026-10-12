# Ch16 — Streaming deep-dive

Not every response fits comfortably in one buffered JSON body. This
chapter shows three ways to deliver a SEQUENCE of values to a client
incrementally, as they become available, instead of making the client wait
for the whole thing to be generated and written at once:

| Mode | Endpoint | Content-Type | Use case |
|---|---|---|---|
| Server-Sent Events | `GET /bookings/{id}/events` | `text/event-stream` | live, ordered updates over a long-lived connection |
| NDJSON export | `GET /bookings/events/export` | `application/x-ndjson` | bulk/batch records a client processes line-by-line as they arrive |
| Chunked transfer | `GET /bookings/events/export/chunked` | `text/plain` | a larger generated payload with no size known up front |

- `contracts/schemas/shipping.schema.json` — `#/$defs/BookingEvent`
  (`bookingId`, `status`, `previousStatus`, `occurredAt`, plus optional
  `origin`/`destination` this chapter leaves unset). Reused unchanged from
  the async-operations/event contract already in the shared schema — all
  three streaming modes emit the *same* event shape, not a chapter-local
  type.

Quarkus (`quarkus/`, port 8096→8080) and FastAPI (`python/`, port
8016→8000) each implement a thin Ch4-style Booking resource (`POST`/`GET`,
just enough to mint an id) plus the three streaming endpoints, against an
in-memory store. `verify.sh` creates a booking on each stack, then drives
all three endpoints and checks status codes, headers, frame/line counts,
per-event schema validity, and — for SSE — actual delivery *timing*.

## Run it

```bash
cd examples/16-streaming
./verify.sh
```

This brings both services up with `docker compose`, waits for health,
drives the streaming sequence against `localhost:8096` (Quarkus) and
`localhost:8016` (FastAPI), and tears the stack down again. Prints `PASS`
only if every assertion holds for **both** stacks.

To poke at it by hand instead:

```bash
docker compose up --build

booking_id=$(curl -s -X POST localhost:8096/bookings \
  -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
       "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":1000}}]}' \
  | jq -r .id)

curl -N "localhost:8096/bookings/$booking_id/events"       # SSE: watch frames arrive one by one
curl -s localhost:8096/bookings/events/export               # NDJSON: one JSON object per line
curl -s -D- -o /dev/null localhost:8096/bookings/events/export/chunked  # headers: no Content-Length

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## The event sequence

Both stacks derive the same deterministic cargo-status progression
(`CONFIRMED → IN_TRANSIT → IN_TRANSIT → IN_TRANSIT → DELIVERED`), cycling
if more events are requested than the sequence is long
(`EventGenerator.java` / `app/events.py`). Only `occurredAt` (wall-clock
time of emission) varies between runs — what matters for this chapter is
event *shape* and *delivery timing*, not a frozen clock, unlike Ch15's
manifest generator which needed byte-for-byte determinism.

```
SSE_EVENT_COUNT        = 5     (one stream)
SSE_INTERVAL           = 250ms (between ticks)
EXPORT_EVENT_COUNT     = 10    (NDJSON export)
CHUNKED_LINE_COUNT     = 500   (chunked-transfer demo)
```

A full SSE stream takes roughly `SSE_EVENT_COUNT * SSE_INTERVAL` ≈ 1.25s —
short enough to keep CI bounded, long enough to measure.

## Proving incremental delivery (not just a status code)

The whole point of this chapter is that a client can start consuming data
**before** the server has finished producing it. A buggy or lazy
implementation can return the right status code, the right Content-Type,
and even the right bytes — just all of them at once, right before the
connection closes — and every status-code/body check in this chapter would
still pass. That's not streaming; it's a disguised buffered response.

`verify.sh` catches this for the SSE endpoint by timestamping each `data:`
frame as a line-buffered reader actually sees it arrive — NOT by reading
curl's aggregate `time_starttransfer`/`time_total` fields. That aggregate
approach was tried first and turned out not to work: both Quarkus and
FastAPI flush the HTTP response *headers* to the socket immediately,
before the first event is even generated, regardless of whether the body
is streamed or buffered. So `time_starttransfer` (time to first byte,
which counts header bytes) comes back near-zero either way, and
`time_total - time_starttransfer` ends up measuring the same total compute
duration whether the body streamed or not — it does NOT distinguish the
two cases. Instead, `verify.sh` opens the stream a second time and reads it
line-by-line through a plain bash loop piped straight from `curl -N` (no
internal buffering on curl's side):

```bash
while IFS= read -r line; do
  printf '%s|%s\n' "$(date +%s.%N)" "$line"
done < <(curl -sS -N --max-time 8 "$base/bookings/$booking_id/events")
```

Each `data:` line gets timestamped the moment the `read` loop actually
receives it. If the server genuinely drips five frames out 250ms apart,
the first `data:` line is read at ~0.25s and the last at ~1.25s:
**spread ≈ 1.0s**. If the server instead builds the whole sequence
internally (sleeping in a loop with no yield in between) and writes it all
to the socket in one shot at the end, all five lines land in the same OS
pipe read burst — the loop processes them microseconds apart no matter how
long the server internally slept first: **spread ≈ 0s**. `verify.sh`
asserts `spread >= 0.6s` (60% of the ideal 1.0s, enough margin for CI
jitter, far above what a buffered implementation produces).

NDJSON and the chunked endpoint are checked for shape (Content-Type, line
count, per-line schema validity) and for the absence of `Content-Length`
(proof the server never computed a total size up front) rather than timed
— both intentionally emit their lines back-to-back with no artificial
delay, since the point there is incremental *framing*, not a live feed.

## The drift probe

To see the timing gate actually catch a regression, introduce this edit
and re-run `./verify.sh`:

**Buffer the SSE stream instead of streaming it.**

In `python/app/main.py`'s `_sse_event_stream`, change:

```python
async def _sse_event_stream(booking_id: str) -> AsyncIterator[str]:
    for i in range(SSE_EVENT_COUNT):
        await asyncio.sleep(SSE_INTERVAL_SECONDS)
        payload = event_for(booking_id, i)
        yield f"data: {json.dumps(payload)}\n\n"
```

to build the whole sequence first and yield it all at once:

```python
async def _sse_event_stream(booking_id: str) -> AsyncIterator[str]:
    frames = []
    for i in range(SSE_EVENT_COUNT):
        await asyncio.sleep(SSE_INTERVAL_SECONDS)  # BUG: still "takes time"...
        payload = event_for(booking_id, i)
        frames.append(f"data: {json.dumps(payload)}\n\n")
    yield "".join(frames)  # ...but now it's ONE buffered write, not five
```

(Or in `quarkus/.../StreamingResource.java`'s `bookingEvents()`, replace the
ticking `Multi` with one that sleeps internally and emits all five items at
once, e.g. `Multi.createFrom().item(() -> { Thread.sleep(1000); return ...; })`
expanded to a single collected list.)

Re-run `./verify.sh`. The status code, Content-Type, and frame count are
all still correct — but the timing assertion catches it immediately:

```
lib.sh: python SSE timing — first frame read at 1791812463.516917954, last frame read at 1791812463.530758123, spread 0.014s
lib.sh: FAIL — python SSE: frame-to-frame spread 0.014s is below the 0.6s floor — these frames look BUFFERED (all arrived in one burst), not delivered incrementally
```

(This is the actual output captured while building this chapter — Quarkus's
genuinely-ticking `Multi` kept passing with a ~1.0s spread throughout.)

Revert the edit and re-run `./verify.sh` — it goes back to `PASS` for both
stacks. That round trip (break it, watch the gate catch it, fix it, watch
the gate go green again) is the thing worth internalizing: a streaming
endpoint's CORRECTNESS includes its delivery timing, not just its final
bytes — a status code and a Content-Type header are necessary but not
sufficient proof that a response actually streamed.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/16-streaming-modes.{svg,excalidraw}`) show the three
streaming modes side by side: a client holding open a connection for SSE
frames trickling in over time, a client reading NDJSON lines as they
arrive, and a client receiving an HTTP/1.1 chunked body with no
`Content-Length` known up front.
