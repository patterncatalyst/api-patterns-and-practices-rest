# Ch18 — Back-end I/O concurrency

A back-end that calls a slow downstream dependency (another service, a
database, a third-party API) has exactly one job while it waits: not waste
resources. This chapter builds the smallest possible example of that —
`GET /io/slow?ms=200`, which simulates a slow I/O call with a delay and
returns a tiny JSON body — implemented two different ways on each stack, to
show the very different concurrency behavior each produces under load.

This is a deliberately thin app: no Booking/Cargo resource model, no
Postgres. The point of this chapter is HOW a handler waits, not what it
returns.

## Run it

```bash
cd examples/18-concurrency
./verify.sh
```

This brings both services up with `docker compose`, waits for health, fires
**20 concurrent requests** at each stack's `/io/slow?ms=200`, and asserts:

- all 20 responses are `200`;
- the whole batch completes in **under 2 seconds** — far below the ~4 second
  floor 20 requests would take if handled one at a time (20 × 200ms).

Prints `PASS` only if both assertions hold for **both** stacks.

To poke at it by hand instead:

```bash
docker compose up --build

# One call, ~200ms:
time curl -s "localhost:8097/io/slow?ms=200" | jq .     # Quarkus
time curl -s "localhost:8017/io/slow?ms=200" | jq .     # FastAPI

# 20 concurrent calls to the CONCURRENT endpoint — finishes in ~200-400ms:
time (for i in $(seq 1 20); do curl -s "localhost:8097/io/slow?ms=200" >/dev/null & done; wait)

# 20 concurrent calls to the BLOCKING contrast endpoint — the Python side
# pins this to a 2-worker pool (see app/main.py), so this takes ~2s
# (10 batches of 2 x 200ms) instead of ~200-400ms:
time (for i in $(seq 1 20); do curl -s "localhost:8017/io/slow-blocking?ms=200" >/dev/null & done; wait)

docker compose down -v
```

Ports are **unique** across the repo's examples: Quarkus on `8097`→8080,
FastAPI on `8017`→8000.

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## Blocking vs. non-blocking vs. virtual threads

A thread-per-request server has a fixed-size pool of threads available to
handle requests. If handling a request means blocking that thread for the
duration of a slow downstream call (`Thread.sleep`, a synchronous JDBC
query, a blocking HTTP client), then the number of requests the server can
serve *concurrently* is capped at the pool size — not by CPU, not by the
actual downstream latency, but by how many threads happen to be parked
waiting. Once every thread in the pool is asleep, the next request queues
behind them, even though the CPU is doing nothing but idling.

Three ways out:

| Approach | How it avoids thread exhaustion | Used here |
|---|---|---|
| **Non-blocking / reactive** | The handler never blocks a thread at all. It registers a callback (a timer, an I/O completion event) and returns the thread to a small, shared pool immediately; the callback resumes the response later, often on a different thread. | `IoResource.slow` (Quarkus, Mutiny `Uni`) |
| **`async`/`await` (event loop)** | Same idea, language-native: `await` suspends the coroutine and returns control to the event loop, which runs other coroutines' code in the meantime, all on ONE thread. | `app.main.slow` (FastAPI, `async def` + `await asyncio.sleep`) |
| **Virtual threads** | The *code* still looks blocking (`Thread.sleep`, sequential), but the JVM parks the cheap virtual thread and frees the expensive OS "carrier" thread underneath it to run other virtual threads. Not used in this example (see below), but worth knowing as a third option on the JVM — annotate a resource method `@RunOnVirtualThread` and write ordinary blocking-looking code. | *(not used; see note)* |

This chapter picked **Mutiny `Uni`** for Quarkus over virtual threads so the
non-blocking behavior is visible in the code itself: `onItem().delayIt()`
is explicitly a timer registration, not a disguised blocking call. Virtual
threads solve the same thread-exhaustion problem with less code change (no
reactive types, no callback chains), but the code reads identically to the
blocking version — the concurrency property is a JVM/runtime guarantee you
have to know to look for, not something visible in the method signature.
Either is a legitimate idiomatic answer; pick virtual threads when porting
an existing blocking codebase incrementally, pick reactive types when you
want the non-blocking contract to show up in the type signature.

`IoResource.slowBlocking` is kept as a deliberate contrast: a plain
(non-`Uni`) resource method doing `Thread.sleep()`. Quarkus REST
automatically dispatches it to the Vert.x WORKER thread pool (not the event
loop) because its return type isn't reactive — one worker thread tied up
per in-flight call, for the full sleep duration.

## The GIL note (Python)

None of this chapter is about Python's Global Interpreter Lock. Both
`/io/slow` and `/io/slow-blocking` are **I/O-bound** — a timer, a sleep —
not CPU-bound, so only one OS thread's worth of actual compute ever needs
to run at a time regardless of how many requests are in flight.
`asyncio.sleep` suspends the coroutine without touching a thread at all;
`time.sleep` (used by `/io/slow-blocking`, off the event loop in a
dedicated pool) releases the GIL for its duration, same as any blocking
syscall.

The GIL only becomes the bottleneck for **CPU-bound** work — JSON-encoding
a huge body, hashing, image processing — run across multiple threads. That
kind of work does not parallelize across cores in CPython the way it would
in Quarkus/the JVM; it would need multiprocessing, a native extension that
releases the GIL during its C code, or (3.13+) the free-threaded build to
actually use more than one core. I/O-bound concurrency — the subject of
this chapter — was never limited by the GIL: both `asyncio.sleep` and
blocking I/O syscalls release it while waiting, which is exactly why
`async def` + `await` scales to many concurrent slow I/O calls on a single
thread.

## Endpoints

| Method | Path | Stack behavior |
|---|---|---|
| GET | `/io/slow?ms=200` | Non-blocking delay; returns `{"sleptMs":200,"worker":"..."}`. The endpoint `verify.sh` measures. |
| GET | `/io/slow-blocking?ms=200` | Deliberately blocking contrast endpoint, same response shape. Not exercised by `verify.sh`'s pass/fail assertions — see the drift probe below for how to point the same assertion at it. |
| GET | `/health` (Python) / `/q/health` (Quarkus) | Liveness, used by `docker compose` healthchecks. |

## The drift probe

The whole point of this chapter is that `verify.sh` actually fails when an
endpoint silently stops being concurrent — not just when it returns the
wrong status code. Every individual response from a serialized
implementation is still a perfectly valid `200`; only the BATCH wall-clock
time reveals the regression. To see it happen:

**Quarkus — cap the blocking-dispatch worker pool to 1 and point the test at the blocking endpoint.**

In `quarkus/src/main/resources/application.properties`, add:

```properties
quarkus.thread-pool.max-threads=1
```

(`quarkus.vertx.worker-pool-size` governs raw Vert.x worker verticles, not
the executor Quarkus REST dispatches plain-return-type resource methods to
— `quarkus.thread-pool.max-threads` is the one that actually bounds
`slowBlocking`'s concurrency.) Then in `verify.sh`, temporarily pass
`/io/slow-blocking` as the third argument to `run_concurrency_test` for the
Quarkus call instead of leaving it defaulted to `/io/slow`. Re-run
`./verify.sh`:

```
lib.sh: quarkus batch of 20 requests completed in 4.169s (serial floor would be 4.0s)
lib.sh: FAIL — quarkus: 20 concurrent requests took 4.169s — expected under 2.0s.
This looks SERIALIZED (one request handled at a time), not concurrent.
```

With the worker pool capped to 1, every one of the 20 calls to the blocking
endpoint queues behind the one before it — wall-clock time converges on the
4-second serial floor the non-blocking endpoint stays nowhere near.

**Python — shrink `_BLOCKING_POOL` to 1 worker and point the test at `/io/slow-blocking`.**

In `python/app/main.py`, change:

```python
_BLOCKING_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="io-slow-blocking")
```

to:

```python
_BLOCKING_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="io-slow-blocking")
```

and temporarily pass `/io/slow-blocking` as the third argument to the
Python `run_concurrency_test` call in `verify.sh` instead of leaving it
defaulted to `/io/slow`. Re-run `./verify.sh`:

```
lib.sh: python batch of 20 requests completed in 4.017s (serial floor would be 4.0s)
lib.sh: FAIL — python: 20 concurrent requests took 4.017s — expected under 2.0s.
This looks SERIALIZED (one request handled at a time), not concurrent.
```

Revert both edits and re-run `./verify.sh` — it goes back to `PASS` for
both stacks. That round trip (break it, watch the gate catch it by
wall-clock time rather than status code, fix it, watch the gate go green
again) is the thing worth internalizing: concurrency is a property you have
to measure under load, not something a single request's `200` can tell you
anything about.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/18-concurrency-model.{svg,excalidraw}`) show the
concurrency model: a fixed, small pool of event-loop/worker threads serving
many concurrent in-flight requests through non-blocking I/O, contrasted
with a thread-per-request model that runs out of threads under the same
load.
