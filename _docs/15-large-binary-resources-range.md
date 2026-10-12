---
title: "Large binary resources & Range requests"
order: 15
part: "Large payloads & streaming"
description: "Serve a large manifest without forcing clients to download it whole: HEAD for metadata, Accept-Ranges, byte-range requests answered with 206 Partial Content and Content-Range, and 416 for an unsatisfiable range."
duration: "26 min"
---

Every resource this site has built so far has been a JSON document small enough that "fetch it" and "fetch all of it" mean the same thing. A booking's manifest breaks that assumption: it is the consolidated listing of every cargo item on a shipment, and in this chapter's example it is a deterministic 2 MiB binary blob — comfortably past the point where "just `GET` the whole thing every time" is a reasonable default. A client checking whether a manifest has even been generated yet shouldn't have to pull 2 MiB to find out. A client resuming a download that died at byte 1,400,000 shouldn't have to restart from zero. A PDF viewer jumping to page 40 shouldn't have to materialize pages 1–39 first. All three needs point at the same HTTP mechanism: let a client ask for less than the whole resource, and tell it up front whether that's even on the table.

This is a different shape of "too much data" than Chapter 8's pagination. Pagination slices a *collection* (a list of `Booking` resources) into pages a client walks one at a time, each page a complete, independently addressable JSON document. A manifest is a single resource, not a collection, and there's no natural item boundary to paginate by; "page 3 of the manifest" means nothing on its own. What a client wants instead is an arbitrary byte window into one opaque blob, which is exactly what `Range` is built for. The two mechanisms solve adjacent problems (too many items, and too many bytes) with different vocabulary for that reason, and a system that tried to paginate a binary document with `limit`/`cursor` parameters would be reinventing `Range` badly.

`/bookings/{bookingId}/manifest` in this chapter's example (`examples/15-range-requests/`) answers three different requests against the same URI: `HEAD` for metadata, a plain `GET` for the full body, and a `GET` carrying a `Range` header for a slice of it. RFC 9110 §14 is the governing spec — it predates this particular API by decades, because range requests are the same mechanism HTTP has always used for resumable downloads and media seeking, not something invented for this chapter's manifest.

## HEAD: metadata without the cost

A client that wants to know how big a manifest is, or whether the server supports range requests on it at all, has no reason to pay for the bytes to find out. `HEAD` answers exactly that question: same URI, same routing, same 404 behavior as `GET`, but no body on the wire. Both stacks' `HEAD` handlers look up the booking, generate (or fetch from cache) the manifest bytes to learn the total size, and return headers only:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@HEAD
public Response head(@PathParam("bookingId") String bookingId) {
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

Two headers carry the entire contract. `Content-Length` is the manifest's exact size in bytes: the `TOTAL` that every subsequent `Range` request and `Content-Range` response gets checked against. `Accept-Ranges: bytes` is the capability advertisement: it tells a client that this resource understands byte-unit `Range` headers, so a download manager or video player probing an unfamiliar server knows whether resuming or seeking is worth attempting before it tries. A resource that doesn't support ranges either omits the header or sends `Accept-Ranges: none`; either way, a client that respects the advertisement won't waste a round trip asking for `bytes=0-1023` against something that's going to ignore the request and hand back the full body anyway. `HEAD`'s response here is, by construction, exactly what `GET`'s headers would be (same `Content-Length`, same `Accept-Ranges`) minus the body that made `GET` expensive.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>The example's README documents a curl trap worth knowing before you reach for it on a real server: <code>curl -X HEAD</code> is not the same request as <code>curl -I</code> (or <code>curl --head</code>). <code>-X HEAD</code> just swaps the method string on an otherwise ordinary GET-shaped request — curl still expects a body matching the response's <code>Content-Length</code> and will hang waiting for bytes a correct HEAD response never sends. Only <code>-I</code>/<code>--head</code> tells libcurl the request really is a HEAD, so it stops reading after the headers. <code>verify.sh</code> uses <code>--head</code> for exactly this reason.</p></div>

## Range requests and 206 Partial Content

A plain `GET` with no `Range` header behaves the way `GET` always has: the full manifest, `200`, `Content-Length` set to the total size. The interesting branch starts when a `Range` header shows up. `Range: bytes=0-1023` asks for the first 1,024 bytes — byte offsets, inclusive on both ends, so `0-1023` is 1,024 bytes, not 1,023. A server that honors it answers `206 Partial Content`, not `200`, and attaches `Content-Range: bytes 0-1023/2097152` so the client can see exactly which slice it got and how large the whole resource is, even though it only asked for a piece of it. The body is exactly those 1,024 bytes — nothing padded, nothing truncated at a block boundary the server found convenient.

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

`bytes=START-END` is the bounded form, but the grammar in RFC 9110 §14.1.2 allows two shorter forms that both stacks parse off the same regex (`^bytes=(\d*)-(\d*)$`, matching an optional start and an optional end around the dash). An **open range**, `bytes=1024-`, means "from byte 1024 to the end" — the end group is empty, so both implementations fill it in as `total - 1` before computing the slice. A **suffix range**, `bytes=-500`, means "the last 500 bytes" — here the *start* group is empty, so the server computes `start = max(0, total - suffixLength)` and serves from there to the end. That `max(0, …)` matters: a suffix range larger than the resource itself (`bytes=-999999999` against a 2 MiB manifest) should clamp to the whole resource, not underflow into a negative offset.

Clamping shows up again at the top end: `end = min(end, total - 1)`. A client is allowed to ask for `bytes=0-99999999` against a resource it doesn't know the exact size of yet — "give me up to 100 MB, however much there is" — and a correct server serves what it has rather than erroring on a request that merely overshoots. The end of the range is advisory past the resource's real length; only the *start* being past the end is a hard failure, because there's nothing at all to serve from there.

That hard failure path matters just as much as the happy one. If a `Range` header doesn't match the grammar — anything that isn't `bytes=` followed by the two-group pattern — both implementations treat it as if no `Range` header had been sent at all, falling straight through to the full `200` response. That's what RFC 9110 §14.2 specifies: a server receiving a `Range` header it can't parse ignores it rather than rejecting the request outright. A client sending a slightly malformed range still gets a usable response, the whole resource, instead of an error for a header it probably generated incorrectly.

Both stacks' regex also fixes the ceiling on what this chapter's implementation supports: one range per request. RFC 9110 §14.1.2 permits a comma-separated list of ranges in a single `Range` header — `bytes=0-99,200-299` — answered with a `multipart/byteranges` body, one part per range, each with its own nested `Content-Range`. Neither implementation here parses that form; a multi-range `Range` header fails the single-range regex and falls back to a full `200`, the same as any other malformed header. That's a chosen scope boundary, not an oversight: multipart ranges exist for clients that want several disjoint windows in one round trip, and a real manifest-serving API would need to decide whether that case is common enough to earn the extra response-encoding complexity. This chapter's point is the single-range mechanism every resumable-download and media-seeking client relies on; multipart ranges are a documented extension past it, not a requirement to prove the pattern.

## 416 Range Not Satisfiable

A syntactically valid range can still be impossible to satisfy: `start >= total` means the client is asking for bytes past the end of a resource that doesn't have them. The response for that is `416 Range Not Satisfiable`, and its one required piece of information is `Content-Range: bytes */total` — the asterisk standing in for "no range," paired with the actual size so the client can recompute a valid request. A client retrying `bytes=99999999-199999999` against a 2 MiB manifest sees `bytes */2097152` and immediately knows the resource is smaller than it assumed, without needing a separate `HEAD` call to find out.

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

Both stacks keep the `416` body minimal — no `Problem` entity, just the status and the one header. RFC 9110 permits a body on `416` but doesn't require one, and `Content-Range: bytes */total` alone is already enough for a well-behaved client to self-correct, so there's nothing a JSON body would add except an extra content-type negotiation the manifest's binary media type doesn't otherwise need. An unknown `bookingId`, by contrast, does get a full `Problem` body on `404` — that failure happens before there's a manifest to have a size at all, so `application/problem+json`'s structured `title`/`status`/`detail` is the right shape there, same as every other 404 on this site since Chapter 6.

## Why this is worth the extra branches

The payoff for all of this branching is behavior a plain `200`-only `GET` endpoint can't offer at any price. A download interrupted at 60% doesn't restart from zero — the client reissues the request with `Range: bytes=1258292-`, picking up exactly where it left off, because `Accept-Ranges: bytes` told it that was possible before it tried. A video player seeking to the middle of a file requests the byte range covering that timestamp's frames instead of streaming everything before it first. A download manager splitting one large file across several parallel connections requests disjoint ranges concurrently and reassembles them locally, turning one slow stream into several faster ones. None of these are exotic use cases bolted onto HTTP — they're the reason `Range` exists, and a manifest, PDF, video, or disk image that supports it transparently gets all three for the cost of implementing one parsing branch correctly.

The cost side is real too, and worth naming rather than glossing over. Every additional response shape (`200` full, `206` partial, `416` unsatisfiable, plus the fallback-to-`200` on a malformed header) is a branch a test suite has to cover independently, because each one has its own status code and header contract a client might depend on. A server that gets the boundary conditions wrong (an off-by-one on `end`, a `start` that isn't checked against `total` before slicing) doesn't usually crash; it serves a byte or two short of what it claimed in `Content-Range`, or it throws an array-bounds exception a client experiences as a dropped connection mid-download. That failure mode is quiet by nature: a `206` that's merely an off-by-one on its byte count looks, to a client not checking the exact length, exactly like a correct `206`.

{% include excalidraw.html file="15-range-request-sequence" alt="A sequence diagram showing a client first sending HEAD to a manifest endpoint and receiving 200 with Accept-Ranges and Content-Length metadata but no body, then sending GET with a Range header and receiving 206 Partial Content with a Content-Range header and exactly the requested byte slice as the body, then sending GET with an out-of-bounds Range header and receiving 416 Range Not Satisfiable with a Content-Range header of bytes */total and no body." caption="Figure 15.1 — HEAD, a 206 Range response, and a 416." %}

## Proof

```bash
cd examples/15-range-requests
./verify.sh
```

The script brings up Quarkus on port 8095 and FastAPI on port 8015, creates a booking on each stack to mint an id, then drives the full sequence against that booking's manifest: `HEAD` (checking `Accept-Ranges` and capturing `Content-Length` as `TOTAL`), a full `GET` (checking the body is exactly `TOTAL` bytes), a bounded `Range: bytes=0-1023` (checking `206`, the exact `Content-Range` string, and exactly 1,024 bytes of body), an open `Range: bytes=1024-` (checking the range runs to `TOTAL-1`), an unsatisfiable range past `TOTAL` (checking `416` and `Content-Range: bytes */TOTAL`), and `HEAD`/`GET` against an unknown booking id (checking `404` with a schema-valid `Problem`). It checks exact byte counts and exact header values throughout, not just status codes.

The README documents two regressions worth triggering by hand to see that discipline pay off. The first swaps the `206` for a `200` in the bounded-range branch: the handler still slices the right bytes and still sets `Content-Range`, but reports the wrong status. Re-running `verify.sh` fails immediately: `expected HTTP 206, got 200`, because `assert_status` checks the exact code the spec requires for a partial response, not just "some 2xx came back". The second is subtler: drop the `-1` off the end offset in the `Content-Range` header, so a correct `206` response advertises `bytes 0-1024/2097152` for a request that actually returned bytes `0-1023`. The status code is right, the byte count in the body is even right, and a test that only checked those two things would pass. `verify.sh` catches it anyway, because it parses `Content-Range` and compares the literal string against what the request implies: `expected Content-Range 'bytes 0-1023/2097152', got 'bytes 0-1024/2097152'`. Revert either edit and the run goes back to `PASS` for both stacks. The lesson in both cases is the same one Chapter 13's purge example made about soft delete: a response that looks plausible from the outside (right status, right-ish headers) can still disagree with itself in a way only an assertion that checks the *relationship* between fields, not each field in isolation, will ever catch.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to whether a resource needs Range support at all. Reach for it when the payload is large enough that "download the whole thing" is itself a cost worth avoiding — media files, PDFs, disk images, any document measured in megabytes rather than kilobytes — and when the evolution axis includes resumability or seeking as a real client need, not a hypothetical one. Operational constraints tip the decision further: a manifest served to a mobile client on an unreliable connection, or to many clients fetching overlapping byte windows from a CDN edge, benefits from Range support in proportion to how often a full download would otherwise fail partway through. Skip it for small, uniformly-sized JSON resources — the same documents this site has served since Chapter 3 — where the entire body is cheaper to transfer than the extra round trip a <code>HEAD</code> probe would cost, and where there is no meaningful "partial" view of a 2&nbsp;KB payload worth constructing. Client diversity matters too: Range support is only worth building once a realistic client population includes something that will actually use it — a browser's native video element, a download manager, a PDF viewer with lazy page loading — rather than JSON API consumers that always want the whole representation anyway.</p></div>
