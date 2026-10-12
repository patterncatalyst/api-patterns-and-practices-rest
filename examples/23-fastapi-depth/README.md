# Ch23 — FastAPI in depth

Ch22 went under the hood of Quarkus REST's build-time, zero-reflection
parameter model. This is the FastAPI corollary: a single-stack, Python-only
example (no `quarkus/` here — unlike the cross-stack chapters, Ch23 is a
per-framework deep-dive) covering three places where FastAPI/ASGI behavior
is easy to get wrong *without ever producing a wrong-looking status code*.

| Mechanic | Endpoint | What a naive implementation gets away with |
|---|---|---|
| `StreamingResponse` + SSE | `GET /bookings/{id}/events` | Right status, right `Content-Type`, right bytes — just all of them at once instead of trickling in |
| `BackgroundTasks` | `POST /bookings/{id}/notify` | A 202 that actually did the work synchronously before responding |
| async vs. threadpool | `GET /thread/async`, `GET /thread/sync` | Both "work" — the question is which execution context actually served the request |

- `contracts/schemas/shipping.schema.json` — `#/$defs/Booking` (minted by
  `POST /bookings`, just enough of the Ch4 resource to hang events and
  notifications off an id) and `#/$defs/BookingEvent` (the SSE payload).
  Reused unchanged — Ch23 doesn't invent its own wire shapes for these.

One service (`python/`, port 8022→8000) against an in-memory store.
`verify.sh` creates a booking, then drives all three mechanics and checks
not just status codes but the thing each one actually promises.

## Run it

```bash
cd examples/23-fastapi-depth
./verify.sh
```

This brings the service up with `docker compose`, waits for health, drives
the three-part sequence against `localhost:8022`, and tears the stack down
again. Prints `PASS` only if every assertion holds.

To poke at it by hand instead:

```bash
docker compose up --build

booking_id=$(curl -s -X POST localhost:8022/bookings \
  -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
       "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":1000}}]}' \
  | jq -r .id)

curl -N "localhost:8022/bookings/$booking_id/events"          # SSE: watch frames arrive one by one

curl -s -X POST localhost:8022/bookings/$booking_id/notify \
  -H 'Content-Type: application/json' -d '{"message":"hi"}'   # 202, immediately
curl -s localhost:8022/bookings/$booking_id/notifications      # empty right away...
sleep 1.2
curl -s localhost:8022/bookings/$booking_id/notifications      # ...then shows the notification

curl -s localhost:8022/thread/async | jq                       # isMainThread: true
curl -s localhost:8022/thread/sync | jq                        # isMainThread: false

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default (the app
doesn't ship telemetry yet):

```bash
docker compose --profile observability up --build
```

## 1. StreamingResponse + SSE — proving incremental delivery

`GET /bookings/{id}/events` streams five deterministic cargo-status
`#/$defs/BookingEvent` frames (`CONFIRMED → IN_TRANSIT → IN_TRANSIT →
IN_TRANSIT → DELIVERED`, 250ms apart) via an async generator that `await
asyncio.sleep(...)`s *between* yields (`app/main.py`'s `_sse_event_stream`).

A buffered implementation — build the whole list, then yield it once —
would pass every status-code and `Content-Type` check here. `verify.sh`
instead opens the stream a second time and reads it line-by-line through a
plain bash loop piped straight from `curl -N` (no internal buffering on
curl's side), timestamping each `data:` line the moment the loop actually
receives it:

```bash
while IFS= read -r line; do
  printf '%s|%s\n' "$(date +%s.%N)" "$line"
done < <(curl -sS -N --max-time 8 "$base/bookings/$booking_id/events")
```

Five frames 250ms apart gives an ideal first-frame-to-last-frame spread of
~1.0s; `verify.sh` asserts `>= 0.6s` (60% of ideal, enough margin for CI
jitter, far above the near-zero spread a buffered implementation produces).
Same technique Ch16 and Ch22 use — see their READMEs for why the obvious
alternative (curl's aggregate `time_starttransfer`/`time_total`) doesn't
work: both streamed and buffered responses flush HTTP headers immediately,
so that comparison measures the same total compute time either way.

## 2. BackgroundTasks — prompt response, deferred-but-observable effect

`POST /bookings/{id}/notify` schedules `_send_notification` via
`background_tasks.add_task(...)` and returns `202 {"status": "queued"}`
immediately. The task itself sleeps for `NOTIFY_DELAY_SECONDS` (1.0s,
standing in for a real email/SMS/webhook call) and then appends to an
in-memory per-booking notification log — but only *after* the response has
already gone out.

`verify.sh` asserts the full shape of that promise, not just the status
code:

1. The POST itself returns in well under 0.5s (`NOTIFY_MAX_RESPONSE_SECONDS`)
   — far faster than the 1.0s the background work takes — proving the
   handler didn't `await` the notification work inline.
2. `GET /bookings/{id}/notifications` **immediately** after the POST
   returns an **empty** list — proving the side effect genuinely hasn't
   happened yet, not just that the client didn't wait for it.
3. Polling the same endpoint (bounded timeout, 5s) eventually finds the
   notification, with the message that was posted — proving the background
   task actually ran and its effect is observable through a normal request/
   response cycle, not just internal app state.

A disguised-synchronous implementation (`await _send_notification(...)`
before returning the 202) would still return `202 {"status": "queued"}` —
but it would blow the prompt-response budget in step 1, and step 2 would
already show the notification instead of an empty list. Either failure
alone pins the bug precisely: "ran the work inline" has two distinct,
independently-wrong fingerprints, and this script checks both.

## 3. async vs. threadpool — the GIL story, made observable

`GET /thread/async` is `async def`; `GET /thread/sync` is a plain `def`.
Both "work" — FastAPI accepts either style for any route — but they run on
different execution contexts:

- uvicorn runs this app as a single process with its event loop on the
  **main thread** (no `--workers`, no reload forking).
- An `async def` handler is awaited directly on that loop, so
  `threading.current_thread() is threading.main_thread()` is **always
  `True`** for `/thread/async`.
- A plain `def` handler is detected by Starlette and offloaded via
  `anyio.to_thread.run_sync` to a worker thread from its threadpool, so the
  same check is **always `False`** for `/thread/sync` — and the reported
  thread name is never the main thread's.

This is *why* FastAPI's guidance is "use `async def` + `await` for I/O, and
plain `def` only for work you're fine handing to a thread": the two styles
aren't interchangeable implementation details, they're genuinely different
places code executes — one shares the single event loop with every other
in-flight `async def` request, the other borrows a thread from a bounded
pool. `verify.sh` calls each endpoint twice to confirm the split is
deterministic, not an artifact of request ordering.

## The drift probe

To see the BackgroundTasks gate actually catch a regression, introduce
this edit and re-run `./verify.sh`:

**Await the notification work inline instead of backgrounding it.**

In `python/app/main.py`'s `notify_booking`, change:

```python
    background_tasks.add_task(_send_notification, booking_id, payload.message)
    return JSONResponse(
        status_code=202,
        content={"bookingId": booking_id, "status": "queued"},
    )
```

to:

```python
    await _send_notification(booking_id, payload.message)  # BUG: inline, not backgrounded
    return JSONResponse(
        status_code=202,
        content={"bookingId": booking_id, "status": "queued"},
    )
```

Re-run `./verify.sh`. The response still comes back `202 {"status":
"queued"}` — but now it takes ~1.0s instead of milliseconds, and the very
next assertion (the "immediately after" GET) finds the notification already
present instead of an empty list. Either check alone fails the run; both
point straight at the same bug:

```
lib.sh: POST /notify responded in 1.012s (budget 0.5s, background delay 1.0s)
lib.sh: FAIL — POST /notify took 1.012s, exceeding the 0.5s prompt-response budget — looks like the notification ran SYNCHRONOUSLY before the response was sent, not as a background task
```

Revert the edit and re-run `./verify.sh` — it goes back to `PASS`. That
round trip (break it, watch the gate catch it, fix it, watch it go green
again) is the thing worth internalizing: a `202 Accepted` is only honest if
the thing it claims to have deferred is actually still pending when the
client reads the response, not already done behind a status code chosen to
look async.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/23-fastapi-in-depth.{svg,excalidraw}`) show the three
mechanics side by side: an SSE client receiving frames over time, a
`POST`/202 response racing ahead of its own background task, and two
requests landing on different execution contexts (event loop vs. threadpool
worker) inside the same uvicorn process.
