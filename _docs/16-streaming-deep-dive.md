---
title: "Streaming deep-dive"
order: 16
part: "Large payloads & streaming"
description: "Push data as it is produced: chunked transfer encoding, Server-Sent Events for live updates, and NDJSON for bulk export, and how to check that a response arrives incrementally instead of buffered."
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

A 2 MiB manifest exists in full before a client asks for a slice of it. A cargo-status feed doesn't: it has no final byte until the next status change, possibly minutes away. A bulk export of booking events can go out as each record is ready instead of after the last one is generated and the array is closed with a `]`. Buffering the whole body is wasteful for a file and wrong for a feed, because there may be no whole body to wait for. Streaming means writing the response before you know how it ends.

Three endpoints stream the same `BookingEvent` from the shared schema over three wire formats:

| Endpoint | Format | Use |
|---|---|---|
| `GET /bookings/{id}/events` | Server-Sent Events | Live, ordered status feed on one long-lived connection |
| `GET /bookings/events/export` | NDJSON | Bulk export a consumer processes line by line |
| `GET /bookings/events/export/chunked` | Plain chunked transfer | The mechanism alone, without SSE or NDJSON framing |

All three emit the same five-step status progression, `CONFIRMED`, three times `IN_TRANSIT`, then `DELIVERED`.

{% include excalidraw.html file="16-streaming-modes" alt="Three streaming modes delivering pieces of data over one HTTP connection over time, shown left to right: chunked transfer encoding writing a series of length-prefixed byte chunks with no Content-Length known up front, Server-Sent Events emitting discrete data colon frames spaced out over a long-lived text/event-stream connection, and NDJSON writing one complete JSON object per newline-terminated line that a consumer can parse as each line arrives." caption="Figure 16.1: Chunked, SSE, and NDJSON: three ways to stream over HTTP." %}

## Chunked transfer encoding

An HTTP/1.1 response normally states its size first: `Content-Length: 1234`, then exactly that many bytes. A server can only make that promise once it has computed or buffered the whole response. Chunked transfer encoding (RFC 9112 section 7.1) drops the promise. The server sends `Transfer-Encoding: chunked` and writes length-prefixed chunks, each a hex size line followed by that many bytes, ending with a zero-length chunk. The client reassembles chunks as they arrive.

Every endpoint here rides on it. When a Quarkus `Multi<String>` or a FastAPI async generator yields values one at a time, the framework has no total to advertise and falls back to chunked automatically. The dedicated chunked endpoint exposes the mechanism: `Transfer-Encoding: chunked` present and `Content-Length` absent.

```bash
status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' "$base/bookings/events/export/chunked")"
assert_status 200 "$status" "$stack GET /bookings/events/export/chunked"

assert_header_absent Content-Length "$headers_file" "$stack chunked export"
```

A missing `Content-Length` is a structural fact about how the response was produced. An endpoint that buffered its output and handed the framework a finished byte array would get a `Content-Length` automatically, with the same status and the same body.

## Server-Sent Events

Server-Sent Events (SSE) give the server a standing channel to push updates over a long-lived `GET` with `Content-Type: text/event-stream`. Each update is a frame that starts with `data:` and ends with a blank line:

```
data: {"status":"IN_TRANSIT"}

```

The format also has `event:` to name a type, `id:` so a reconnecting client resumes from the last id it saw, and `retry:` to set the reconnect delay. One `data:` line per update is enough to carry a `BookingEvent`.

SSE needs nothing beyond HTTP: no new port, no upgrade, and the browser's `EventSource` is built in, including automatic reconnect. The cost is direction. SSE is server-to-client only, so a tracking dashboard fits and a client that must send messages back over the same channel does not.

Quarkus returns a Mutiny `Multi<BookingEvent>` from a timer source, annotated `@Produces(MediaType.SERVER_SENT_EVENTS)` with `@RestStreamElementType(MediaType.APPLICATION_JSON)` so each item becomes one JSON `data:` frame. `startingAfter` delays the first tick by one interval, and `select().first(N)` closes the stream after the last event. FastAPI returns a `StreamingResponse` over an async generator that calls `asyncio.sleep` between `yield`s:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/{bookingId}/events")
@Produces(MediaType.SERVER_SENT_EVENTS)
@RestStreamElementType(MediaType.APPLICATION_JSON)
public Multi<BookingEvent> bookingEvents(@RestPath String bookingId) {
    if (store.get(bookingId) == null) {
        throw notFoundException(bookingId);
    }

    // ticks() emits 0, 1, 2, ... at a fixed cadence; starting AFTER the
    // interval (not at t=0) means the client sees the connection open
    // immediately but the first `data:` frame only arrives one interval
    // later: genuinely spaced out, not all buffered and flushed at
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

In both stacks the delay sits between writes to the socket, not before one write of everything.

## NDJSON

A JSON array isn't valid until the closing `]`, so a standard parser can't use the first record before the server has produced the last. Newline-delimited JSON (`application/x-ndjson`) puts one complete JSON value on each line, with no enclosing array and no commas between records. A consumer parses a line, gets a record, and moves on. A malformed line spoils one record, not the whole response. That suits bulk export, where a client reconciling ten thousand events shouldn't hold the full response in memory.

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

### The Quarkus double-encoding gotcha

Quarkus REST's Jackson `MessageBodyWriter` claims media types it doesn't specifically recognize. Handed a `Multi<String>` for `application/x-ndjson`, it serializes each string as JSON again: it wraps the line in quotes and escapes the newline to the two characters `\n`. The response is still `200` and still labeled `application/x-ndjson`, but it is one JSON string instead of ten lines, and the break shows up only when a consumer splits on newlines.

`toJsonLine` serializes each event with `ObjectMapper` and appends the newline. A writer registered for exactly `application/x-ndjson` and `String` then writes the bytes as they are:

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

FastAPI has no equivalent problem. `StreamingResponse` writes each yielded string's UTF-8 bytes to the socket with no serialization step in between.

## Check that delivery is incremental

A status code and a `Content-Type` say nothing about whether a response streamed. Change an SSE handler from "sleep, then emit, five times" to "sleep five times, then emit everything in one write" and it still returns `200`, still sets `text/event-stream`, and still delivers five valid frames. Only the arrival times differ.

curl's timing fields don't separate the two. Both stacks flush headers the moment the handler returns its stream object, so `time_starttransfer` is near zero for a streamed and a buffered body alike, and `time_total` measures compute time either way.

Timestamp each line as it is read instead:

```bash
while IFS= read -r line; do
  printf '%s|%s\n' "$(date +%s.%N)" "$line" >> "$timed_file"
done < <(curl -sS -N --max-time 8 "$base/bookings/$booking_id/events")
```

`curl -N` turns off curl's output buffering, so each line reaches the loop when the socket delivers it. Five frames 250 ms apart give a first-to-last spread near 1.0 second. A server that buffers and writes once gives timestamps microseconds apart, a spread near zero. Requiring a spread of at least 0.6 seconds leaves margin for CI jitter and is nowhere near a buffered result.

NDJSON and the chunked endpoint carry no timing check. Their point is incremental framing, so they are checked for content type, line count, per-line schema validity and the absent `Content-Length`.

## What sits between server and client

Incremental delivery can still be lost on the way. A reverse proxy or ingress controller can buffer an upstream chunked response and forward it only after a byte threshold or when the connection closes. Default proxy buffering absorbs slow clients without tying up upstream connections, and it also turns "an update every 250 ms" back into "everything at once". The failure sits one layer above the application, which has no code to fix it. Whether a given ingress preserves the timing is settled only by running the same line-timestamp check through it.

## When to use each mode

| Need | Use | Why |
|---|---|---|
| Live feed, server to client, held open by a browser or long-running client | SSE | Plain HTTP, native `EventSource`, automatic reconnect |
| Bulk sequence of independent records consumed as they arrive | NDJSON | No enclosing array, per-record parsing, no full materialization |
| One large body whose size is unknown until generation ends | Plain chunked transfer | No record structure needed |
| Client sends data back on the same channel, or many multiplexed streams | None of these | A bidirectional protocol (WebSockets, gRPC streaming) fits better |

> **🤖 Explore with your agent**
>
> "In examples/16-streaming, add a `GET /bookings/{id}/events/export` NDJSON endpoint that streams the same `BookingEvent` lines for one booking on both the Quarkus and FastAPI stacks. Keep the response chunked with no `Content-Length`, and make sure the Quarkus version isn't double-encoded by the String writer."
>
> Check: `curl -sS -N -D - http://localhost:8096/bookings/<id>/events/export` shows `Transfer-Encoding: chunked`, no `Content-Length`, and one JSON object per line, not one quoted string.

## Build, run, observe

```bash
cd examples/16-streaming && ./verify.sh
```

The script starts both stacks with `docker compose` (Quarkus on port 8096, FastAPI on port 8016), creates a booking on each, and checks all three endpoints, including the SSE timing spread. It prints `PASS` when every check holds on both stacks. Full output is in `examples/16-streaming/README.md`.

Experiments:

- Change the FastAPI generator to collect all five frames in a list and yield the joined string once. Status, content type and frame count still pass, and the timing check fails with a spread near 0.014 seconds against the 0.6-second floor.
- Remove the Quarkus `NdjsonMessageBodyWriter`. The export still returns `200`, but the line count drops from ten to one.
- Request an unknown booking id on the SSE endpoint. Both stacks return `404` with a `Problem` body, not an open stream.

## For deeper coverage

- [RFC 9112 section 7.1: Chunked Transfer Coding](https://www.rfc-editor.org/rfc/rfc9112#name-chunked-transfer-coding): the mechanism every endpoint here rides on.
- *Cloud Native Design Patterns*, stream-processing (same series, streaming and incremental delivery).
- *Cloud Native Design Patterns*, event-driven (same series, push-style delivery patterns).
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022).
