---
title: "FastAPI in depth"
order: 23
part: "Multi-protocol contracts & framework deep-dives"
description: "async def handlers run on FastAPI's event loop and plain def handlers run in a threadpool, and StreamingResponse and BackgroundTasks both depend on that dispatch model."
duration: "26 min"
---

## Learning objectives

By the end of this chapter you can:

- Explain how ASGI's single event loop lets `async def` handlers serve many in-flight requests without a thread each.
- Stream a response incrementally with `StreamingResponse` over an async generator.
- Use `BackgroundTasks.add_task` to return a prompt `202 Accepted` and defer slow work until after the response is sent.
- Choose `async def` or plain `def` per route, and explain why Starlette runs plain `def` handlers through `anyio.to_thread.run_sync`.
- Reason about the GIL's effect on CPU-bound and I/O-bound work when choosing between the event loop and the threadpool.

## Why this matters

FastAPI decides at request time, every time, where a handler runs: on the single event loop every other in-flight request shares, or on a worker thread borrowed from a bounded pool. A client can't see the decision. `GET /thread/async` and `GET /thread/sync` can return the same JSON and the same `200` while running in different places in one process. Streaming and background work depend on the same decision.

{% include excalidraw.html file="23-fastapi-in-depth" alt="A single uvicorn process with one event loop on the main thread serving an async StreamingResponse that drips SSE frames over time, a BackgroundTasks call returning a 202 while its deferred work finishes later on the same loop, and a plain def handler offloaded through AnyIO to a threadpool worker thread distinct from the main thread." caption="Figure 23.1: One event loop, one threadpool: where StreamingResponse, BackgroundTasks and plain def handlers run inside a single FastAPI process." %}

## ASGI: one event loop, many requests

FastAPI is a layer over Starlette, which is built on ASGI. WSGI is synchronous and single-shot: a callable takes one request and returns one response, and the server blocks meanwhile, so concurrency means more threads or processes. ASGI applications are coroutines that receive and send messages over time, so one process holds many requests in flight as long as none blocks the thread that drives them all.

That thread is the event loop. It resumes whichever coroutine just became unblocked and runs it until it finishes or reaches its next `await`. An `async def` route is such a coroutine: at an `await` it yields, and another request's coroutine runs. Concurrency needs cooperation, not threads. Run `uvicorn` as one process with no `--workers` and no reload, and there is exactly one loop thread.

## Streaming a response

A response that is a sequence produced over time, such as five cargo-status events a quarter second apart, can be built wrongly in a way no status, header or body check detects. A handler that collects all five events, serializes them and hands one string to the response has the right bytes; only when each byte left the server differs.

FastAPI's `StreamingResponse` takes any async iterable and writes each item to the socket as it's yielded, instead of requiring the whole body up front the way `JSONResponse` does. An async generator that awaits before each `yield` suspends and returns control to the loop until its timer fires:

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

Each frame is a Server-Sent Events record, `data: {...}` followed by a blank line, and validates against `#/$defs/BookingEvent` as it arrives. The Quarkus counterpart is a `Multi<String>`. Streaming doesn't relax the schema obligation; it moves the check from once per body to once per frame.

Telling the two apart means measuring arrival time per line. `curl -N` (no client buffering) feeds a loop that timestamps each line:

```bash
while IFS= read -r line; do
  printf '%s|%s\n' "$(date +%s.%N)" "$line" >> "$timed_file"
done < <(curl -sS -N --max-time 8 "$BASE/bookings/$booking_id/events")
```

At a 250 ms interval, five frames spread about 1.0 second from first to last; a buffered body spreads near zero. Curl's own `time_starttransfer` and `time_total` can't tell the cases apart, because a streamed and a buffered handler both flush headers immediately, before the first event exists.

## Deferring work past the response

A request triggers slow work, such as a notification, and the caller shouldn't wait for it. A `202 Accepted` promises "accepted and will do", not "already done". A handler that awaits the work inline and then answers `202 {"status": "queued"}` fakes that promise: the status code is right and the caller waited anyway.

`BackgroundTasks.add_task` holds the callable and its arguments. Starlette flushes the `202`, then awaits the task on the same event loop:

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

The task is `async def` and only awaits (`asyncio.sleep` stands in for an email, SMS or webhook call), so running it later costs no extra thread. The promise has two observable halves: the `POST` returns well under the 1.0-second task delay, and a `GET /bookings/{id}/notifications` immediately afterward returns an empty list that fills in later. An inline await breaks both.

`BackgroundTasks` fits fire-and-forget work in the same process that can be lost on a restart and needs no retry policy. When any of that stops being true, use a task queue outside the request cycle: Celery on Redis or RabbitMQ, or ARQ for a lighter asyncio-native queue. On Quarkus the equivalent is JobRunr.

## `async def` on the loop, plain `def` in the threadpool

FastAPI accepts both forms for any route, and they are not stylistic variants. They run in different places:

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

`/thread/async` always reports `isMainThread: true`; Starlette awaits it on the loop. `/thread/sync` always reports `false`; Starlette sees a plain function and runs it on a worker thread through `anyio.to_thread.run_sync`.

The reason is the loop's single thread. A plain `def` handler has no `await` points, so a blocking call inside it, such as a synchronous database driver, `requests`, `time.sleep` or CPU work, would freeze every in-flight request if it ran on the loop. On a worker thread it blocks only itself.

The GIL decides how much that buys. Only one thread runs Python bytecode at a time, so a threadpool gives concurrency, not parallelism. That is enough for blocking I/O, because socket reads, file reads and most C-extension database drivers release the GIL while they wait, and the loop keeps serving. A tight pure-Python loop never releases it, so moving it to a thread doesn't help; CPU-bound work needs multiple processes or a C extension that drops the GIL. The free-threaded build (PEP 703, opt-in since CPython 3.13) targets that gap.

The failure mode is `async def` around a blocking call. FastAPI schedules it on the loop, the first blocking call freezes every other request for its duration, and nothing shows until concurrent load makes the stall matter.

## Decision rule

Choose per endpoint by what the handler blocks on.

| The handler | Declare it | Because |
|---|---|---|
| Awaits async drivers only (asyncpg, `httpx.AsyncClient`, an async Kafka client) | `async def` | It shares the loop cooperatively and costs nothing extra |
| Calls a blocking library with no async equivalent (a synchronous ORM, a legacy SDK) | `def` | The threadpool isolates the blocking from other requests |
| Does CPU-bound work of tens of milliseconds or more | `def` at best; better, another process | A thread still contends for the GIL |
| Runs on a low-traffic internal service where no slow handler competes with enough requests | Either | A stall is never noticed |

> **🤖 Explore with your agent**
>
> "In `examples/23-fastapi-depth`, add `GET /thread/blocking-async` declared `async def` that calls `time.sleep(1)`, and `GET /thread/blocking-sync` declared `def` that does the same. Run two concurrent requests against each and report which pair finishes in about 1 second and which in about 2, with the reason."
>
> Check: `./verify.sh` still passes, and the reply's timings for the two endpoints match the rule in the table above.

## Build, run, observe

```bash
cd examples/23-fastapi-depth && ./verify.sh
```

`verify.sh` starts the FastAPI service (port 8022) with `docker compose`. SSE frames arrive incrementally, `BackgroundTasks` returns `202` promptly while the notification stays absent until a bounded poll finds it, and the async and sync handlers report different threads. The SSE spread must reach 0.6 seconds, which tolerates CI jitter. It prints `PASS` when all hold. The full output is in `examples/23-fastapi-depth/README.md`.

- Replace `add_task` with an inline `await`: the response-time check and the empty-list check both fail.

## For deeper coverage

- [FastAPI docs: Concurrency and async / await](https://fastapi.tiangolo.com/async/): when `async def` helps and when plain `def` is right.
- [FastAPI docs: Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/): the reference for `BackgroundTasks.add_task`.
- Lukasz Dynowski & Marcin Dulak, *Learning API Styles* (O'Reilly, 2025): framework-level request-handling trade-offs across API styles.
- Cloud Native Design Patterns, "Anti-patterns" chapter: the `async def` around a blocking call mistake.
