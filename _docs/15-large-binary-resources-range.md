---
title: "Large binary resources & Range requests"
order: 15
part: "Large payloads & streaming"
description: "Serve a large manifest without forcing clients to download it whole: HEAD for metadata, Accept-Ranges, byte-range requests answered with 206 Partial Content and Content-Range, and 416 for an unsatisfiable range."
duration: "26 min"
---

## Learning objectives

By the end of this chapter you can:

- Implement `HEAD` to expose `Content-Length` and `Accept-Ranges: bytes` without paying for the body.
- Parse bounded, open (`bytes=1024-`) and suffix (`bytes=-500`) `Range` forms and compute the byte slice.
- Answer a satisfiable range with `206 Partial Content` and an exact `Content-Range`.
- Answer an out-of-bounds range with `416 Range Not Satisfiable` and `Content-Range: bytes */total`.
- Decide when a resource is large enough to justify Range support.

## Why this matters

A booking's manifest lists every cargo item on a shipment, and here it is a deterministic 2 MiB binary blob. A client checking whether a manifest exists shouldn't pull 2 MiB to find out. A client resuming a download that died at byte 1,400,000 shouldn't restart from zero. A PDF viewer jumping to page 40 shouldn't fetch pages 1 to 39 first. All three need the same thing: ask for less than the whole resource, and learn up front whether that's possible.

Pagination slices a collection into pages, each a complete JSON document. A manifest is one resource with no item boundary, and "page 3 of the manifest" means nothing. The client wants an arbitrary byte window into an opaque blob, which is what `Range` is for. Paginating a binary document with `limit` and `cursor` would reinvent `Range` badly.

`/bookings/{bookingId}/manifest` answers three requests on one URI: `HEAD` for metadata, `GET` for the full body, and `GET` with a `Range` header for a slice. RFC 9110 section 14 governs. Range requests are the mechanism HTTP has always used for resumable downloads and media seeking.

## Pattern: Range request

### The problem

A large resource served only as a full `200` forces every client to download all of it: to learn its size, to resume after a failure, or to read one window.

### The solution

**Advertise byte-range support with `Accept-Ranges`, answer a `Range` header with `206` and the exact slice, and reject an impossible range with `416`.**

### How Quarkus and FastAPI model it

`HEAD` returns the headers `GET` would, without the body. `Content-Length` is the total that every later `Range` and `Content-Range` is checked against. `Accept-Ranges: bytes` tells a client that resuming or seeking is worth attempting. A resource without range support omits it or sends `none`.

{% include codetabs.html langs="Quarkus|Python" %}

```java
@HEAD
public Response head(@RestPath String bookingId) {
    if (store.get(bookingId) == null) {
        return notFound(bookingId);
    }
    byte[] manifest = ManifestGenerator.forBooking(bookingId);
    return Response.ok()
            .header("Accept-Ranges", "bytes")
            .header("Content-Length", manifest.length)
            .build();
}
```

```python
@app.head("/bookings/{booking_id}/manifest")
def head_manifest(booking_id: str) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    data = get_manifest(booking_id)
    return Response(
        status_code=200,
        headers={"Accept-Ranges": "bytes", "Content-Length": str(len(data))},
    )
```

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p><code>curl -X HEAD</code> only swaps the method string, so curl waits for a body that a correct HEAD response never sends and hangs. Use <code>curl -I</code> (or <code>--head</code>), which tells libcurl to stop after the headers.</p></div>

### 206 Partial Content

A `GET` without `Range` returns the full manifest with `200`. `Range: bytes=0-1023` asks for the first 1,024 bytes: offsets are inclusive on both ends. The server answers `206 Partial Content` with `Content-Range: bytes 0-1023/2097152`, so the client sees which slice it got and the total, and the body is exactly those bytes.

{% include codetabs.html langs="Quarkus|Python" %}

```java
if (start >= total || start > end) {
    return unsatisfiable(total);
}
end = Math.min(end, total - 1);

int length = (int) (end - start + 1);
byte[] slice = Arrays.copyOfRange(manifest, (int) start, (int) start + length);

return Response.status(206)
        .entity(slice)
        .type("application/pdf")
        .header("Accept-Ranges", "bytes")
        .header("Content-Range", "bytes " + start + "-" + end + "/" + total)
        .header("Content-Length", length)
        .build();
```

```python
if start >= total or start > end:
    return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})

end = min(end, total - 1)
chunk = data[start : end + 1]
return Response(
    content=chunk,
    status_code=206,
    media_type="application/pdf",
    headers={
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{total}",
        "Content-Length": str(len(chunk)),
    },
)
```

Both stacks parse the header with `^bytes=(\d*)-(\d*)$`, which allows three forms:

| Form | Meaning | Slice |
|---|---|---|
| `bytes=0-1023` | Bounded | Bytes 0 to 1023 |
| `bytes=1024-` | Open | From 1024 to `total - 1` |
| `bytes=-500` | Suffix | `start = max(0, total - 500)` to the end |

The `max(0, ...)` clamps a suffix longer than the resource to the whole resource instead of a negative offset. The end clamps too, with `end = min(end, total - 1)`: `bytes=0-99999999` against a smaller resource serves what exists. Only a start past the end is a hard failure.

A `Range` header that doesn't match the grammar is ignored and the full `200` returns, as RFC 9110 section 14.2 specifies. Multi-range requests (`bytes=0-99,200-299`, answered with `multipart/byteranges`) fail the single-range pattern and fall back to the full `200`. That's a scope choice: multipart ranges earn their encoding complexity only when clients want several disjoint windows in one round trip.

### 416 Range Not Satisfiable

A valid range can still be impossible: `start >= total` asks for bytes past the end. The response is `416` with `Content-Range: bytes */total`, which gives the client the real size so it can retry without a separate `HEAD`:

{% include codetabs.html langs="Quarkus|Python" %}

```java
private Response unsatisfiable(int total) {
    return Response.status(416)
            .header("Content-Range", "bytes */" + total)
            .build();
}
```

```python
if start >= total or start > end:
    return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
```

The `416` has no body, since the header is enough to self-correct. An unknown `bookingId` gets a full `application/problem+json` `404`, because that failure happens before there is a manifest to size.

{% include excalidraw.html file="15-range-request-sequence" alt="A sequence diagram showing a client first sending HEAD to a manifest endpoint and receiving 200 with Accept-Ranges and Content-Length metadata but no body, then sending GET with a Range header and receiving 206 Partial Content with a Content-Range header and exactly the requested byte slice as the body, then sending GET with an out-of-bounds Range header and receiving 416 Range Not Satisfiable with a Content-Range header of bytes */total and no body." caption="Figure 15.1: HEAD, a 206 Range response, and a 416." %}

## What it buys, and what it costs

An interrupted download resumes with `Range: bytes=1258292-` instead of restarting. A video player seeks by requesting the bytes for that timestamp. A download manager fetches disjoint ranges over parallel connections and reassembles them.

Each response shape (`200`, `206`, `416`, and the fallback to `200`) has its own status and header contract, so each needs its own coverage. Boundary errors rarely crash. An off-by-one on `end` serves a byte short of what `Content-Range` claimed, or an array-bounds exception shows up as a dropped connection mid-download. A `206` that is one byte off looks like a correct `206` to a client that doesn't check the length.

## When not to use it

| Add Range support | Skip it |
|---|---|
| Payload is megabytes: media, PDFs, disk images | Small JSON documents where the whole body costs less than a `HEAD` round trip |
| Clients resume or seek: mobile on unreliable links, CDN edges serving overlapping windows | Clients that always want the whole representation |
| A realistic client will use it: a video element, a download manager, a lazy PDF viewer | No consumer that sends `Range` |

> **🤖 Explore with your agent**
>
> "In examples/15-range-requests, extend the `Range` handling for `GET /bookings/{bookingId}/manifest` in the Quarkus `ManifestResource` and the FastAPI `app/main.py` to accept two comma-separated ranges (`bytes=0-99,200-299`) and answer `206` with a `multipart/byteranges` body, one part per range, each with its own `Content-Range`. Keep single ranges, the `416` path and the fall-back to a full `200` for a malformed header unchanged."
>
> Check: `curl -s -D - -o /dev/null -H 'Range: bytes=0-99,200-299' localhost:8095/bookings/<id>/manifest` shows `206` and a `multipart/byteranges` content type, and `./verify.sh` still prints `PASS`.

## Build, run, observe

```bash
cd examples/15-range-requests && ./verify.sh
```

The script starts Quarkus on port 8095 and FastAPI on port 8015, creates a booking on each, and runs `HEAD`, a full `GET`, a bounded range, an open range, an unsatisfiable range and an unknown booking against the manifest. It checks exact byte counts and exact `Content-Range` strings, and prints `PASS` when both stacks agree.

- Return `200` instead of `206` in the bounded-range branch. The slice and `Content-Range` are right and the run fails: `expected HTTP 206, got 200`.
- Drop the `-1` from the end offset in `Content-Range`, so the header says `bytes 0-1024/2097152` for a body that is bytes 0 to 1023. Status and byte count are right, and the run fails on the literal header string.

## For deeper coverage

- [RFC 9110 section 14: HTTP Semantics, Range Requests](https://www.rfc-editor.org/rfc/rfc9110#name-range-requests): the governing spec for `Range`, `Accept-Ranges`, `Content-Range` and `416`.
- *Cloud Native Design Patterns*, appendix-a-protocols (same series, protocol fundamentals appendix).
- Gough, Bryant & Auburn, *Mastering API Architecture* (O'Reilly, 2022).
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022).
