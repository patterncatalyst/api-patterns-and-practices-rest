---
title: "Streaming deep-dive"
order: 16
part: "Large payloads & streaming"
description: "Push data as it is produced: chunked transfer encoding, Server-Sent Events for live updates, and NDJSON for bulk export, plus how to prove a response is delivered incrementally, not buffered."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Implement chunked transfer encoding (`Transfer-Encoding: chunked`, no `Content-Length`) for a response whose size isn't known up front.
- Stream Server-Sent Events (`text/event-stream`, `data:` frames) for a live, one-directional feed.
- Stream NDJSON (`application/x-ndjson`) for a bulk export a consumer processes line by line.
- Fix the Quarkus double-encoding gotcha with a dedicated `MessageBodyWriter`.
- Prove incremental delivery with a `curl -N` frame-timing check rather than status codes alone.

## Why this matters

Chapter 15 answered a question about *size*: a 2 MiB manifest sits still on disk, fully formed, and a client wants a slice of it without paying for the rest. This chapter answers a different question, about *time*: what happens when the data a client wants doesn't exist all at once in the first place? A cargo-status feed has no final byte until the next status change happens, possibly minutes from now. A bulk export of booking events can be handed to a client the instant each record is ready, rather than after every record has been generated and the whole array closed with a `]`. "Wait for the entire response body before sending any of it" is not merely wasteful here the way it was for the manifest: it is actively wrong, since there may be no "entire body" to wait for. Streaming is what HTTP calls the alternative: start writing the response before you know how it ends.

The example for this chapter (`examples/16-streaming/`) extends the same Ch4-style `Booking` resource with three endpoints, each streaming the identical `BookingEvent` shape from `contracts/schemas/shipping.schema.json` (reused unchanged, not invented locally) over three wire formats. `GET /bookings/{id}/events` streams Server-Sent Events: a live, ordered feed of cargo-status transitions over one long-lived connection. `GET /bookings/events/export` streams NDJSON: a bulk export a batch consumer processes line by line as it arrives. `GET /bookings/events/export/chunked` isolates plain HTTP chunked transfer from either framing, so the underlying mechanism can be checked on its own. All three sit on the same deterministic five-step status progression (`CONFIRMED → IN_TRANSIT → IN_TRANSIT → IN_TRANSIT → DELIVERED`) that `EventGenerator.java` and `app/events.py` both produce; only the wall-clock `occurredAt` on each event varies between runs, because what this chapter teaches is event shape and delivery timing, not a frozen clock.

## The mechanism underneath: chunked transfer encoding

A normal HTTP/1.1 response tells the client how much is coming before it sends any of the body: `Content-Length: 1234`, then exactly 1,234 bytes. That header is a promise a server can only make once it knows the full size: which means computing or buffering the whole response first. Chunked transfer encoding, defined in RFC 9112 §7.1, is HTTP/1.1's answer to not knowing the size in advance: the server sends `Transfer-Encoding: chunked` instead of `Content-Length`, then writes the body as a sequence of length-prefixed chunks, each one a size line in hex followed by that many bytes, ending in a zero-length chunk that closes the body. The client reads chunks as they arrive and reassembles them; neither side needs the total up front.

Every endpoint in this chapter rides on this mechanism, whether or not the handler code ever mentions it by name. When a Quarkus `Multi<String>` or a FastAPI async generator produces values one at a time, the framework has no total length to advertise, so it falls back to chunked transfer automatically. The dedicated `/bookings/events/export/chunked` endpoint exists to let `verify.sh` check this mechanism in isolation, independent of SSE's `data:` framing or NDJSON's newline framing, by asserting the one header pair that proves it (`Transfer-Encoding: chunked` present, `Content-Length` absent):

```bash
status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' "$base/bookings/events/export/chunked")"
assert_status 200 "$status" "$stack GET /bookings/events/export/chunked"

assert_header_absent Content-Length "$headers_file" "$stack chunked export"
```

A missing `Content-Length` is not an oversight to fix: it is proof the server never computed a total size before it started writing. An endpoint that buffered its output internally and then handed the finished byte array to the framework would end up with a `Content-Length` header automatically, even though the status code and body would look identical. `Content-Length`'s absence is a structural fact about *how* the response was produced, which is why `verify.sh` checks it directly rather than inferring streaming from anything softer.

## Server-Sent Events: a live feed over plain HTTP

Server-Sent Events give a server a standing channel to push updates to a browser or any HTTP client, using nothing but a long-lived GET response with `Content-Type: text/event-stream`. Each update is a frame starting with `data:` and ending in a blank line (`data: {"status":"IN_TRANSIT"}\n\n`), and a client (the browser's native `EventSource`, or anything reading the stream line by line) processes each frame as it arrives rather than waiting for the connection to close. The format supports a handful of other fields (`event:` to name an event type, `id:` to let a reconnecting client resume from the last id it saw, `retry:` to set the reconnect delay), but a single `data:` line per update carries a `BookingEvent` just fine, and is what both stacks send here.

SSE's appeal for cargo tracking is that it needs nothing beyond HTTP: no new port, no protocol upgrade, no client library beyond what browsers ship natively. A client that loses the connection has the browser's `EventSource` retry automatically, built into the spec rather than something an application implements. The trade-off is direction: SSE is strictly server-to-client. A tracking dashboard that only displays incoming status changes is exactly what SSE is for; a client that also needs to send messages back over the same channel (bidding, chat, collaborative editing) needs something bidirectional, which is where Chapter 17 picks up the comparison with WebSockets.

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/{bookingId}/events")
@Produces(MediaType.SERVER_SENT_EVENTS)
@RestStreamElementType(MediaType.APPLICATION_JSON)
public Multi<BookingEvent> bookingEvents(@PathParam("bookingId") String bookingId) {
    if (store.get(bookingId) == null) {
        throw notFoundException(bookingId);
    }

    // ticks() emits 0, 1, 2, ... at a fixed cadence; starting AFTER the
    // interval (not at t=0) means the client sees the connection open
    // immediately but the first `data:` frame only arrives one interval
    // later — genuinely spaced out, not all buffered and flushed at
    // once. select().first(N) completes (closes) the stream after the
    // Nth tick instead of ticking forever.
    return Multi.createFrom().ticks()
            .startingAfter(Duration.ofMillis(EventGenerator.SSE_INTERVAL_MILLIS))
            .every(Duration.ofMillis(EventGenerator.SSE_INTERVAL_MILLIS))
            .onItem().transform(tick -> EventGenerator.eventFor(bookingId, tick.intValue()))
            .select().first(EventGenerator.SSE_EVENT_COUNT);
}
```

```python
async def _sse_event_stream(booking_id: str) -> AsyncIterator[str]:
    for i in range(SSE_EVENT_COUNT):
        await asyncio.sleep(SSE_INTERVAL_SECONDS)
        payload = event_for(booking_id, i)
        yield f"data: {json.dumps(payload)}\n\n"


@app.get("/bookings/{booking_id}/events")
async def booking_events(booking_id: str) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    return StreamingResponse(_sse_event_stream(booking_id), media_type="text/event-stream")
```

The two implementations converge on the same shape despite looking nothing alike. Quarkus works in Mutiny's reactive vocabulary: `Multi.createFrom().ticks()` is a reactive-streams source that emits on a timer, `@RestStreamElementType(MediaType.APPLICATION_JSON)` tells Quarkus REST to marshal each emitted `BookingEvent` as the JSON payload of one SSE `data:` frame, and `select().first(N)` turns an infinite ticker into a bounded five-event stream. FastAPI works in plain `async`/`await`: `_sse_event_stream` is an async generator that calls `asyncio.sleep` between `yield`s, and `StreamingResponse` sends each yielded string to the socket as it's produced. What matters in both is the same: the delay sits *between* frames being written to the socket, not before one write of everything at once.

## NDJSON: one JSON value per line

Newline-delimited JSON solves a narrower problem than SSE: how do you stream a sequence of JSON records without wrapping them in a JSON array? A JSON array (`[{...},{...},{...}]`) is not valid JSON until the closing `]` is written, so a client reading it with a standard parser cannot do anything useful with the first record until the server has also produced the last one: exactly the buffering problem streaming is supposed to avoid. NDJSON (media type `application/x-ndjson`, sometimes `application/jsonlines`) sidesteps this by putting each record on its own line with no enclosing array and no trailing comma: parse one line, get one complete, independently valid JSON value, move to the next. A consumer can start processing record one before record two exists, and a line that fails to parse doesn't invalidate every record around it the way a malformed array element would.

That makes NDJSON a natural fit for bulk/batch export: a client pulling ten thousand `BookingEvent` records to reconcile against its own store wants to process them incrementally, not materialize the whole response in memory before touching the first one. The example's `/bookings/events/export` endpoint produces ten such lines:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/events/export")
@Produces("application/x-ndjson")
public Multi<String> exportEvents() {
    return Multi.createFrom().items(IntStream.range(0, EventGenerator.EXPORT_EVENT_COUNT).boxed())
            .onItem().transform(i -> toJsonLine(EventGenerator.eventFor(EventGenerator.EXPORT_SAMPLE_BOOKING_ID, i)));
}
```

```python
async def _ndjson_export_stream() -> AsyncIterator[str]:
    for i in range(EXPORT_EVENT_COUNT):
        payload = event_for(EXPORT_SAMPLE_BOOKING_ID, i)
        yield json.dumps(payload) + "\n"


@app.get("/bookings/events/export")
async def export_events() -> Response:
    return StreamingResponse(_ndjson_export_stream(), media_type="application/x-ndjson")
```

FastAPI's side is unremarkable: `json.dumps` plus a trailing `\n`, yielded one line at a time, and `StreamingResponse` writes each yielded string straight to the socket. Quarkus's side needs one extra piece the Python side doesn't: `toJsonLine` pre-serializes each `BookingEvent` to a JSON string with `ObjectMapper` *before* handing it to the `Multi<String>` pipeline, and a dedicated `MessageBodyWriter` is registered to write that string's raw bytes to the wire. That second part is not decoration: without it, this endpoint silently produces broken NDJSON.

### The double-encoding gotcha

Quarkus REST ships a Jackson-based `MessageBodyWriter` that registers broadly enough to claim media types it doesn't specifically recognize. Left to its own devices, it looks at `Multi<String>` being produced for `application/x-ndjson`, decides "this is a Java object, serialize it as JSON," and does exactly that to a `String`: which means wrapping the string in quotes and escaping its embedded `\n` to the two characters `\n`. The result is a response that is *syntactically* one giant JSON string, not ten lines of JSON: each `BookingEvent` line, already perfectly valid JSON on its own, gets its newline escaped away and the whole thing re-quoted, so what should have been ten independently parseable records becomes an opaque blob that happens to look almost right until a consumer tries to split it on newlines and gets one line back instead of ten.

`NdjsonMessageBodyWriter` exists to intercept exactly this:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@Provider
@Produces("application/x-ndjson")
public class NdjsonMessageBodyWriter implements MessageBodyWriter<String> {

    @Override
    public boolean isWriteable(Class<?> type, Type genericType, Annotation[] annotations, MediaType mediaType) {
        return String.class.isAssignableFrom(type);
    }

    @Override
    public void writeTo(String line, Class<?> type, Type genericType, Annotation[] annotations,
            MediaType mediaType, MultivaluedMap<String, Object> httpHeaders, OutputStream entityStream)
            throws IOException {
        entityStream.write(line.getBytes(StandardCharsets.UTF_8));
    }
}
```

```python
# FastAPI has no equivalent gotcha: StreamingResponse writes each yielded
# str's UTF-8 bytes to the socket as-is, with no serialization step in
# between — there is no content-negotiation layer deciding how to encode a
# plain `str` the way JAX-RS's writer-lookup mechanism does for String.
```

Registered for exactly `application/x-ndjson` plus `String`, this writer wins the lookup for this one combination and writes the line's bytes straight to the output stream: no quoting, no escaping, no re-serialization of a value already serialized once. `StreamingResource#exportEvents` does the JSON encoding itself with `ObjectMapper`, appends the `\n`, and this writer's only job is to get out of the way. It's a small amount of code for a bug that would otherwise be invisible at the status-code and `Content-Type` level (the response is still `200`, still labeled `application/x-ndjson`, still full of recognizable JSON-looking text) and would only surface as a parse failure downstream, in whatever consumer tried to read the export line by line. FastAPI never faces this problem because nothing in its stack performs framework-level content negotiation on a plain `str`; a yielded string's bytes go to the socket exactly as written, one cost of JAX-RS's richer, more automatic serialization machinery showing up unexpectedly.

## Proving incremental delivery: the part that's easy to get wrong

Here is the fact this chapter's `verify.sh` was built around: a status code and a `Content-Type` header prove almost nothing about whether a response streamed. An SSE handler changed from "sleep, then emit, five times" to "sleep five times, then emit everything in one write, right before closing the connection" would still return `200`, still set `Content-Type: text/event-stream`, still deliver five well-formed `data:` frames with correct JSON inside. Every assertion made so far (status, headers, frame count, per-frame schema validity) would pass against that broken implementation exactly as against the correct one. The bug is real, and none of those checks can see it, because none look at *when* the bytes arrived, only at what they eventually contained.

The first instinct for measuring "when" is curl's built-in timing fields (`time_starttransfer` for time-to-first-byte, `time_total` for the whole request), and it turns out not to work here. Both Quarkus and FastAPI flush HTTP response *headers* to the socket the moment the handler returns its stream object, before the first event has even been generated. `time_starttransfer` counts header bytes as the first byte, so it comes back near-zero whether the body that follows is streamed incrementally or fully buffered. Subtracting it from `time_total` doesn't help either: that difference measures total compute time regardless of whether the output was written incrementally or all at once at the end. Two implementations differing exactly in the dimension this chapter cares about (incremental versus buffered delivery) produce indistinguishable curl timing numbers.

The example's actual test reads the stream the way a real streaming consumer would: line by line, timestamping each line the instant it's read, with no buffering of its own sitting in between:

```bash
while IFS= read -r line; do
  printf '%s|%s\n' "$(date +%s.%N)" "$line"
done < <(curl -sS -N --max-time 8 "$base/bookings/$booking_id/events")
```

`curl -N` disables curl's own output buffering, so each line reaches the `read` loop as soon as the socket delivers it. A server that truly spaces five frames 250ms apart produces five timestamps roughly 250ms apart, for a first-to-last spread near 1.0 second. A server that buffers everything internally and writes it all in one burst produces timestamps microseconds apart (the `read` loop drains them from the same OS pipe read, regardless of how long the server slept before writing), for a spread near zero, no matter how much internal sleep time it consumed. `verify.sh` asserts the spread is at least 0.6 seconds (60% of the 1.0-second ideal, enough margin for CI jitter, nowhere near a buffered implementation's result):

```bash
spread="$(awk -v a="$last_ts" -v b="$first_ts" 'BEGIN { printf "%.3f", a - b }')"
if ! awk_ge "$spread" "$SSE_MIN_SPREAD_SECONDS"; then
  fail "$stack SSE: frame-to-frame spread ${spread}s is below the ${SSE_MIN_SPREAD_SECONDS}s floor — these frames look BUFFERED (all arrived in one burst), not delivered incrementally"
fi
```

The example's README documents the regression this catches directly: change the FastAPI generator from yielding after each sleep to accumulating all five frames into a list and yielding the joined result once, and every existing check still passes (status 200, correct `Content-Type`, five valid frames) while the timing assertion fails immediately, reporting a spread around 0.014 seconds against the 0.6-second floor. NDJSON and the chunked endpoint don't carry an equivalent timing assertion, because their point is incremental *framing*, not a live feed with meaningful inter-record delay; they're checked for the things that matter in a bulk export instead: correct `Content-Type`, expected line count, every line independently schema-valid, and `Content-Length`'s absence as the structural proof that the server never pre-computed a total size.

{% include excalidraw.html file="16-streaming-modes" alt="Three streaming modes delivering pieces of data over one HTTP connection over time, shown left to right: chunked transfer encoding writing a series of length-prefixed byte chunks with no Content-Length known up front, Server-Sent Events emitting discrete data colon frames spaced out over a long-lived text/event-stream connection, and NDJSON writing one complete JSON object per newline-terminated line that a consumer can parse as each line arrives." caption="Figure 16.1: Chunked, SSE, and NDJSON: three ways to stream over HTTP." %}

## What sits between the server and a real client

None of this guarantees incremental delivery survives the trip across production infrastructure. A reverse proxy or ingress controller between a Kubernetes service and the public internet can buffer an upstream's chunked response and forward it only once a threshold of bytes has accumulated, or once the connection closes: exactly the behavior this chapter proves the *application* doesn't exhibit, reintroduced one layer up the stack where the application has no code of its own to fix it. A proxy's default buffering settings exist for good reasons (they absorb a slow or unreliable client without tying up an upstream connection), but those same defaults are what defeats a live SSE feed or a low-latency NDJSON stream, turning "updates every 250ms" back into "the whole thing at once." This is a recurring failure mode for exactly the services built here, not a hypothetical edge case, and it isn't solved in this chapter. Chapter 25 traces a request end to end through Compose, and Chapter 26's move to Kubernetes-ingress networking is where a real ingress in front of these same handlers settles whether it preserves this chapter's delivery timing.

## Proof

Quarkus comes up on port 8096, FastAPI on port 8016. The script creates a booking on each stack to mint an id, then drives all three endpoints: SSE (status, `Content-Type`, exactly five schema-valid frames, and the frame-to-frame timing spread), SSE against an unknown booking id (404 with a `Problem` body), the NDJSON export (status, `Content-Type`, exactly ten lines, each independently schema-valid against `BookingEvent`), and the dedicated chunked endpoint (status, `Transfer-Encoding: chunked` present, `Content-Length` absent, and at least the expected line count). It prints `PASS` only once every assertion holds for both stacks, including the timing floor, which is the one check in this chapter that distinguishes a response that merely claims to stream from one that actually does.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to which streaming mode fits a given need. Reach for <strong>SSE</strong> when the interaction axis is strictly one-directional, server-to-client, and lives over a connection a browser or long-running client is willing to hold open (a tracking dashboard, a notification feed, a progress indicator for work already covered by Chapter 10's async pattern but wanted live rather than polled). Reach for <strong>NDJSON</strong> when the shape is a bulk or batch sequence of independent records a consumer wants to start processing before the last one exists (exports, log tails, large result sets a client pipes into its own processing loop one line at a time), where there is no "live" element at all, just a wish to avoid materializing one huge array on either end. Reach for plain <strong>chunked transfer</strong> directly (no SSE or NDJSON framing on top) when the payload is a single large body whose size truly isn't known until generation finishes (a generated report, a computed file) and no record-level structure is needed. Skip all three for a client that needs to send data back over the same channel while the stream is open, or that needs multiplexed concurrent streams on one connection: that's a different interaction shape, and Chapter 17 is where WebSockets, webhooks, and gRPC streaming earn their place against this chapter's HTTP-native options.</p></div>

## Build, run, observe

```bash
cd examples/16-streaming && ./verify.sh
```

`verify.sh` brings both services up with `docker compose`, creates a booking on each stack, then checks the SSE, NDJSON export, and chunked-transfer endpoints, including a frame-to-frame timing assertion that proves the SSE stream arrives incrementally rather than in one buffered burst. Expect `PASS` once every assertion holds for both stacks; the full output from a real run is in `examples/16-streaming/README.md`.

## For deeper coverage

- [RFC 9112 §7.1: HTTP/1.1: Chunked Transfer Coding](https://www.rfc-editor.org/rfc/rfc9112#name-chunked-transfer-coding): the mechanism every endpoint in this chapter rides on.
- *Cloud Native Design Patterns*, stream-processing (same series, streaming and incremental delivery).
- *Cloud Native Design Patterns*, event-driven (same series, push-style delivery patterns).
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022).
