---
title: "REST over HTTP/2 & HTTP/3"
order: 19
part: "Performance & transport"
description: "What changes for a REST API under the hood across HTTP versions: HTTP/2 multiplexing and HPACK, TCP head-of-line blocking, and HTTP/3 over QUIC with stream isolation, connection migration, and 0-RTT."
duration: "26 min"
---

## Learning objectives

By the end of this chapter you can:

- Explain why HTTP/1.1 forces parallel connections and what that costs under REST-shaped traffic.
- Explain HTTP/2's multiplexed streams and `HPACK` header compression, and why TCP head-of-line blocking survives underneath them.
- Explain how HTTP/3 over QUIC isolates per-stream loss, and what connection migration and 0-RTT buy over HTTP/2.
- Force protocol negotiation with `curl --http2-prior-knowledge`/`%{http_version}` rather than trusting a `200` response alone.
- Apply the Chapter 2 axes to decide when HTTP/3 is worth the mandatory-TLS/UDP operational cost.

## Why this matters

Every chapter so far has treated the resource model, the status codes, the headers, and the framing of a response as the whole story. That is the whole story for REST's contract (methods, status codes, representations, hypermedia), but it says nothing about which wire protocol version carried those bytes between client and server. A `GET /bookings/{id}` that returns `200` with a JSON body is equally correct over HTTP/1.1, HTTP/2, or HTTP/3; the resource, method, and representation never change. What changes underneath is how many exchanges can share a connection, how much of each request is redundant bytes on the wire, and what happens when a single lost packet hits the network between client and server. This chapter is about that layer (transport, not semantics) and closes Part 8 with the smallest possible example: one endpoint, one JSON body, three ways of carrying it.

## HTTP/1.1: one request at a time, per connection

HTTP/1.1's model is a single request in flight per TCP connection. A client sends a request, waits for the full response, and only then can send the next one on that same connection. Pipelining (queuing several requests before any response arrives) is part of the 1.1 spec on paper, but no production client uses it, because one slow or malformed response anywhere in the pipeline jams the whole queue behind it. Browsers settled on a workaround instead: open several parallel TCP connections to the same host (six per origin was the common ceiling) and spread requests across them so one slow response doesn't stall every pending one.

That workaround has a real cost. Every parallel connection pays its own TCP handshake, its own TLS handshake if the origin is `https://`, and its own slow-start ramp before it reaches full throughput, multiplied by however many connections the client opens to get around one connection only doing one thing at a time. A REST API serving a UI that fires off a resource list followed by a dozen detail fetches pays that multiplication directly: a dozen requests queueing behind six sockets, each socket re-paying setup costs the others already paid. None of this touches the contract (the booking resource, the `200`, the JSON shape are unaffected), but it sets a latency floor under every response that has nothing to do with how fast the server computed it.

## HTTP/2: multiplexed streams, one connection, HPACK

HTTP/2 fixes the "one connection, one thing at a time" problem directly, by changing the framing underneath HTTP rather than anything in REST's request/response model. Instead of a text-based request line followed by headers followed by a body, HTTP/2 wraps everything in a binary framing layer: requests and responses split into length-prefixed frames (HEADERS, DATA, SETTINGS, and others) each tagged with a stream identifier, many of them interleaved over a single TCP connection, with the receiving end reassembling each stream's frames back into a complete request or response. The multiplexing browsers used to fake with six parallel connections now happens natively on one: a resource list and a dozen detail fetches can all be in flight on the same socket, none waiting for the others, with no multiplication of handshake costs.

The second piece is header compression. Every HTTP request carries a pile of repeated header fields (`User-Agent`, cookies, `Accept`, authorization tokens) that barely change from one request to the next on the same connection. HTTP/1.1 sends all of that in full, every time. HTTP/2's **HPACK** maintains a shared, stateful compression table between client and server for the life of the connection, so a header field sent once needs only a small reference on every subsequent request instead of its full bytes. For an API client making many small requests in a burst (exactly the shape a REST-backed UI produces), HPACK's savings compound with every additional request on the connection, because the per-request header overhead that used to be retransmitted in full keeps shrinking toward nearly nothing.

HTTP/2 also shipped server push (letting a server proactively send a response the client hasn't asked for yet, anticipating what it will need next), but push never justified its own complexity: most clients and browsers disable it, and the apps in this chapter's example don't use it either. Worth knowing it exists; not worth building around.

None of this touches the resource model. `GET /bookings/{id}` still returns a `200` with the same JSON body it always did; multiplexing and HPACK change how many bytes cross the wire and how many of them arrive in parallel, not what methods, status codes, or representations mean. What HTTP/2 does *not* fix is the layer underneath its own framing: **TCP head-of-line blocking**. TCP guarantees in-order delivery of every byte on a connection, which means if one packet is lost, every byte after it (regardless of which HTTP/2 stream it belongs to) sits in the kernel's receive buffer waiting for the lost packet to be retransmitted and arrive, even though the bytes for a completely unrelated stream might already be sitting there ready to hand to the application. HTTP/2 multiplexes streams at the application layer, but TCP still delivers them as one ordered byte stream underneath, so a single lost packet stalls every in-flight request on that connection, not just the one whose packet was lost. On a reliable wired connection this rarely matters; on a flaky mobile or satellite link, it's the exact problem HTTP/2 claimed to solve, reappearing one layer down.

## HTTP/3 over QUIC: streams that don't share a head-of-line

HTTP/3 keeps HTTP/2's idea (many concurrent streams over one logical connection) and replaces the transport underneath it. Instead of TCP, HTTP/3 runs over **QUIC**, a transport protocol built on **UDP** that implements its own reliability, ordering, and congestion control above the UDP datagram layer, where TCP's guarantees used to live. The reason this matters for head-of-line blocking is that QUIC tracks loss and retransmission **per stream**, not per connection: if a packet carrying stream A's data is lost, QUIC retransmits only what stream A needs, and stream B's already-arrived data is handed to the application immediately, with no need to wait for A's lost packet to catch up. The same multiplexing HTTP/2 does at the HTTP layer now holds all the way down to the transport, which is the one guarantee TCP structurally couldn't give it.

QUIC folds two other structural wins in alongside stream isolation. **Connection migration** addresses a problem TCP can't solve at all: a TCP connection is identified by a 4-tuple of source IP, source port, destination IP, and destination port, so the moment a client's IP address changes (a phone moving from WiFi to cellular, for instance), the old connection is dead and every stream on it has to restart from a fresh handshake. QUIC identifies a connection by a connection ID the two ends agree on independently of IP address and port, so the same QUIC connection (and everything in flight on it) survives the network change; the client just keeps sending from its new address and the server recognizes the connection ID. **0-RTT** resumption lets a client that has talked to a server before send its first request in the very first flight of packets, using cryptographic parameters cached from a prior session, rather than waiting for a full handshake round trip to complete first, collapsing the usual handshake-then-request sequence into one combined step when the client already has that cached state.

The cost of QUIC's architecture is that Transport Layer Security is not optional. HTTP/2 can run over plain cleartext TCP (h2c) when both sides agree to skip TLS, which is exactly how this chapter's example demonstrates it below. QUIC has no equivalent escape hatch: TLS 1.3 is integrated into the QUIC handshake itself, not layered on top of it as a separate negotiation, so there is no cleartext HTTP/3 the way there's cleartext HTTP/2. Every HTTP/3 deployment needs a real certificate and key, even for local testing with a throwaway self-signed one.

## Proving it: the same endpoint, three ways

The example for this chapter (`examples/19-http2-http3/`) is as thin as Chapter 18's by design: no Booking resource, no Postgres, just one `GET /` endpoint returning a tiny JSON body that echoes back the HTTP version the server itself saw negotiated on the connection. The point isn't what the endpoint returns; it's which wire protocol carried the same, unchanged response. `curl --http2-prior-knowledge -w '%{http_version}'` forces the request onto HTTP/2 cleartext ("h2c" via prior knowledge, meaning the client sends HTTP/2's connection preface immediately on a plain TCP socket, with no Upgrade handshake and no TLS/ALPN negotiation involved), and the `%{http_version}` format writes back exactly what curl saw negotiated, giving an assertion independent of the response body.

The two stacks get there differently, and the gap is the kind of thing a REST API built with "any ASGI server, any servlet container" assumptions can trip over without warning. Quarkus has HTTP/2 on by default in its Vert.x HTTP layer, including h2c via prior knowledge the moment a connection carries no TLS context, which describes this compose stack exactly, since it has no certificates configured. Python's story needs an explicit swap: uvicorn, the ASGI server every other Python example in this book uses, is HTTP/1.1-only on a cleartext bind (it has no h2c support at all), so this chapter's FastAPI app is served by **Hypercorn** instead, which negotiates HTTP/2 over a plain bind via prior knowledge as soon as the `h2` package is installed, with no change to the application code itself.

{% include codetabs.html langs="Quarkus|Python" %}

```java
@Path("/")
public class ProtocolResource {

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Map<String, Object> root(@Context HttpServerRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("service", "shipping-quarkus-ch19");
        body.put("httpVersion", request.version().name());
        return body;
    }
}
```

```python
@app.get("/")
def root(request: Request) -> dict[str, object]:
    # ASGI's `http_version` scope key reports what the server negotiated on
    # this connection ("1.1" or "2"), independent of curl's own
    # `%{http_version}` reporting.
    return {
        "service": "shipping-python-ch19",
        "httpVersion": request.scope.get("http_version"),
    }
```

Both handlers are ordinary REST resource methods: nothing about the code changes to go from serving HTTP/1.1 to also serving HTTP/2. What changes is configuration: Quarkus's `application.properties` sets `quarkus.http.http2=true` explicitly (redundant with the framework default, but it puts the chapter's point in config a reader can see rather than a default they'd have to already know about), and the Python side's `pyproject.toml` adds `hypercorn` and `h2` as dependencies, with the Containerfile's entrypoint launching `hypercorn app.main:app --bind 0.0.0.0:8000` in place of the usual `uvicorn` invocation. No application code moved; only the server process underneath it did.

`verify.sh` makes the negotiation itself the assertion, not just the status code, because that's the failure mode a REST API can have without anyone noticing from the response alone: a server that silently stops speaking HTTP/2 still answers every request with a perfectly good `200` over HTTP/1.1, and only a client that forces the protocol and checks what actually got negotiated will catch the regression. Running `./verify.sh` brings both services up, forces `--http1.1` against each and asserts `%{http_version}` reports `1.1`, then forces `--http2-prior-knowledge` against each and asserts `2`: four assertions, `PASS` only if every one holds. The example's README documents a drift probe that proves this isn't a pattern on paper: flip `quarkus.http.http2` to `false`, and the h2c prior-knowledge preface arrives at a server that can only answer HTTP/1.1 bytes, so curl (expecting a SETTINGS frame) errors out instead of ever reaching the `%{http_version}` comparison. The response body and status code were never going to tell that story; only forcing the protocol does.

## Why HTTP/3 stays out of CI

HTTP/3 is documented in this chapter's example but tier-gated out of `compose.yaml` and `verify.sh` by design: demonstrated locally, not verified on every run the way h1 and h2 are. The reason traces straight back to the mandatory-TLS point above: QUIC runs over UDP, has no cleartext mode at all, and needs real certificate material even for a throwaway local test. Wiring that into this book's CI would mean generating and provisioning TLS certificates for both stacks, publishing UDP ports through `docker compose` (far less battle-tested than TCP port publishing across CI runners), and depending on a curl build linked against an HTTP/3-capable TLS backend, which not every environment ships by default. That's a lot of moving, environment-sensitive parts for a chapter whose point (REST's contract is indifferent to the wire protocol underneath it) is already fully proven by the verified h1-versus-h2 contrast above.

Running it locally instead is a few extra commands. For Quarkus, generating a throwaway self-signed keystore with `keytool`, pointing `quarkus.http.ssl.certificate.key-store-file` at it, and setting `quarkus.http.http3=true` brings up an HTTP/3 listener a `curl -k --http3` (built against an HTTP/3-capable backend such as ngtcp2 or quiche) can reach. For Hypercorn, the same shape applies with `--quic-bind` alongside `--certfile`/`--keyfile`, since QUIC's TLS requirement is identical on both stacks. Both paths are documented step by step in the example's README rather than scripted into `verify.sh`, and that asymmetry is this chapter's actual state: HTTP/2 is proven on every CI run, against both stacks, by an automated assertion that fails loudly on regression; HTTP/3 is proven by hand, once, documented well enough to repeat, and revisited if this project's TLS story matures enough to make automating it worthwhile.

## Caching, proxies, and ALPN in brief

A detail that carries forward unchanged from earlier chapters: HTTP caching semantics (`Cache-Control`, `ETag`, conditional requests) live at the HTTP semantic layer this whole book has been building, not at the transport layer this chapter adds underneath it, so none of it changes crossing from HTTP/1.1 to HTTP/2 to HTTP/3. A CDN or reverse proxy in front of a REST API commonly terminates HTTP/2 or HTTP/3 from the client and proxies to the origin over whatever that origin supports, often plain HTTP/1.1: a pattern worth knowing about because it means the protocol a client negotiated and the protocol the origin server actually implements can legitimately differ, with the proxy bridging the gap. The way a browser picks HTTP/2 over HTTPS at all is **ALPN** (Application-Layer Protocol Negotiation), a TLS extension where client and server agree on `h2` or `http/1.1` during the TLS handshake itself, before a single HTTP byte crosses the wire: the TLS-backed counterpart to this chapter's example using cleartext h2c prior knowledge to reach the same HTTP/2 framing without a certificate in the picture.

## Proof

Quarkus comes up on port 8098, FastAPI (served by Hypercorn) on port 8018. The script brings both services up with `docker compose`, waits for health, then fires paired `--http1.1` and `--http2-prior-knowledge` requests at each stack's `GET /`, asserting `200` and the expected `%{http_version}` on all four. It prints `PASS` only once every assertion holds for both stacks: the verified half of this chapter's story, with HTTP/3 documented as the local-only half above.

{% include excalidraw.html file="19-http2-http3" alt="HTTP/1.1 serial head-of-line blocking across one request per connection at a time compared with HTTP/2 multiplexed streams over one TCP connection using HPACK header compression but still subject to TCP head-of-line blocking on packet loss, compared with HTTP/3 running independent QUIC streams over UDP with QPACK header compression, connection migration across network changes, and 0-RTT handshake resumption." caption="Figure 19.1: HTTP/1.1, HTTP/2, and HTTP/3 under a REST API." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to whether the HTTP version underneath a REST API is worth deliberate attention. It matters most when the interaction shape is many small requests over the same connection (a UI firing a resource list followed by a batch of detail fetches, a mobile client polling several endpoints in a burst) because that's exactly the shape HTTP/2's multiplexing and HPACK were built to help, and the shape HTTP/1.1's one-at-a-time connections and repeated headers punish hardest. Weigh client diversity next: HTTP/2 over TLS with ALPN is effectively universal across browsers, mobile clients, and modern HTTP libraries at this point, so enabling it on the server side is close to a free win with no client-side cost, unlike HTTP/3, which still depends on client and intermediary QUIC support that isn't guaranteed across every proxy, corporate firewall, or older HTTP client a diverse population might run. Reach for HTTP/3 specifically when the deployment's reality includes lossy networks (mobile clients on cellular links, geographically distant clients over long paths with real packet loss) where TCP head-of-line blocking is an active, measurable cost, or when clients roam across networks mid-session and connection migration avoids a full reconnect; both are QUIC's actual advantages over HTTP/2, not generic "newer is better" reasoning. Skip investing further than HTTP/2 when the deployment is internal, low-latency, and low-loss (most service-to-service traffic inside a data center) where TCP's head-of-line blocking rarely triggers in practice and the added TLS-and-UDP operational complexity of HTTP/3 buys little. None of this changes the REST contract itself: the decision is entirely about what the transport does to latency and throughput beneath resources, methods, and status codes that stay exactly the same either way.</p></div>

## Build, run, observe

```bash
cd examples/19-http2-http3 && ./verify.sh
```

`verify.sh` brings both services up with `docker compose`, then forces `--http1.1` and `--http2-prior-knowledge` requests at each stack's `GET /` and asserts curl's `%{http_version}` reports `1.1` and `2` respectively. Expect `PASS` once all four negotiations check out for both stacks; the full output from a real run is in `examples/19-http2-http3/README.md`.

## For deeper coverage

- [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): multiplexed streams and HPACK framing.
- [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114): HTTP semantics over QUIC.
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): the layer that stays unchanged across all three transports.
- *Cloud Native Design Patterns*, appendix-a-protocols (same series, protocol fundamentals appendix).
