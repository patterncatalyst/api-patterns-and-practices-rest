"""Ch18 back-end I/O concurrency anchor — FastAPI side.

Two implementations of "call a slow downstream dependency and return its
result," to show the very different concurrency behavior each produces:

- `/io/slow`          — the idiomatic answer: `async def` + `await
                         asyncio.sleep(...)`. The event loop is free to run
                         other requests' code while this one is suspended on
                         the await, so N concurrent callers are served
                         concurrently off ONE thread.
- `/io/slow-blocking` — the naive answer, kept only as a contrast. A
                         genuinely blocking `time.sleep()` call cannot run on
                         the event loop thread (it would freeze every other
                         in-flight request for its duration), so it is
                         pushed onto a deliberately tiny worker pool here —
                         see `_BLOCKING_POOL` below. Once every worker in
                         that pool is asleep, additional callers queue
                         behind them instead of running concurrently.

GIL note: none of this is about Python's Global Interpreter Lock. Both
endpoints below are I/O-bound (a timer / a sleep), not CPU-bound, so only
one OS thread's worth of *compute* ever needs to run at a time regardless of
how many requests are in flight. The GIL only becomes the bottleneck for
CPU-bound work (e.g. JSON-encoding a huge body, hashing, compression) run on
multiple threads — that kind of work does NOT parallelize across threads in
CPython the way it would in Quarkus/the JVM, and would need
multiprocessing, a native extension that releases the GIL, or (on 3.13+)
the free-threaded build to actually use more than one core. I/O-bound
concurrency, which is what this chapter is about, was never limited by the
GIL in the first place — `asyncio.sleep` and blocking I/O syscalls both
release it while waiting.
"""
from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI

app = FastAPI(title="shipping-python-ch18")

# A deliberately tiny, dedicated pool for the blocking contrast endpoint
# only — NOT FastAPI/Starlette's own default threadpool (which defaults to
# 40 workers and would mask the exhaustion this endpoint exists to
# demonstrate at the K=20 concurrency this chapter's verify.sh uses). See
# README.md for how to shrink this further (down to 1) and watch the
# endpoint fully serialize.
_BLOCKING_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="io-slow-blocking")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "up"}


@app.get("/io/slow")
async def slow(ms: int = 200) -> dict[str, object]:
    await asyncio.sleep(ms / 1000)
    return {"sleptMs": ms, "worker": f"event-loop:{threading.current_thread().name}"}


def _blocking_sleep(ms: int) -> dict[str, object]:
    time.sleep(ms / 1000)
    return {"sleptMs": ms, "worker": threading.current_thread().name}


@app.get("/io/slow-blocking")
async def slow_blocking(ms: int = 200) -> dict[str, object]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_BLOCKING_POOL, _blocking_sleep, ms)
