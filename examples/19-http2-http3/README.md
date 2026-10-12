# Ch19 — REST over HTTP/2 & HTTP/3

REST is a style defined at the HTTP *semantics* layer — methods, status
codes, representations, hypermedia. It says nothing about which wire
protocol version carries those semantics. This chapter proves that with the
smallest possible example: the same `GET /` endpoint, serving the same tiny
JSON body, over **HTTP/1.1** and **HTTP/2** — no application code change
required, purely a server/transport-layer concern.

This is a deliberately thin app, like Ch18: no Booking/Cargo resource
model, no Postgres. The point of this chapter is WHICH wire protocol
carried the response, not what it returns.

## Run it

```bash
cd examples/19-http2-http3
./verify.sh
```

This brings both services up with `docker compose`, waits for health, and
for **each** stack:

- forces HTTP/1.1 (`curl --http1.1`) and asserts `%{http_version}` reports
  `1.1` with a `200`;
- forces HTTP/2 cleartext, "h2c" (`curl --http2-prior-knowledge`) and
  asserts `%{http_version}` reports `2` with a `200`.

Prints `PASS` only if all four assertions hold.

To poke at it by hand instead:

```bash
docker compose up --build

# HTTP/1.1, explicit:
curl -s --http1.1 -o /dev/null -w '%{http_version}\n' http://localhost:8098/   # Quarkus
curl -s --http1.1 -o /dev/null -w '%{http_version}\n' http://localhost:8018/   # FastAPI

# HTTP/2 cleartext (h2c), prior knowledge — no TLS, no ALPN:
curl -s --http2-prior-knowledge -o /dev/null -w '%{http_version}\n' http://localhost:8098/
curl -s --http2-prior-knowledge -o /dev/null -w '%{http_version}\n' http://localhost:8018/

# The response body itself also reports what the server saw negotiated:
curl -s --http2-prior-knowledge http://localhost:8098/ | jq .
curl -s --http2-prior-knowledge http://localhost:8018/ | jq .

docker compose down -v
```

Ports are **unique** across the repo's examples: Quarkus on `8098`→8080,
FastAPI on `8018`→8000.

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## HTTP/1.1 vs. HTTP/2: what actually changes on the wire

| | HTTP/1.1 | HTTP/2 |
|---|---|---|
| **Framing** | Text-based request/status lines + headers, body delimited by `Content-Length`/chunking. | Binary framing layer — requests/responses are split into length-prefixed frames (HEADERS, DATA, SETTINGS, ...). |
| **Multiplexing** | One request in flight per TCP connection at a time (HTTP/1.1 pipelining exists on paper but is unused in practice); browsers/clients open multiple parallel connections to compensate. | Many concurrent request/response "streams" interleaved over a SINGLE TCP connection — no connection-per-request workaround needed, and no head-of-line blocking at the HTTP layer (TCP-level HOL blocking on a lost packet still applies; that's what HTTP/3 fixes — see below). |
| **Header compression** | None — repeated headers (`User-Agent`, cookies, `Accept`, ...) are sent in full on every request. | HPACK — a shared, stateful compression table across the connection means repeated header fields cost almost nothing after the first request. |
| **Server push** | N/A | Technically part of the spec, but disabled by both this chapter's app and most clients/browsers in practice — not exercised here. |
| **Negotiation** | Default for any plain HTTP request. | Either ALPN during a TLS handshake (what browsers do against `https://`), or cleartext "h2c" — see below. |

Practically: a REST API that serves a UI making many small requests (a
resource list followed by N detail fetches, for example) benefits
measurably from HTTP/2's multiplexing and header compression — fewer
sockets, less redundant header bytes — without changing a single resource,
method, or status code. The REST contract (`contracts/openapi/shipping-api.yaml`
elsewhere in this repo) is unaffected either way.

## HTTP/2 cleartext (h2c): how each stack serves it

This compose stack has **no TLS configured** (no certs), so the usual
browser path to HTTP/2 — ALPN negotiated during a TLS handshake — isn't
available here. The alternative is cleartext HTTP/2, "h2c", via **prior
knowledge**: the client simply sends the HTTP/2 connection preface
immediately on a plain TCP connection, with no Upgrade handshake or TLS
involved. `curl --http2-prior-knowledge` does exactly this.

- **Quarkus**: HTTP/2 is ON by default in the Vert.x HTTP layer, and h2c via
  prior knowledge works out of the box against a cleartext listener.
  `quarkus/src/main/resources/application.properties` sets
  `quarkus.http.http2=true` explicitly (redundant with the default, but
  makes the chapter's point visible in config rather than relying on a
  default the reader can't see).

- **FastAPI / Python**: **uvicorn — the ASGI server every other Python
  example in this repo uses — does not speak HTTP/2 cleartext.** It's
  HTTP/1.1-only on a plain TCP bind. This chapter swaps in
  [**Hypercorn**](https://hypercorn.readthedocs.io/) instead, an ASGI
  server that negotiates HTTP/2 over a cleartext bind via prior knowledge as
  soon as the `h2` package is installed — no extra flag needed. See
  `python/pyproject.toml` (adds `hypercorn` + `h2`) and
  `python/Containerfile`'s `ENTRYPOINT`:

  ```dockerfile
  ENTRYPOINT ["hypercorn", "app.main:app", "--bind", "0.0.0.0:8000"]
  ```

  No application code changed to go from HTTP/1.1-only to
  HTTP/1.1-and-HTTP/2 — `app/main.py` is identical in shape to a
  uvicorn-served app. This was verified by hand before wiring it into the
  container: a local Hypercorn instance answered both `curl --http1.1` (got
  `1.1`) and `curl --http2-prior-knowledge` (got `2`) against the same
  plain `--bind 0.0.0.0:PORT` with zero extra Hypercorn flags.

## HTTP/3 / QUIC — LOCAL ONLY, not in CI

**HTTP/3 is deliberately tier-gated out of this chapter's `compose.yaml` and
`verify.sh`.** HTTP/3 runs over QUIC, which is built on **UDP**, not TCP,
and — unlike HTTP/2's h2c escape hatch — **HTTP/3 has no cleartext mode**:
QUIC's transport-layer security (TLS 1.3) is mandatory and baked into the
protocol itself, not optional like HTTP/2's TLS+ALPN path. That means
exercising HTTP/3 here would require:

- a real (self-signed is fine, but still real) TLS certificate + key for
  both stacks;
- UDP port publishing in `compose.yaml` (`docker compose` and most CI
  runners are far less battle-tested with UDP port mapping than TCP);
- client-side QUIC support in whatever's firing the request (curl needs to
  be built against an HTTP/3-capable TLS backend; the one in `curl` images
  commonly available doesn't always have it).

That's a lot of moving, environment-sensitive parts for a chapter whose
point is "REST doesn't care which wire protocol carries it" — the point is
already proven by the h1/h2 contrast above. Rather than ship something
environment-fragile into CI, HTTP/3 is documented here as a **local-only**
exercise:

**Quarkus + HTTP/3 (local, with a self-signed cert):**

```bash
# Generate a throwaway self-signed cert + key (dev only):
keytool -genkeypair -alias h3demo -keyalg RSA -keysize 2048 -validity 1 \
  -dname "CN=localhost" -keystore keystore.p12 -storetype PKCS12 \
  -storepass changeit

# In application.properties (or as -D system properties), enable TLS + HTTP/3:
# quarkus.http.ssl.certificate.key-store-file=keystore.p12
# quarkus.http.ssl.certificate.key-store-password=changeit
# quarkus.http.insecure-requests=disabled
# quarkus.http.http3=true

# curl needs an HTTP/3-capable build (e.g. curl built against ngtcp2/quiche,
# or nghttp3 — not every distro's default curl has this):
curl -k --http3 https://localhost:8443/
```

**FastAPI + HTTP/3 (local):** Hypercorn supports QUIC via `--quic-bind` plus
`--certfile`/`--keyfile` (TLS is mandatory for QUIC, same as Quarkus above):

```bash
hypercorn app.main:app --bind 0.0.0.0:8443 --quic-bind 0.0.0.0:8443 \
  --certfile cert.pem --keyfile key.pem

curl -k --http3 https://localhost:8443/
```

Why this stays out of `verify.sh`: UDP + mandatory TLS + a cert-generation
step is exactly the kind of environment-sensitive setup that turns a
30-second CI gate into a flaky one. The h1/h2 negotiation this chapter
already proves — same endpoint, same body, different wire protocol,
verified by `%{http_version}` — makes the pedagogical point HTTP/3 would
only repeat with extra moving parts. Revisit this tier-gate once the
contract-spine work picks up TLS story for the whole repo (not planned as
of this chapter).

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | `/` | Returns `{"service": "...", "httpVersion": "..."}` — the body itself echoes what the server saw negotiated on the connection (Quarkus via Vert.x's `HttpServerRequest.version()`, FastAPI via ASGI's `request.scope["http_version"]`). The endpoint `verify.sh` exercises over both HTTP/1.1 and HTTP/2. |
| GET | `/health` (Python) / `/q/health` (Quarkus) | Liveness, used by `docker compose` healthchecks. |

## The drift probe

The whole point of this chapter is that `verify.sh` fails when a server
silently stops speaking HTTP/2 — not just when it returns the wrong status
code. A broken h2 negotiation still serves perfectly good HTTP/1.1
responses; only forcing the protocol and checking `%{http_version}` reveals
the regression. To see it happen:

**Quarkus — flip `quarkus.http.http2` to `false`.**

In `quarkus/src/main/resources/application.properties`, change:

```properties
quarkus.http.http2=true
```

to:

```properties
quarkus.http.http2=false
```

Re-run `./verify.sh`:

```
lib.sh: ok — quarkus --http1.1 GET /: HTTP 200
lib.sh: ok — quarkus --http1.1 negotiated HTTP/1.1
curl: (16) Remote peer returned unexpected data while we expected SETTINGS frame.  Perhaps, peer does not support HTTP/2 properly.
```

With HTTP/2 disabled, the server falls back to answering the h2c
prior-knowledge preface as plain HTTP/1.1 bytes — curl, expecting an HTTP/2
SETTINGS frame, can't parse them and exits non-zero (`curl: (16)`) instead
of ever getting as far as `%{http_version}`. `verify.sh` (running under
`set -euo pipefail`) exits non-zero at that point, the `EXIT` trap tears the
stack down cleanly, and the run is a clear `FAIL` either way — whether curl
itself errors out or (on a server that degrades more gracefully) returns
`1.1` where `2` was expected.

Revert the property and re-run `./verify.sh` — it goes back to `PASS` for
both stacks. That round trip (break h2 negotiation, watch the gate catch it
by forcing the protocol rather than trusting a plain 200, fix it, watch the
gate go green again) is the thing worth internalizing: protocol support is
a property you have to force and measure, not something a default request
can tell you anything about.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/19-http2-http3.{svg,excalidraw}`) show the protocol
negotiation paths covered in this chapter: HTTP/1.1 (always available),
HTTP/2 cleartext via prior knowledge (what `verify.sh` exercises on both
stacks), and HTTP/3/QUIC (local-only, tier-gated out of CI).
