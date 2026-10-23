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

Every chapter so far has asked what a response looks like on the wire: the status code, the headers, the framing. This one asks what happens behind the handler while the wire is quiet. A booking confirmation calls a payment service. A manifest export reads from Postgres. A routing lookup calls a carrier's rate API. Every one of those is a request that spends most of its time doing nothing but waiting on something else to finish, and the question this chapter answers is what a server thread does during that wait, because the answer determines how many of those requests can be in flight at once before the server stops accepting new ones.

The example for this chapter (`examples/18-concurrency/`) strips away everything but that question. There's no `Booking` resource, no contract, no Postgres: just `GET /io/slow?ms=200`, which simulates a slow downstream call with a 200ms delay and returns a tiny JSON body naming the thread that handled it. Each stack implements that endpoint two ways: once idiomatically, once naively, so the contrast in behavior under load is visible without anything else in the example competing for attention.

## The thread-per-request ceiling

A conventional web server keeps a fixed-size pool of threads ready to handle requests (a worker pool, a servlet container's thread pool, whatever the framework calls it). A request comes in, a thread picks it up, and that thread stays assigned to the request until a response goes out. If handling the request means calling something slow (a `Thread.sleep()`, a synchronous JDBC query, a blocking HTTP client waiting on a downstream reply), the thread sits parked for the full duration of that call, doing nothing, holding a slot in the pool that no other request can use.

The ceiling this creates has nothing to do with CPU. A machine running this kind of server under load can show near-zero CPU utilization while still rejecting or queueing new requests, because every thread in the pool is asleep waiting on I/O rather than computing anything. The pool size, not the hardware, is the bottleneck: a 20-thread pool serving requests that each block for 200ms on a downstream call can sustain at most 20 requests in flight simultaneously, no matter how fast the machine is or how idle its cores are. Request 21 queues behind the first 20 to finish, even though nothing is actually busy.

Three different techniques get past this ceiling, and the two stacks in this chapter's example reach for a different one of the first two by default.

## Quarkus: blocking, reactive, and virtual threads

Quarkus REST decides where to run a resource method based on its return type. A method returning a plain object (`SlowResponse`, a `String`, whatever) is assumed to block, so Quarkus dispatches it to the Vert.x **worker thread pool**, a separate, bounded pool set aside exactly for blocking work so it doesn't stall the event loop. That's the naive path in this example, `slowBlocking`:

```java
@GET
@Path("/slow-blocking")
@Produces(MediaType.APPLICATION_JSON)
public SlowResponse slowBlocking(@QueryParam("ms") @DefaultValue("200") long ms) throws InterruptedException {
    Thread.sleep(ms);
    return new SlowResponse(ms, Thread.currentThread().getName());
}
```

Simple, readable, and exactly the shape a thread-per-request mental model expects. But every call ties up one worker thread for the full `ms` milliseconds. Enough concurrent slow callers and the worker pool fills, and the next request queues behind it, the ceiling from the previous section made concrete.

A method returning Mutiny's `Uni` or `Multi` tells Quarkus the opposite: this method's non-blocking contract is in its type signature, so dispatch it to the **event-loop** threads instead: a small, fixed pool (by default one per CPU core) built to never block. This chapter's idiomatic endpoint, `slow`, returns a `Uni<SlowResponse>` whose completion is scheduled by a Vert.x timer rather than produced by a blocked thread:

```java
@GET
@Path("/slow")
@Produces(MediaType.APPLICATION_JSON)
public Uni<SlowResponse> slow(@QueryParam("ms") @DefaultValue("200") long ms) {
    return Uni.createFrom()
            .item(() -> new SlowResponse(ms, Thread.currentThread().getName()))
            .onItem().delayIt().by(Duration.ofMillis(ms));
}
```

`onItem().delayIt().by(...)` registers a timer and returns immediately; no thread blocks for the 200ms, it's parked as a callback the Vert.x reactor fires later, possibly resuming on a different event-loop thread than the one that received the request. That's why the handful of event-loop threads can serve far more than a handful of concurrent callers: nothing is ever asleep waiting for the clock, only waiting to be told the clock ran out.

A third option exists on the JVM and deserves a place in this picture even though the example doesn't use it: **virtual threads**. Annotate a resource method `@RunOnVirtualThread` and write it exactly like `slowBlocking` above (`Thread.sleep()`, sequential, nothing reactive), and the JVM parks the lightweight virtual thread instead of the expensive OS carrier thread underneath it, freeing that carrier to run other virtual threads while this one waits. The code reads as blocking; the runtime makes it scale like it isn't. That's a materially different trade-off from the reactive `Uni` above: virtual threads let an existing blocking codebase absorb a huge concurrency improvement with essentially no rewrite, while `Uni`/`Multi` force every non-blocking step through a different, more awkward vocabulary: `onItem()`, `.chain()`, callback composition instead of sequential statements. This chapter picked `Uni` for the idiomatic endpoint specifically because the non-blocking contract then shows up in the method's *type*, not just in a runtime guarantee a reader has to already know to look for. Porting an existing blocking service incrementally is the case for reaching for virtual threads instead; building new code where the non-blocking property should be visible in the signature is the case for reactive types. Neither is wrong; they solve the same thread-exhaustion problem from different directions.

The knob that governs which pool `slowBlocking` competes for is easy to misname. `quarkus.vertx.worker-pool-size` sounds like the right setting but governs raw Vert.x worker verticles, a lower-level primitive most resource methods never touch directly. The setting that actually bounds how many concurrent `slowBlocking`-shaped calls Quarkus REST can run at once is `quarkus.thread-pool.max-threads`: the blocking executor Quarkus REST dispatches plain-return-type resource methods to. Capping it to `1` and re-running the load test turns the blocking endpoint's 20 concurrent calls into something that completes in roughly the 4-second serial floor instead of the sub-second concurrent time, because every call now queues behind the one before it on a pool of exactly one thread.

{% include codetabs.html langs="Quarkus|Python" %}

```java
@GET
@Path("/slow")
@Produces(MediaType.APPLICATION_JSON)
public Uni<SlowResponse> slow(@QueryParam("ms") @DefaultValue("200") long ms) {
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

## FastAPI: the event loop versus a bounded thread pool

Python's answer to the same problem predates Quarkus's reactive types by design intent, if not by syntax: `async def` plus `await` runs a coroutine on a single-threaded **event loop**, and `await` is the point where a coroutine voluntarily gives the loop back so it can run some other coroutine's code while this one waits. `asyncio.sleep(ms / 1000)` is the async equivalent of Mutiny's timer; it doesn't block the thread, it suspends the coroutine and schedules a wake-up, letting the one event-loop thread interleave work across every in-flight request:

```python
@app.get("/io/slow")
async def slow(ms: int = 200) -> dict[str, object]:
    await asyncio.sleep(ms / 1000)
    return {"sleptMs": ms, "worker": f"event-loop:{threading.current_thread().name}"}
```

Twenty concurrent callers of this endpoint cost the event loop twenty scheduled wake-ups, not twenty threads: the same structural trick as Quarkus's event-loop dispatch, expressed in a language where suspension is a keyword instead of a method call on a reactive type.

The naive contrast is a truly blocking call: `time.sleep()` freezes whatever thread calls it, and calling it directly inside an `async def` would freeze the *entire event loop* (every other in-flight request) for the sleep's duration, which is worse than the Quarkus worker-pool case because there's normally only one event loop thread to begin with. FastAPI's example sidesteps that by explicitly offloading the blocking call to a dedicated executor:

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

`_BLOCKING_POOL` is capped at two workers by design: small enough that the exhaustion this endpoint is meant to demonstrate actually shows up at the twenty-concurrent-request scale this chapter's test uses. (FastAPI/Starlette's own default threadpool defaults to around forty workers, comfortably large enough to mask the exhaustion effect at this load, which is exactly why the example wires up its own smaller pool instead of relying on the framework default.) The behavior is the same shape as Quarkus's worker-pool path: a bounded number of threads, each tied up for the full sleep duration per call, and the (K − pool size) extra callers queueing behind them. Shrink `_BLOCKING_POOL` to one worker and the twenty-request batch serializes almost exactly like the Quarkus blocking endpoint does with its thread pool capped to one: both techniques converge on the identical failure mode because the failure mode is the same idea (a small fixed pool of threads, each occupied for the full wait) wearing a different language's syntax.

## The GIL, and why it doesn't matter here

Python's Global Interpreter Lock gets blamed for concurrency problems it doesn't cause in this chapter. The GIL means only one thread executes Python bytecode at any instant, which sounds like it should prevent exactly the kind of concurrent handling this example demonstrates. But it doesn't, because both endpoints here are **I/O-bound**, not CPU-bound. `asyncio.sleep` doesn't touch a thread at all; it's a pure scheduling operation inside the event loop. `time.sleep`, called from the blocking contrast endpoint's worker pool, releases the GIL for its duration exactly the way any blocking syscall does: waiting on a timer, a socket read, or a disk operation all involve the same release-the-GIL-while-the-OS-does-something pattern, because there's no Python bytecode to execute during the wait regardless of which thread is "holding" anything.

The GIL becomes the real constraint for **CPU-bound** work spread across multiple threads: JSON-encoding a large body, hashing, image resizing, any workload where the bottleneck is actual Python bytecode execution rather than waiting on something external. That kind of work doesn't parallelize across threads in CPython the way it would across Quarkus's event-loop or worker threads on the JVM, because the GIL serializes bytecode execution regardless of thread count: running four CPU-bound threads takes roughly the same wall time as running one, since only one of them is ever executing at a time. Getting real parallelism for that kind of work needs multiprocessing (separate interpreter processes, each with its own GIL), a native extension that releases the GIL during its C code, or, from Python 3.13 onward, the experimental free-threaded build that removes the GIL entirely. None of that is this chapter's problem. I/O-bound concurrency (a service waiting on a database, a downstream HTTP call, a file read) was never limited by the GIL, which is precisely why `async def` plus `await` scales to many concurrent slow I/O calls on a single thread without any of those heavier techniques.

## The measured contrast

Every claim above is testable only by measuring wall-clock time across a batch of concurrent calls: a single request's `200` response proves nothing about concurrency, because a serialized implementation returns the exact same correct body, just later. `verify.sh` fires **20 concurrent requests** at each stack's non-blocking `/io/slow?ms=200` endpoint and checks the whole batch against two numbers: the serial floor twenty 200ms calls would take if handled one at a time (20 × 200ms = 4.0s), and the actual elapsed time for the batch, which the test requires to land well under 2 seconds (close to the roughly 0.3-second time one call alone would take, since twenty concurrent non-blocking calls cost barely more wall time than one). Point that same assertion at `/io/slow-blocking` with either stack's small pool capped down to a single worker and the batch converges on the 4-second serial floor instead, because every call now queues fully behind the one before it. That round trip (correct behavior passing, a regressed pool size failing by wall-clock time alone, both status codes still a clean `200` throughout) is the concrete evidence that a concurrency property is not something a status code can certify.

## DB and file I/O behind the same handler

The same choice applies to every slow dependency a real handler calls, not just a simulated sleep. A Postgres query issued through a blocking JDBC driver from inside a plain-return-type Quarkus resource method behaves exactly like `slowBlocking`: one worker thread tied up for the query's duration, the worker pool filling under load regardless of how fast the database itself responds. The fix is the same pattern this chapter already demonstrated, applied to a real dependency instead of a timer: a reactive database client (Quarkus's reactive Postgres client returning `Uni<Row>`) keeps the query non-blocking end to end, or `@RunOnVirtualThread` lets the same blocking JDBC code scale without a rewrite. File I/O follows the identical logic: reading a large manifest off disk with a blocking `InputStream` read ties up a thread for the read's duration exactly like `Thread.sleep()` does; a non-blocking file API or virtual threads avoid it the same two ways.

FastAPI's side mirrors this directly. An endpoint that calls `psycopg2` (a synchronous driver) from inside an `async def` blocks the single event-loop thread for the query's duration: the single-event-loop version of the freeze `time.sleep` would cause, affecting every other in-flight request, not just this one. The fix is either an async-native driver (`asyncpg`, used elsewhere in this project's reactive database access, or `aiosqlite` for SQLite) so the query itself is an `await`-able operation that suspends the coroutine without blocking the loop, or (if a synchronous driver is unavoidable) offloading the call to `run_in_executor` the same way `/io/slow-blocking` does here, accepting that the offloaded work now competes for a bounded thread pool instead of the no-limit-but-CPU cost of a truly non-blocking driver. Neither stack has a shortcut around this: whatever is slow and synchronous underneath an async-looking handler reintroduces the exact ceiling this chapter opened with, invisibly, until someone runs a concurrent load test against it.

## Proof

Quarkus comes up on port 8097, FastAPI on port 8017. The script brings both services up with `docker compose`, waits for health, then fires 20 concurrent requests at each stack's `/io/slow?ms=200` and asserts every response is `200` and the whole batch completes in under 2 seconds: far below the 4-second floor the same 20 requests would need if handled strictly one at a time. It prints `PASS` only once both assertions hold for both stacks. The README documents a drift probe that caps each stack's blocking pool to a single worker by design and points the same assertion at `/io/slow-blocking` instead, watching `verify.sh` fail by wall-clock time with every individual response still a correct `200`: the regression this chapter exists to make visible.

{% include excalidraw.html file="18-concurrency-model" alt="Quarkus blocking worker pool exhausting under many concurrent slow calls next to Quarkus reactive Uni and virtual threads serving the same load on a small fixed pool, alongside Python's async event loop interleaving many coroutines on one thread versus a bounded threadpool queuing once its workers are all asleep, all labeled to show the same requests-waiting-on-I/O workload served without thread exhaustion versus with it." caption="Figure 18.1: Blocking pools versus non-blocking/virtual threads and the async event loop." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to decide whether a reactive, virtual-thread, or async model shift pays off. Reach for it when the <strong>interaction shape</strong> is many concurrent clients each waiting on a slow downstream dependency (a database, a third-party API, another service) where the slow part is I/O, not computation: that's exactly the shape a thread-per-request pool handles worst and an event loop or virtual threads handle best. Weigh it against <strong>team familiarity</strong> and the codebase's current shape: a service already written as straightforward blocking code gets the biggest win from virtual threads (near-zero rewrite, same mental model) or from an async-native driver swap on the Python side, while a greenfield service where the non-blocking contract should be visible in the type signature is the case for Mutiny's `Uni`/`Multi` or FastAPI's `async def`. Skip the model shift entirely for purely CPU-bound work (hashing, encoding, heavy computation) where no amount of non-blocking I/O helps and the real fix is multiprocessing, native code, or more cores, not a different concurrency primitive. And don't reach for it where the load never approaches the pool ceiling in the first place: a low-traffic internal tool with five callers and a worker pool of fifty has no exhaustion problem to solve, and the extra complexity of reactive types or async-only libraries buys nothing a straightforward blocking implementation wasn't already providing.</p></div>

## Build, run, observe

```bash
cd examples/18-concurrency && ./verify.sh
```

`verify.sh` brings both services up with `docker compose`, fires 20 concurrent requests at each stack's non-blocking `/io/slow?ms=200` endpoint, and asserts every response is `200` and the whole batch completes well under the 4-second serial floor. Expect `PASS` once both stacks clear that bound; the full output from a real run is in `examples/18-concurrency/README.md`.

## For deeper coverage

- Benjamin J. Evans & Jonathan Gough, *Optimizing Cloud Native Java* (O'Reilly, 2024): virtual threads and JVM concurrency.
- Kirill Bobrov, *Grokking Concurrency* (Manning, 2024): event loops, thread pools, and concurrency fundamentals.
- Pekka Enberg, *Latency: Reduce delay in software systems* (Manning, 2025): the cost of blocking I/O.
- *Cloud Native Design Patterns*, communications (same series, back-end call patterns under load).
