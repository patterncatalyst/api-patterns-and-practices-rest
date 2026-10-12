"""Ch0 boot skeleton — FastAPI side.

Proves the toolchain (uv + FastAPI on UBI 10) builds, starts, and answers a
request. The real shipping/cargo resource model (bookings, cargo, routes)
arrives contract-first in Ch4.
"""

from fastapi import FastAPI

app = FastAPI(title="shipping-python")


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "shipping-python", "status": "up"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "up"}
