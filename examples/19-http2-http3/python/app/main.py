"""Ch19 REST over HTTP/2 & HTTP/3 anchor — FastAPI side.

A deliberately thin app (no Booking/Cargo model — see README for why): one
endpoint, `GET /`, returning a small JSON body. The point of this chapter is
WHICH wire protocol carried that response, not what it returns.

ASGI servers and HTTP/2: uvicorn — the ASGI server used by every other
Python example in this repo — does not speak HTTP/2 cleartext (h2c); it is
HTTP/1.1-only on a plain TCP bind. This app is served by Hypercorn instead
(see Containerfile's ENTRYPOINT), which negotiates HTTP/2 over a cleartext
bind via "prior knowledge" (the client sends the HTTP/2 connection preface
immediately, no TLS/ALPN or Upgrade handshake involved) as soon as the `h2`
package is installed. No application code change is needed to go from
HTTP/1.1-only to HTTP/1.1-and-HTTP/2 here — it's entirely a server/transport
layer concern, which is itself the thing worth noticing: REST is defined at
the HTTP semantics layer (methods, status codes, representations), and is
indifferent to which wire protocol version carries it.
"""
from __future__ import annotations

from fastapi import Request, FastAPI

app = FastAPI(title="shipping-python-ch19")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "up"}


@app.get("/")
def root(request: Request) -> dict[str, object]:
    # ASGI's `http_version` scope key reports what the server negotiated on
    # this connection ("1.1" or "2"), independent of curl's own
    # `%{http_version}` reporting — handy for confirming from the response
    # body itself, not just the client's view.
    return {
        "service": "shipping-python-ch19",
        "httpVersion": request.scope.get("http_version"),
    }
