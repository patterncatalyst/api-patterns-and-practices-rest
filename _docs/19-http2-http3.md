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
- Force protocol negotiation with `curl --http2-prior-knowledge`/`%{http_version}` instead of trusting a `200` response alone.
- Decide when HTTP/3 is worth its mandatory-TLS and UDP operational cost.

## Why this matters

A `GET /bookings/{id}` that returns `200` with a JSON body is equally correct over HTTP/1.1, HTTP/2 or HTTP/3. The resource, method and representation don't change. What changes is how many exchanges share a connection, how many header bytes repeat, and what one lost packet does to everything in flight. That's the transport layer, not the contract.

The demo is one `GET /` returning a JSON body that echoes the HTTP version the server saw negotiated, carried three ways. It has no Booking resource and no database.

{% include excalidraw.html file="19-http2-http3" alt="HTTP/1.1 serial head-of-line blocking across one request per connection at a time compared with HTTP/2 multiplexed streams over one TCP connection using HPACK header compression but still subject to TCP head-of-line blocking on packet loss, compared with HTTP/3 running independent QUIC streams over UDP with QPACK header compression, connection migration across network changes, and 0-RTT handshake resumption." caption="Figure 19.1: HTTP/1.1, HTTP/2, and HTTP/3 under a REST API." %}

## HTTP/1.1: one request at a time per connection

HTTP/1.1 allows one request in flight per TCP connection. The client waits for the full response before sending the next. Pipelining is in the spec, but no production client uses it, because one slow response jams the queue behind it. Browsers open several parallel connections instead, commonly six per origin.

Each extra connection pays its own TCP handshake, its own TLS handshake on `https://`, and its own slow-start ramp. A UI that fetches a resource list and then a dozen details queues a dozen requests behind six sockets, and each socket pays setup the others already paid. The contract is untouched, but this sets a latency floor under every response that has nothing to do with server speed.

## HTTP/2: multiplexed streams, one connection, HPACK

HTTP/2 changes the framing under HTTP, not REST's model. Requests and responses split into binary frames (HEADERS, DATA, SETTINGS and others), each tagged with a stream id and interleaved over one TCP connection. A resource list and a dozen detail fetches share one socket, none waiting for the others, with no repeated handshakes.

Headers repeat heavily: `User-Agent`, cookies, `Accept`, authorization tokens. HTTP/1.1 resends them in full on every request. **HPACK** keeps a stateful compression table shared by client and server for the life of the connection, so a header sent once costs a small reference afterward. A burst of small requests, the shape a REST-backed UI produces, saves more with each request.

HTTP/2 also defined server push, where the server sends a response the client hasn't asked for. Most clients disable it and the demo doesn't use it.

HTTP/2 doesn't fix **TCP head-of-line blocking**. TCP delivers one ordered byte stream, so one lost packet holds back every later byte on the connection, including bytes for unrelated HTTP/2 streams that already arrived. A single loss stalls every in-flight request. On a reliable wired link this rarely matters. On a lossy mobile or satellite link it's the problem HTTP/2 set out to solve, one layer down.

## HTTP/3 over QUIC

HTTP/3 keeps many streams over one logical connection and replaces the transport. **QUIC** runs over **UDP** and implements its own reliability, ordering and congestion control. It tracks loss per stream: when a packet carrying stream A is lost, only stream A waits for the retransmission, and stream B's data goes to the application immediately.

QUIC adds two more properties:

- **Connection migration.** A TCP connection is identified by source IP, source port, destination IP and destination port, so a phone moving from WiFi to cellular kills it and every stream restarts from a fresh handshake. QUIC identifies a connection by an id the two ends agree on, so the connection and everything in flight survive the change of address.
- **0-RTT.** A client that has talked to the server before sends its first request in the first flight, using cached cryptographic parameters, instead of finishing a handshake round trip first.

TLS isn't optional. HTTP/2 can run over cleartext TCP (h2c) when both sides skip TLS. QUIC integrates TLS 1.3 into its handshake, so there is no cleartext HTTP/3, and every deployment needs a certificate and key, even a throwaway self-signed one for local testing.

## Force and check the negotiated version

`curl --http2-prior-knowledge` sends the HTTP/2 connection preface at once on a plain TCP socket, with no Upgrade handshake and no TLS or ALPN. `-w '%{http_version}'` prints the version curl saw negotiated, an assertion independent of the body. This matters because a server that silently stops speaking HTTP/2 still answers every request with a good `200` over HTTP/1.1. Only a client that forces the protocol and reads the negotiated version catches the regression.

The two stacks get HTTP/2 differently:

| Stack | HTTP/2 over a cleartext bind | Configuration |
|---|---|---|
| Quarkus | On by default in the Vert.x HTTP layer, including h2c by prior knowledge when the connection has no TLS | `quarkus.http.http2=true`, redundant with the default but visible |
| FastAPI | Not available under uvicorn, which is HTTP/1.1-only on a cleartext bind | Serve with Hypercorn and install `h2`; launch `hypercorn app.main:app --bind 0.0.0.0:8000` |

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
    # `%{http_version}` reporting: handy for confirming from the response
    # body itself, not just the client's view.
    return {
        "service": "shipping-python-ch19",
        "httpVersion": request.scope.get("http_version"),
    }
```

Both handlers are ordinary resource methods. Going from HTTP/1.1 to HTTP/2 changes the server process and its configuration, not the application code.

## HTTP/3 is a manual run

HTTP/3 is documented but kept out of the compose file and the verify script. QUIC needs certificate material, UDP port publishing through `docker compose` (less proven than TCP across CI runners), and a curl built against an HTTP/3-capable TLS backend, which not every environment ships. That's a lot of environment-sensitive setup, and the h1-versus-h2 contrast already shows that REST's contract doesn't depend on the wire protocol.

To run it locally on Quarkus, generate a throwaway self-signed keystore with `keytool`, point `quarkus.http.ssl.certificate.key-store-file` at it, and set `quarkus.http.http3=true`. Reach it with `curl -k --http3` from a build using a backend such as ngtcp2 or quiche. Hypercorn takes `--quic-bind` alongside `--certfile` and `--keyfile`. The README lists both paths step by step.

## Caching, proxies and ALPN

Caching semantics (`Cache-Control`, `ETag`, conditional requests) live at the HTTP semantic layer, so they're identical across all three versions. A CDN or reverse proxy commonly terminates HTTP/2 or HTTP/3 from the client and talks to the origin over HTTP/1.1, so the version a client negotiated and the version the origin implements can legitimately differ.

Browsers pick HTTP/2 over HTTPS with **ALPN** (Application-Layer Protocol Negotiation), a TLS extension where client and server agree on `h2` or `http/1.1` during the handshake, before any HTTP byte crosses the wire. Cleartext prior knowledge reaches the same framing without a certificate.

## When the HTTP version is worth attention

| Situation | Guidance |
|---|---|
| Many small requests on one connection: a UI fetching a list then details, a mobile client polling several endpoints | Enable HTTP/2. Multiplexing and HPACK target this shape. |
| Diverse clients | HTTP/2 with ALPN is effectively universal, so enabling it costs little. HTTP/3 depends on client and intermediary QUIC support that isn't guaranteed. |
| Lossy networks (cellular, long distance) or clients roaming between networks | HTTP/3. Per-stream loss recovery and connection migration are QUIC's real advantages. |
| Internal, low-latency, low-loss service-to-service traffic | Stop at HTTP/2. TCP head-of-line blocking rarely triggers and HTTP/3 adds TLS and UDP operations for little gain. |

> **🤖 Explore with your agent**
>
> "In examples/19-http2-http3, add a `GET /version` endpoint to both the Quarkus `ProtocolResource` and the FastAPI app that returns only `httpVersion`, then write a script that calls `/` and `/version` on ports 8098 and 8018 with `--http1.1` and `--http2-prior-knowledge` and fails unless `%{http_version}` is `1.1` and `2` respectively."
>
> Check: run the script, then set `quarkus.http.http2=false` and confirm the Quarkus prior-knowledge call fails instead of printing `1.1`.

## Build, run, observe

```bash
cd examples/19-http2-http3 && ./verify.sh
```

The script starts both stacks with `docker compose` (Quarkus on port 8098, FastAPI served by Hypercorn on port 8018), waits for health, then calls `GET /` on each stack with `--http1.1` and `--http2-prior-knowledge` and checks `200` and the expected `%{http_version}` of `1.1` and `2`. It prints `PASS` when all four negotiations hold. Full output is in `examples/19-http2-http3/README.md`.

Experiments:

- Set `quarkus.http.http2=false`. The prior-knowledge preface reaches a server that only answers HTTP/1.1 bytes, so curl errors out before it prints a version.
- Swap Hypercorn back to uvicorn on the FastAPI side. The `--http2-prior-knowledge` check fails, because uvicorn has no h2c support.

## For deeper coverage

- [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): multiplexed streams and HPACK framing.
- [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114): HTTP semantics over QUIC.
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): the layer that stays unchanged across all three transports.
- *Cloud Native Design Patterns*, appendix-a-protocols (same series, protocol fundamentals appendix).
