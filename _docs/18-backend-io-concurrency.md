---
title: "Back-end I/O concurrency"
order: 18
part: "Performance & transport"
description: "Serve many concurrent requests that each wait on I/O without exhausting threads: Quarkus blocking worker pools versus reactive and virtual threads, and Python's async event loop versus a thread pool under the GIL."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Explain the thread-per-request ceiling and why CPU utilization can stay near zero while requests queue.
- Compare Quarkus's blocking worker pool, `Uni`/`Multi` reactive dispatch, and `@RunOnVirtualThread` for I/O-bound work.
- Compare Python's `async def`/`await` event loop against an explicit `ThreadPoolExecutor`/`run_in_executor` offload.
- Explain why the GIL doesn't constrain I/O-bound concurrency but does constrain CPU-bound work.
- Measure concurrency with a wall-clock batch test rather than a single request's status code.

## Why this matters

A booking confirmation calls a payment service. A manifest export reads from Postgres. A routing lookup calls a carrier's rate API. Each request spends most of its time waiting, and what the server thread does during that wait decides how many requests can be in flight before the server stops accepting new ones.

Strip everything else away: no `Booking`, no contract, no Postgres. `GET /io/slow?ms=200` simulates a slow downstream call with a delay and returns a small JSON body naming the thread that handled it. Each stack implements it twice, once idiomatically and once naively, so the contrast under load is the only thing to see.

{% include excalidraw.html file="18-concurrency-model" alt="Quarkus blocking worker pool exhausting under many concurrent slow calls next to Quarkus reactive Uni and virtual threads serving the same load on a small fixed pool, alongside Python's async event loop interleaving many coroutines on one thread versus a bounded threadpool queuing once its workers are all asleep, all labeled to show the same requests-waiting-on-I/O workload served without thread exhaustion versus with it." caption="Figure 18.1: Blocking pools versus non-blocking/virtual threads and the async event loop." %}

## The thread-per-request ceiling

A conventional server keeps a fixed pool of threads. A request takes a thread, and the thread stays assigned until the response goes out. If the handler calls something slow, such as `Thread.sleep()`, a synchronous JDBC query or a blocking HTTP client, the thread parks for the whole call and holds a pool slot no other request can use.

The ceiling has nothing to do with CPU. A server in this state can show near-zero CPU while it queues or rejects requests, because every thread is asleep on I/O. A 20-thread pool serving requests that each block 200 ms sustains at most 20 in flight, however idle the cores are. Request 21 waits for one of the first 20 to finish.

## Quarkus: worker pool, event loop, virtual threads

Quarkus REST picks where to run a resource method from its return type. A plain object means blocking, so the method runs on the Vert.x worker pool, a bounded pool set aside so blocking work doesn't stall the event loop:

```java
@GET
@Path("/slow-blocking")
@Produces(MediaType.APPLICATION_JSON)
public SlowResponse slowBlocking(@RestQuery("ms") @DefaultValue("200") long ms) throws InterruptedException {
    Thread.sleep(ms);
    return new SlowResponse(ms, Thread.currentThread().getName());
}
```

Every call holds one worker for the full `ms`. Enough concurrent callers fill the pool, and the next request queues.

A method returning Mutiny's `Uni` or `Multi` declares a non-blocking contract in its type, so Quarkus runs it on the event-loop threads, a small pool (one per core by default) that must never block. The idiomatic endpoint, `slow`, returns a `Uni<SlowResponse>` whose completion a Vert.x timer schedules; it appears next to its FastAPI twin below.

`onItem().delayIt().by(...)` registers a timer and returns. No thread sleeps for the 200 ms. The completion resumes as a callback, possibly on a different event-loop thread, so a handful of threads serve far more concurrent callers than their count.

Virtual threads are the third option. Annotate a resource method `@RunOnVirtualThread` and write it like `slowBlocking`, sequential with `Thread.sleep()`. The JVM parks the virtual thread and frees the OS carrier thread to run others. The code reads as blocking and scales as if it weren't.

| | `Uni`/`Multi` | `@RunOnVirtualThread` |
|---|---|---|
| Code style | Callback composition: `onItem()`, `chain()` | Sequential statements |
| Existing blocking code | Rewrite | Near-zero rewrite |
| Non-blocking visible in the signature | Yes | No |
| Use it for | New code | Porting a blocking service incrementally |

The setting that bounds how many `slowBlocking`-shaped calls run at once is `quarkus.thread-pool.max-threads`, the blocking executor Quarkus REST uses. `quarkus.vertx.worker-pool-size` sounds right but governs raw Vert.x worker verticles that resource methods rarely touch. Cap `quarkus.thread-pool.max-threads` at `1` and 20 concurrent blocking calls take about the 4-second serial floor instead of under a second.

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/slow")
@Produces(MediaType.APPLICATION_JSON)
public Uni<SlowResponse> slow(@RestQuery("ms") @DefaultValue("200") long ms) {
    return Uni.createFrom()
            .item(() -> new SlowResponse(ms, Thread.currentThread().getName()))
            .onItem().delayIt().by(Duration.ofMillis(ms));
}
```

```python
@app.get("/io/slow")
async def slow(ms: int = 200) -> dict[str, object]:
    await asyncio.sleep(ms / 1000)
    return {"sleptMs": ms, "worker": f"event-loop:{threading.current_thread().name}"}
```

## FastAPI: event loop versus a bounded thread pool

`async def` with `await` runs a coroutine on a single-threaded event loop. `await` is where the coroutine gives the loop back so another can run. `asyncio.sleep` doesn't block the thread: it suspends the coroutine and schedules a wake-up. Twenty concurrent callers cost twenty scheduled wake-ups, not twenty threads. It is the same trick as Quarkus event-loop dispatch, with suspension as a keyword instead of a reactive type.

The naive contrast is a truly blocking call. `time.sleep()` called directly inside an `async def` freezes the entire event loop, and with it every other in-flight request. That's worse than the Quarkus worker pool, because there is normally one event loop. The blocking endpoint offloads to a dedicated executor:

```python
_BLOCKING_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="io-slow-blocking")

def _blocking_sleep(ms: int) -> dict[str, object]:
    time.sleep(ms / 1000)
    return {"sleptMs": ms, "worker": threading.current_thread().name}

@app.get("/io/slow-blocking")
async def slow_blocking(ms: int = 200) -> dict[str, object]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_BLOCKING_POOL, _blocking_sleep, ms)
```

The pool has two workers so exhaustion shows at twenty concurrent requests. The framework's own threadpool defaults to about forty workers, enough to hide the effect at this load. The behavior matches the Quarkus worker pool: a bounded number of threads, each held for the full sleep, with the rest queueing. Shrink the pool to one worker and the batch serializes just as the Quarkus blocking endpoint does with its pool capped at one.

## The GIL and I/O-bound work

The Global Interpreter Lock lets one thread execute Python bytecode at a time. That doesn't limit this workload, because it is I/O-bound. `asyncio.sleep` involves no thread at all. `time.sleep` in the worker pool releases the GIL while it waits, as any blocking syscall does, since no bytecode runs during the wait.

The GIL does constrain CPU-bound work across threads: JSON-encoding a large body, hashing, image resizing. Four CPU-bound threads take about as long as one, because only one executes at a time. Real parallelism there needs multiprocessing, a native extension that releases the GIL, or the free-threaded build available from Python 3.13. I/O-bound concurrency never needed any of them.

## Measure concurrency by wall clock

A single `200` response proves nothing about concurrency, because a serialized implementation returns the same correct body, later. Fire 20 concurrent requests at the non-blocking endpoint and compare the batch time with the serial floor: 20 x 200 ms = 4.0 s. A concurrent implementation finishes well under 2 s, close to the cost of one call. Point the same check at the blocking endpoint with its pool capped to one worker and the batch converges on 4 s, with every response still a clean `200`.

## Database and file I/O behind the same handler

The choice applies to every slow dependency, not only a sleep.

| Dependency | Blocks | Fix |
|---|---|---|
| Blocking JDBC call in a plain-return Quarkus method | One worker per query | Reactive Postgres client returning `Uni<Row>`, or `@RunOnVirtualThread` |
| Blocking `InputStream` read of a large manifest | One worker per read | Non-blocking file API, or virtual threads |
| Synchronous driver such as `psycopg2` inside `async def` | The single event-loop thread, so every in-flight request | Async driver such as `asyncpg`, or `run_in_executor` |

An executor offload competes for a bounded thread pool, where a truly async driver doesn't. Whatever is slow and synchronous under an async-looking handler brings the ceiling back until a concurrent load test finds it.

## When to change the concurrency model

| Situation | Choice |
|---|---|
| Many concurrent clients each waiting on a slow database, API or service | Event loop, reactive types or virtual threads |
| Existing blocking code | Virtual threads, or an async driver swap on the Python side |
| New code where non-blocking should show in the type | `Uni`/`Multi` or `async def` |
| CPU-bound work | Multiprocessing, native code or more cores, not a different I/O model |
| Load far below the pool ceiling, such as five callers and fifty workers | Keep the blocking code |

> **🤖 Explore with your agent**
>
> "In examples/18-concurrency, add a `GET /io/slow-virtual?ms=200` endpoint to the Quarkus service using `@RunOnVirtualThread` with the same sequential body as `slowBlocking`, and report which thread name each of `/io/slow`, `/io/slow-blocking` and `/io/slow-virtual` returns for one call. Then explain which of the three a blocking JDBC call should use and why."
>
> Check: fire 20 concurrent requests at `/io/slow-virtual?ms=200` on port 8097. The batch should finish well under 2 seconds, like `/io/slow`, not near the 4-second serial floor.

## Build, run, observe

```bash
cd examples/18-concurrency && ./verify.sh
```

The script starts both stacks with `docker compose` (Quarkus on port 8097, FastAPI on port 8017), waits for health, fires 20 concurrent requests at each stack's `/io/slow?ms=200`, and requires every response to be `200` and the batch to finish under 2 seconds. It prints `PASS` when both stacks clear the bound. Full output is in `examples/18-concurrency/README.md`.

Experiments:

- Cap each stack's blocking pool to one worker and point the same check at `/io/slow-blocking`. The batch lands near 4 seconds and the check fails, while every response is still `200`.

## For deeper coverage

- Benjamin J. Evans & Jonathan Gough, *Optimizing Cloud Native Java* (O'Reilly, 2024): virtual threads and JVM concurrency.
- Kirill Bobrov, *Grokking Concurrency* (Manning, 2024): event loops, thread pools, and concurrency fundamentals.
- Pekka Enberg, *Latency: Reduce delay in software systems* (Manning, 2025): the cost of blocking I/O.
- *Cloud Native Design Patterns*, communications (same series, back-end call patterns under load).
