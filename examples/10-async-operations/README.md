# Ch10 — Async / long-running operations

Extends the [Ch4 contract-first anchor](../04-contract-first/) with the
part of the contract that doesn't fit inside one request/response: starting
work that takes longer than an HTTP client should block for, and letting
the client come back later for the result.

- `contracts/openapi/shipping-api.yaml` — `requestConfirmation` /
  `getOperation`.
- `contracts/schemas/shipping.schema.json` — `Operation`,
  `OperationStatus`.

Quarkus (`quarkus/`, host port **8090**) and FastAPI (`python/`, host port
**8010**) independently implement the identical protocol against an
in-memory store. These ports are deliberately unique across the repo's
examples so this stack can run alongside any other chapter's without a
clash.

## Run it

```bash
cd examples/10-async-operations
./verify.sh
```

This brings both services up with `docker compose`, waits for health,
drives the confirmation lifecycle (and the cancel path) against
`localhost:8090` (Quarkus) and `localhost:8010` (FastAPI), schema-validates
every response, and tears the stack down again. Prints `PASS` only if every
assertion holds for **both** stacks.

To poke at it by hand instead:

```bash
docker compose up --build

# 1. Create a PENDING booking.
curl -s -X POST localhost:8090/bookings \
  -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
       "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":1000}}]}' | jq .

# 2. Start confirmation -> 202 + Location: /operations/{opId} + Operation body.
curl -si -X POST localhost:8090/bookings/<bookingId>/confirmation

# 3. Poll the operation until it 303s to the confirmed booking.
curl -si localhost:8090/operations/<opId>

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## The 202 -> poll -> 303 lifecycle

Confirming a booking runs routing/capacity checks that this example models
as taking longer than one request/response should block for:

1. **`POST /bookings/{id}/confirmation`** — the booking must be `PENDING`
   (otherwise `409 Problem`; unknown booking is `404 Problem`). Returns
   **202 Accepted** with a `Location: /operations/{opId}` header and an
   `Operation` body (`status: RUNNING`, since the worker starts
   immediately). The booking is **not** yet `CONFIRMED`.
2. A background worker — a scheduled task on each stack's own runtime
   (Quarkus: a daemon-thread `ScheduledExecutorService`; FastAPI:
   `asyncio.create_task` + `await asyncio.sleep(...)`) — completes the
   operation after a short, deterministic **~2s** delay: `status` becomes
   `SUCCEEDED`, `resource` is set to `/bookings/{id}`, and the booking
   transitions `PENDING` -> `CONFIRMED`.
3. **`GET /operations/{opId}`** — while the operation is still
   `PENDING`/`RUNNING`/`FAILED`, returns **200** with the `Operation` body.
   Once it's `SUCCEEDED`, returns **303 See Other** with `Location`
   pointing at the now-`CONFIRMED` booking. The client follows that
   redirect to get the final resource — the operation resource itself never
   turns into the booking resource; it just points at it.

```
Client                      Server                      Worker
  |-- POST .../confirmation ->|                            |
  |<-- 202 + Location --------|-- schedule (~2s) --------->|
  |                           |                            |
  |-- GET /operations/{id} -->|                            |
  |<-- 200 Operation(RUNNING)-|                            |
  |         ... poll ...      |                       (sleeps ~2s)
  |                           |<-- confirm booking ---------|
  |-- GET /operations/{id} -->|                            |
  |<-- 303 Location:/bookings/{id} --|                      |
  |-- GET /bookings/{id} ---->|                            |
  |<-- 200 Booking(CONFIRMED)-|                            |
```

## Cancel

`DELETE /operations/{opId}` cancels a still-running operation: **204 No
Content**, the operation moves to `FAILED` (with an `error` Problem
explaining it was client-cancelled), and — because the worker checks a
`cancelled` flag before applying its completion side effect — the booking
is **left `PENDING`**, never `CONFIRMED`. The race is resolved in the
cancel's favor on both stacks:

- **Quarkus**: `OperationStore.cancel()` and the scheduled completion task
  both synchronize on the same per-operation record; whichever runs first
  wins, and the completion task is a no-op once `cancelled` is set.
- **FastAPI**: `asyncio` is single-threaded and cooperative — `cancel()`
  runs to completion without yielding, so there's no window for the
  delayed task (which only awaits once, at the very start, during
  `asyncio.sleep`) to interleave with it.

`DELETE` is idempotent: cancelling an already-terminal operation (already
`SUCCEEDED` or `FAILED`) is a no-op that still returns 204, the same
convention `DELETE /bookings/{id}` uses for soft-delete.

## Endpoints implemented (identically, in both stacks)

| Method | Path                               | Success | Notes |
|--------|-------------------------------------|---------|-------|
| POST   | `/bookings`                         | 201     | from Ch4 — creates the `PENDING` booking to confirm |
| POST   | `/bookings/{id}/confirmation`       | 202/404/409 | `Location: /operations/{opId}`, body = `Operation` |
| GET    | `/operations/{opId}`                | 200/303/404 | `Operation` while running; `303 Location` once `SUCCEEDED` |
| DELETE | `/operations/{opId}`                | 204/404 | cancel a running operation; idempotent on a terminal one |
| GET    | `/bookings/{id}`                    | 200/404 | from Ch4 — used to confirm the final `CONFIRMED` state |

Errors are always `Problem` (`application/problem+json`): 404 unknown
booking/operation, 409 confirming a non-`PENDING` booking. `_links`
(HATEOAS) is intentionally omitted everywhere — that's Ch12.

## The drift probe

`verify.sh` is only worth running if it actually rejects a response that
drifts from the protocol. To see it happen, introduce one of these edits in
either stack and re-run `./verify.sh`:

**Option A — make confirmation return 200 instead of 202.**

In `python/app/main.py`'s `request_confirmation`, change:

```python
return _json(202, operation, headers={"Location": f"/operations/{op_id}"})
```

to:

```python
return _json(200, operation, headers={"Location": f"/operations/{op_id}"})  # BUG: not 202
```

(Or in `quarkus/.../BookingResource.java`'s `requestConfirmation`, change
`Response.status(Response.Status.ACCEPTED)` to `Response.status(Response.Status.OK)`.)

Re-run `./verify.sh`. It fails immediately at the confirmation assertion
for that stack:

```
lib.sh: FAIL — python POST /bookings/{id}/confirmation: expected HTTP 202, got 200
```

**Option B — never transition the operation to SUCCEEDED.**

In `python/app/operations.py`'s `_complete_confirmation`, comment out the
`record.status = OperationStatus.SUCCEEDED` line (leaving the operation
stuck `RUNNING` forever). Re-run `./verify.sh` — it polls for
`POLL_TIMEOUT_SECONDS` (10s) and then fails with:

```
lib.sh: FAIL — python operation op_... never returned 303 within 10s
```

Revert either edit and re-run `./verify.sh` — it goes back to `PASS` for
both stacks. That round trip (break it, watch the gate catch it, fix it,
watch the gate go green again) is the thing worth internalizing: the 202 ->
poll -> 303 *protocol* is enforced mechanically — status codes, headers,
and eventual state — not just "does the server respond."

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/10-async-lifecycle.{svg,excalidraw}`) show the
confirmation request's lifecycle: the 202 Accepted response, the background
worker completing the operation, and the client polling until the 303
redirect to the confirmed booking.
