---
title: "FastAPI in depth"
order: 23
part: "Multi-protocol contracts & framework deep-dives"
description: "Why async def handlers run on FastAPI's event loop while plain def handlers get offloaded to a threadpool, and how StreamingResponse and BackgroundTasks each depend on that same ASGI dispatch model."
duration: "26 min"
---

Chapter 22 opened Quarkus REST's box and found a build-time compiler deciding, once and for all, how a request maps onto a Java method. This chapter opens FastAPI's box and finds the opposite kind of decision, made at request time, every time: which execution context should run *this* handler — the single event loop every other in-flight request shares, or a worker thread borrowed from a bounded pool. That decision is invisible to a client exactly the way Quarkus's was: a `GET /thread/async` and a `GET /thread/sync` can return the identical JSON shape, the identical `200`, and still have executed in two different places inside the same process. This chapter grounds that distinction, and two others built on top of it (streamed responses and backgrounded work), in the real endpoints of `examples/23-fastapi-depth/`, a single-stack, FastAPI-only example that is this chapter's corollary to Chapter 22's Quarkus-only one.

## ASGI: one event loop, many in-flight requests

FastAPI is a thin layer over Starlette, and Starlette is built on ASGI — the Asynchronous Server Gateway Interface, Python's answer to WSGI for a world where a web application needs to do more than accept a request, compute a response, and return. WSGI's contract is synchronous and single-shot: an application is a callable that takes one request's environment and returns one response, and the server calling it blocks for the duration, so a WSGI deployment's only lever for serving more than one request at a time is more worker processes or threads. ASGI's contract is asynchronous: an application is a coroutine that receives messages (a request's start, its body chunks) and sends messages (a response's status, headers, body chunks) over time, so a single process can hold many requests in flight at once without a thread each — as long as none of them blocks the thread driving all of them.

That thread is the event loop, and in this chapter's example it's `uvicorn`'s, running as a single process with no `--workers` flag and no reload-forked subprocess — the simplest possible ASGI deployment, chosen so the thread story in the example's third mechanic has exactly one event-loop thread to point at. The event loop's job is to drive every coroutine that's currently waiting on something (a socket read, a timer, another coroutine's completion) by resuming whichever one just became unblocked and letting it run until it either finishes or hits its next `await`. A FastAPI route declared `async def` is exactly such a coroutine: when a request arrives for it, Starlette schedules it onto the loop, it runs synchronously-looking Python until it reaches an `await`, and at that point it yields control back to the loop so some *other* request's coroutine can make progress while this one's `await` is pending. Nothing about that model requires multiple threads to serve multiple concurrent requests; it requires every handler to cooperate by awaiting at its I/O boundaries instead of blocking the thread outright.

That contrast (one thread multiplexing many logical requests versus one thread or process per request) is also the cleanest line back to Chapter 22's Quarkus material. Quarkus's build-time compiler decides, ahead of any request, exactly which bytecode resolves a given endpoint's parameters; FastAPI's ASGI dispatch decides, for *every* request, which execution context should run the handler at all — "how is this binding resolved" versus "where does this code run," both invisible from the wire, which is exactly why a chapter like this one has to open the box rather than infer the mechanism from `curl` output. This chapter stays inside FastAPI's box from here: streaming a response incrementally over that one event loop, deferring work past a response without blocking it, and the async-versus-threadpool split deciding which of a handler's lines of code share the loop with every other request.

## StreamingResponse and the SSE line that proves it

`GET /bookings/{id}/events` in `python/app/main.py` streams five Server-Sent Events, one cargo-status transition at a time, through an async generator:

```python
async def _sse_event_stream(booking_id: str) -> AsyncIterator[str]:
    for i in range(SSE_EVENT_COUNT):
        await asyncio.sleep(SSE_INTERVAL_SECONDS)
        payload = event_for(booking_id, i)
        yield f"data: {json.dumps(payload)}\n\n"


@app.get("/bookings/{booking_id}/events")
async def booking_events(booking_id: str) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    return StreamingResponse(_sse_event_stream(booking_id), media_type="text/event-stream")
```

`StreamingResponse` is Starlette's answer to "this body isn't one value I have in hand, it's a sequence I produce over time" — it takes any async iterable and writes each item to the socket as it's yielded, rather than requiring the whole body materialized as a `bytes` or `str` up front the way a plain `JSONResponse` does. `_sse_event_stream` is an async generator, Python's native vocabulary for exactly that shape: `await asyncio.sleep(SSE_INTERVAL_SECONDS)` *before* each `yield` means the function suspends there, handing control back to the event loop, and only resumes (and only then produces the next line) once that sleep's timer fires. Each `yield` hands `StreamingResponse` one `data: {...}\n\n` frame, `text/event-stream`'s wire format for Server-Sent Events, and `StreamingResponse` writes that frame to the socket immediately rather than waiting to accumulate more.

The reason this matters is the same reason Chapter 22's NDJSON export needed its own `MessageBodyWriter`: a response correct byte-for-byte can still have been produced two structurally different ways, and only one of them streams. A handler that built the full list of five events in a loop, serialized the whole thing, and handed one complete string to `StreamingResponse` would pass a status-code check, a `Content-Type` check, and even a byte-for-byte body comparison against the real incremental version — every observable difference is in *when* each byte left the server, not *what* the bytes are. `verify.sh` makes that difference checkable, using the same technique Chapter 16 and Chapter 22 both rely on: it opens the stream with `curl -N` (no buffering on curl's own side) piped into a bash `read` loop that timestamps each line the instant it's received —

```bash
while IFS= read -r line; do
  printf '%s|%s\n' "$(date +%s.%N)" "$line"
done < <(curl -sS -N --max-time 8 "$base/bookings/$booking_id/events")
```

— and asserts the spread between the first and last `data:` line's timestamps is at least 0.6 seconds. At a 250ms interval between five frames, the ideal spread is 1.0 second (four gaps between five events); 0.6 seconds leaves room for CI jitter while staying far above the near-zero spread a buffered implementation would produce. The README notes why the more obvious measurement (curl's own `time_starttransfer`/`time_total` fields) doesn't distinguish the two cases: both a streamed and a buffered handler flush HTTP response headers immediately, well before the first event is even generated, so an aggregate timing field measures the same thing either way. Only reading line-by-line and stamping each arrival separates "this trickled in" from "this all showed up at once wearing a streaming `Content-Type`."

Each frame that arrives is schema-validated against `#/$defs/BookingEvent` from the shared contract as it's read, not after the whole stream closes — `bookingId`, a `status` and `previousStatus` drawn from the same `BookingStatus` enum every other chapter uses, and an `occurredAt` timestamp. Streaming a response doesn't relax the obligation that each unit of it be a schema-valid instance of whatever the contract promises; it just means that obligation gets checked once per frame instead of once per body.

## BackgroundTasks: a prompt response, a deferred and observable effect

`POST /bookings/{id}/notify` answers a different question: not "how do I send a long response incrementally" but "how do I accept a request, trigger slow work, and not make the caller wait for it." FastAPI's `BackgroundTasks` is the direct tool for that:

```python
async def _send_notification(booking_id: str, message: str) -> None:
    await asyncio.sleep(NOTIFY_DELAY_SECONDS)
    store.add_notification(booking_id, message, _now_utc())


@app.post("/bookings/{booking_id}/notify")
async def notify_booking(
    booking_id: str, payload: NotifyRequest, background_tasks: BackgroundTasks
) -> Response:
    missing = _booking_or_404(booking_id)
    if missing is not None:
        return missing

    background_tasks.add_task(_send_notification, booking_id, payload.message)
    return JSONResponse(
        status_code=202,
        content={"bookingId": booking_id, "status": "queued"},
    )
```

`background_tasks.add_task(...)` schedules `_send_notification` to run *after* the response has already been sent — Starlette holds the callable and its arguments, flushes the `202` to the client, and only then awaits the task on the same event loop. `_send_notification` is itself `async def` and only ever awaits (`asyncio.sleep` standing in for a real email, SMS, or webhook call), so running it later costs nothing extra in threads or processes; it's the same loop, just a later turn.

The observable promise a `202 Accepted` makes is specific ("I've accepted this and will do it, not that I've already done it"), and it's a promise a disguised-synchronous handler can fake at the status-code level while breaking at the timing level. `verify.sh` checks both halves of that promise rather than the status code alone: the `POST` itself must return in well under half a second, far faster than the 1.0-second `NOTIFY_DELAY_SECONDS` the background work takes, which rules out an implementation that secretly `await`s `_send_notification` before responding. Then it reads `GET /bookings/{id}/notifications` *immediately* after the `POST` and requires an **empty** list (not because the client didn't wait, but because the side effect hasn't happened yet) before polling the same endpoint on a bounded timeout until the notification shows up with the message that was posted. The README spells out why both assertions matter independently: an inline-`await`ed implementation would still return `202 {"status": "queued"}`, but it would blow the response-time budget *and* the follow-up `GET` would already show the notification instead of an empty list — two distinct, independently wrong fingerprints for the same bug, which is exactly the regression the chapter's drift probe walks through by reverting `add_task` to an inline `await` and watching `verify.sh` fail on both counts.

`BackgroundTasks` fits exactly this shape of work: fire-and-forget, in-process, no need to survive the process restarting, no retry policy beyond "it ran or it didn't." It stops being enough the moment any of those stop being true — a notification that must survive the server crashing mid-send, a job needing automatic retry with backoff, pending work that must be inspectable or rate-limited independently of request volume, or background work heavy enough to want its own worker pool. Those call for a real task queue outside the request/response cycle, the Python-ecosystem equivalent of what Chapter 22 named JobRunr for on the Quarkus side: Celery backed by Redis or RabbitMQ, or ARQ for a lighter asyncio-native queue. `BackgroundTasks` is the proportionate choice when "after the response, on this same process" is an acceptable answer to "when and where does this run"; a dedicated queue is the proportionate choice the moment it isn't.

## async def on the loop, plain def in the threadpool: the GIL's role

The example's third mechanic is the one this chapter has been building toward, and it's also the most commonly misunderstood thing about FastAPI: a route handler can be declared either `async def` or plain `def`, FastAPI accepts both for any endpoint, and the two are not interchangeable stylistic choices — they run in different places.

```python
def _thread_report(handler: str) -> dict:
    current = threading.current_thread()
    return {
        "handler": handler,
        "isMainThread": current is threading.main_thread(),
        "threadName": current.name,
    }


@app.get("/thread/async")
async def thread_async() -> dict:
    return _thread_report("async")


@app.get("/thread/sync")
def thread_sync() -> dict:
    return _thread_report("sync")
```

`/thread/async` is declared `async def`: Starlette awaits it directly on the event loop, the same loop handling every other in-flight `async def` request, so `threading.current_thread() is threading.main_thread()` reports `True` on every single call in this single-process, no-reload uvicorn deployment. `/thread/sync` is a plain `def`: Starlette detects that it isn't a coroutine function and, rather than calling it inline and blocking the loop for however long it takes to return, offloads it via `anyio.to_thread.run_sync` to a worker thread pulled from AnyIO's threadpool — so the identical check reports `False`, every time, on a thread whose name is never the main thread's. `verify.sh` calls both endpoints twice specifically to confirm this split is deterministic — a property of *which kind of function this is*, not an accident of request ordering or scheduler mood.

The reason Starlette bothers to make this distinction comes back to what the event loop is: a single thread, cooperatively multiplexing many logical requests by having each one yield at its `await` points. An `async def` handler that only awaits other coroutines (an async database driver, an `httpx.AsyncClient` call, `asyncio.sleep`) is a well-behaved citizen of that loop: whatever it's waiting on, something else can run meanwhile. A plain `def` handler has no `await` points at all, and if Starlette called it directly on the loop, any blocking call inside it (a synchronous database driver, `requests`, `time.sleep`, CPU-bound work) would freeze the *entire* event loop for its duration, stalling every other in-flight request on the process. Offloading plain `def` handlers to a threadpool sidesteps that: the handler gets to block freely, because it's blocking a thread set aside for exactly that, not the one thread every coroutine depends on.

This is where Python's Global Interpreter Lock earns its mention, because it shapes what that offloading buys. CPython's GIL ensures only one thread executes Python bytecode at a time, even across multiple OS threads, so handing a plain `def` handler to a threadpool worker doesn't let it run Python *in parallel* with the event loop thread; it lets it run Python *concurrently*, interleaved at the bytecode level, which is enough to keep the event loop unstuck as long as the offloaded work periodically releases the GIL. Blocking I/O calls do exactly that: a synchronous socket read, a file read, most C-extension database drivers release the GIL while waiting on the kernel or the network, which is precisely the window the event loop needs to keep servicing other requests. CPU-bound Python code is the case where this stops helping — a tight pure-Python loop never releases the GIL voluntarily, so running it on a threadpool thread still contends for the same single lock every other thread needs, and true parallelism for that kind of work requires sidestepping the GIL entirely, via multiple processes or a C extension that drops it explicitly. Python's ongoing free-threaded build effort (PEP 703, an opt-in no-GIL build since CPython 3.13) targets exactly that gap: a GIL-free interpreter would let CPU-bound Python run in parallel across threads, a different problem than the one `anyio.to_thread.run_sync` solves today — blocking I/O still benefits from being off the event loop's one thread regardless, but a no-GIL interpreter would change the calculus for the CPU-bound case offloading alone can't fix.

None of this is specific to this example's two toy endpoints; it's the rule FastAPI's own documentation states and every real handler has to be written against: use `async def` with `await` for anything awaitable I/O (an async ORM, `httpx`, an async Kafka client) so it shares the event loop cooperatively, and reach for plain `def` for anything built on a blocking library with no async equivalent, so Starlette's threadpool isolates its blocking from everyone else's request. Writing `async def` around a call to a synchronous, blocking library is the failure mode this split exists to prevent: the function *looks* async, FastAPI happily schedules it on the loop, and the first blocking call inside it freezes every other in-flight request for as long as that call takes — a mistake with no visible symptom until the service is under enough concurrent load for the stall to matter.

{% include excalidraw.html file="23-fastapi-in-depth" alt="A single uvicorn process with one event loop on the main thread serving an async StreamingResponse that drips SSE frames over time, a BackgroundTasks call returning a 202 while its deferred work finishes later on the same loop, and a plain-def handler offloaded through AnyIO to a threadpool worker thread distinct from the main thread." caption="Figure 23.1 — One event loop, one threadpool: where StreamingResponse, BackgroundTasks, and plain def handlers each actually run inside a single FastAPI process." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to choosing async def versus plain def per endpoint, rather than picking one style for an entire service. The deciding question is almost always "what does this handler block on": if every I/O call inside it has a real async driver (asyncpg over psycopg2, httpx over requests, an async Kafka client), async def is close to free and keeps the handler cooperating with the event loop the way StreamingResponse and BackgroundTasks both depend on. The moment a handler's only dependency is a blocking library with no async equivalent (a synchronous ORM, a legacy SDK, a CPU-bound computation measured in tens of milliseconds or more), plain def is the better fit, because declaring async def around a blocking call doesn't make the call non-blocking, it just hides a stalled event loop behind a signature that looks safe. Reach past FastAPI's own model once the blocking work is CPU-bound and large enough that a threadpool's cooperative concurrency isn't the fix: true parallel computation needs multiple processes or a C extension that drops the GIL explicitly, not a borrowed thread. Skip worrying about the split for a low-traffic internal service where no slow handler ever competes with enough concurrent requests for a stall to be noticeable — the distinction matters in proportion to how many requests share that one event loop when a handler blocks it.</p></div>
