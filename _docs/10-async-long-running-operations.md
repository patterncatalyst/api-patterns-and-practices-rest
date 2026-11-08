---
title: "Asynchronous & long-running operations"
order: 10
part: "Asynchronous work & jobs"
description: "Model work that outlasts one request: return 202 with a Location to an operation resource, let the client poll it, redirect with 303 to the result, and offer a cancel."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Model work that outlasts one request as `202 Accepted` plus a pollable `Operation` resource, instead of blocking the connection or returning a premature `200`.
- Redirect a completed operation with `303 See Other` instead of folding the produced resource into the operation's body.
- Implement a race-safe cancel (`DELETE /operations/{opId}`) where whichever of cancel or completion finalizes first wins, using a lock on Quarkus and cooperative scheduling in `asyncio`.
- Explain why a FastAPI handler that calls `asyncio.create_task()` must be `async def`.
- Decide when synchronous handling is enough and when `202`, poll and `303` are warranted.

## Why this matters

Confirming a booking runs a routing check against carrier schedules and a capacity check against the destination terminal: calls to systems this service doesn't own, with latency it doesn't control. A single request and response forces a choice between two options, and both are wrong.

{% include excalidraw.html file="10-async-lifecycle" alt="Sequence: the client POSTs a confirmation and gets 202 with a Location to an operation. Polls return 200 with RUNNING, then 303 to the confirmed booking. A DELETE on the running operation moves it to FAILED and leaves the booking PENDING." caption="Figure 10.1: The 202, poll, 303 lifecycle, with cancel." %}

## Pattern: Long-Running Operation

### The problem

**Blocking** holds the connection open until routing and capacity resolve, then returns `200`. A carrier lookup that usually takes 200 ms occasionally takes eight seconds, the client's timeout fires at five, and the server has done work, possibly mutating state, that the client never learns about. The client retries into a booking that is mid-transition, and two confirmation attempts race. Blocking ties the client's patience to a dependency the service doesn't control.

**A premature `200`** starts the checks in the background and reports success at once. That response claims a `CONFIRMED` booking that doesn't exist yet, and if the checks later fail (no route, terminal at capacity), the contract has no way to take the claim back. A `200` must mean the state in the body is the state that exists.

### The solution

**Report that the work started, not that it finished: return `202 Accepted` with a `Location` to an operation resource the client polls, and `303 See Other` to the result when it succeeds.**

RFC 9110 §15.3.3 defines `202` as accepted for processing, not completed, with an eventual result that may differ from the request.

`POST /bookings/{id}/confirmation` starts the path:

| Booking state | Response |
| --- | --- |
| Not found | `404` Problem |
| Exists, not `PENDING` | `409` Problem, because confirming is a state transition even when it takes longer than one request |
| `PENDING` | `202` with the operation body and `Location: /operations/{opId}`; the booking stays `PENDING` |

The operation is a first-class resource at `/operations/{opId}`, not an opaque job id. The shared `Operation` type in `contracts/schemas/shipping.schema.json` fixes its shape:

- `id`
- `status`: `PENDING`, `RUNNING`, `SUCCEEDED` or `FAILED`
- `createdAt`
- `completedAt`, `resource` (the URI of what the operation produced) and `error` (a `Problem`, only on `FAILED`), populated when it finishes

One schema serves every long-running action, so a client that polls a confirmation can poll a reconcile job.

`GET /operations/{opId}` depends on `status`:

| Status | Response |
| --- | --- |
| `PENDING`, `RUNNING`, `FAILED` | `200` with the full `Operation`; the client reads `status` and decides whether to ask again |
| `SUCCEEDED` | `303` with `Location` at the produced resource, here the `CONFIRMED` booking |

RFC 9110 §15.4.4 describes this use of `303`: the result isn't the operation but something else to `GET`. The operation is immutable once it succeeds; the booking keeps its own lifecycle (loaded, in transit, delivered). The operation records that work happened and where it landed, not what the target looks like now.

### How Quarkus and FastAPI model it

Both handlers check existence, then state, then start the work:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@POST
@Path("/{id}/confirmation")
@Produces(MediaType.APPLICATION_JSON)
public Response requestConfirmation(@RestPath String id) {
    Booking booking = store.get(id);
    if (booking == null) {
        return notFound(id);
    }
    if (booking.status() != BookingStatus.PENDING) {
        return problem(409, "Booking not confirmable",
                "Booking " + id + " is not PENDING (status=" + booking.status() + ")");
    }

    String opId = "op_" + Ulid.generate();
    Operation operation = operationStore.startConfirmation(opId, id, store);

    // Same rationale as createBooking(): a literal header string, not
    // Response.created(URI), keeps this byte-for-byte identical to the
    // Python stack's relative Location.
    return Response.status(Response.Status.ACCEPTED)
            .header("Location", "/operations/" + opId)
            .entity(operation)
            .build();
}
```

```python
@app.post("/bookings/{booking_id}/confirmation", status_code=202)
async def request_confirmation(booking_id: str) -> JSONResponse:
    # async def (not def, unlike this module's other handlers): FastAPI
    # runs a plain `def` endpoint in a worker thread via run_in_threadpool,
    # which has no running asyncio event loop: asyncio.create_task() inside
    # operations.start_confirmation() needs one. An `async def` endpoint
    # runs directly on the event loop that the background task is
    # scheduled onto.
    booking = store.get(booking_id)
    if booking is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    if booking.status != BookingStatus.PENDING:
        return _problem(
            409, "Booking not confirmable",
            f"Booking {booking_id} is not PENDING (status={booking.status.value})",
        )

    op_id = f"op_{generate_ulid()}"
    operation = operations.start_confirmation(op_id, booking_id)
    return _json(202, operation, headers={"Location": f"/operations/{op_id}"})
```

Every other FastAPI handler here is a plain `def`, which FastAPI runs in a thread pool. `request_confirmation` must be `async def`, because `operations.start_confirmation()` calls `asyncio.create_task()`, which needs a running event loop. A `def` endpoint runs in a worker thread with no loop, and `create_task` raises `RuntimeError: no running event loop`. It's easy to miss if the confirmation path isn't the first one exercised.

Quarkus has no equivalent trap. `OperationStore.startConfirmation()` hands the delayed work to a `ScheduledExecutorService` owned by the application scope, independent of the thread running the JAX-RS method.

## Cancel, and the race it has to win

A client can reasonably want to stop a running operation. `DELETE /operations/{opId}` returns `204 No Content`, the same empty-body convention as `DELETE /bookings/{id}`. The operation moves to `FAILED`, its `error` says it was cancelled by client request rather than by a failed check, and the booking stays `PENDING`. A cancel that let the worker finish and confirm the booking anyway would be a lie, like a premature `200`.

The cancel and the worker's completion can be in flight at the same instant, and whichever finalizes the operation first must win cleanly. Each runtime uses its own primitive:

{% include codetabs.html langs="Quarkus|Python" %}

```java
public boolean cancel(String opId) {
    OperationRecord record = operations.get(opId);
    if (record == null) {
        return false;
    }
    synchronized (record) {
        OperationStatus current = record.status.get();
        if (current != OperationStatus.PENDING && current != OperationStatus.RUNNING) {
            return false;
        }
        record.cancelled.set(true);
        record.status.set(OperationStatus.FAILED);
        record.completedAt = nowUtc();
        record.error = new Problem("Operation cancelled", 499,
                "Cancelled by client request before completion");
    }
    return true;
}

private void completeConfirmation(String opId, BookingStore bookingStore) {
    OperationRecord record = operations.get(opId);
    if (record == null) {
        return;
    }
    synchronized (record) {
        if (record.cancelled.get()) {
            return; // cancel() already finalized this operation as FAILED.
        }
        bookingStore.confirm(record.bookingId);
        record.status.set(OperationStatus.SUCCEEDED);
        record.completedAt = nowUtc();
        record.resource = "/bookings/" + record.bookingId;
    }
}
```

```python
def cancel(op_id: str) -> bool:
    """Cancels a still-PENDING/RUNNING operation. Returns False if unknown
    or already terminal (SUCCEEDED/FAILED); the caller treats DELETE as
    idempotent either way. The delayed completion below checks `cancelled`
    before mutating anything, so a cancel that wins the race leaves the
    booking PENDING.
    """
    record = _operations.get(op_id)
    if record is None or record.status not in (OperationStatus.PENDING, OperationStatus.RUNNING):
        return False
    record.cancelled = True
    record.status = OperationStatus.FAILED
    record.completed_at = _now_utc()
    record.error = Problem(
        title="Operation cancelled", status=499,
        detail="Cancelled by client request before completion",
    )
    return True


async def _complete_confirmation(op_id: str) -> None:
    await asyncio.sleep(CONFIRMATION_DELAY_SECONDS)
    record = _operations.get(op_id)
    if record is None or record.cancelled:
        return
    booking = store.get(record.booking_id)
    if booking is not None and booking.status == BookingStatus.PENDING:
        confirmed = booking.model_copy(update={"status": BookingStatus.CONFIRMED, "updatedAt": _now_utc()})
        store.put(confirmed)
    record.status = OperationStatus.SUCCEEDED
    record.completed_at = _now_utc()
    record.resource = f"/bookings/{record.booking_id}"
```

Quarkus runs the scheduler on daemon threads, concurrent with the thread handling the `DELETE`. Both `cancel()` and `completeConfirmation()` synchronize on the same per-operation record and check `cancelled` inside the lock, so the loser's branch is a no-op. Python needs no lock: `asyncio` is single-threaded and cooperative, `cancel()` has no `await`, and `_complete_confirmation()` yields once, at its sleep. A cancel during the sleep has landed completely by the time the worker checks `record.cancelled`.

`DELETE` is idempotent: cancelling an operation that is already `SUCCEEDED` or `FAILED` is a no-op that still answers `204`, so a client retrying a cancel it isn't sure landed gets no surprise error.

## Polling

The contract sets no poll interval. A server that knows roughly how long the work takes can send `Retry-After` on the `202` or on a `200` poll, so the client gets a number instead of guessing a backoff. The contract omits it to stay narrow; a flow with less predictable completion should add it. The point is that the client is in a loop at all, not blocked on one connection.

## When to use it

| Situation | Choice |
| --- | --- |
| Latency is bounded and small against client timeouts, and the client has nothing to do but wait | Stay synchronous; a poll loop adds a round trip for nothing |
| Duration varies, depends on a system you don't control, or risks a client timeout | `202`, poll, `303` |
| Any long-running action | An `Operation` resource, not a bespoke job token per endpoint |
| Work is abortable before it commits a side effect | Offer cancel; if it can only race an irreversible effect, document that instead of exposing a `DELETE` that quietly does nothing |

> **🤖 Explore with your agent**
>
> "In `examples/10-async-operations`, add a `Retry-After: 1` header to the `202` from `POST /bookings/{id}/confirmation` and to `200` responses from `GET /operations/{opId}` while the status is `PENDING` or `RUNNING`, on both the Quarkus `BookingResource`/`OperationResource` and the FastAPI `app/main.py`. Keep `async def request_confirmation` and don't change the cancel locking."
>
> Check: `curl -i -X POST localhost:8090/bookings/<id>/confirmation` (FastAPI on `8010`) shows `Retry-After`, and `./verify.sh` still prints `PASS`.

## Build, run, observe

Quarkus listens on `8090` and FastAPI on `8010`.

```bash
cd examples/10-async-operations && ./verify.sh
```

It starts both stacks, drives a booking through `202`, poll and `303` to `CONFIRMED`, runs a second booking through a cancel that leaves it `PENDING`, and checks the `409`, `404` and repeat-`DELETE` paths. Every `Operation`, `Booking` and `Problem` body is validated against the shared schema. It prints `PASS` when both stacks agree. Full output is in `examples/10-async-operations/README.md`.

Experiments:

- Change `request_confirmation` from `async def` to `def`. The first confirmation fails with `no running event loop`.
- Remove the `cancelled` check from the completion path. A cancelled operation confirms its booking anyway.

## For deeper coverage

- [RFC 9110 §15.3.3: 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110#section-15.3.3) and [§15.4.4: 303 See Other](https://www.rfc-editor.org/rfc/rfc9110#section-15.4.4): the two status codes the lifecycle is built on.
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): async and long-running-operation patterns.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): the long-running-operation pattern and its resource shape.
- James Gough, Daniel Bryant & Matthew Auburn, *Mastering API Architecture* (O'Reilly, 2022): operational patterns for work that outlasts a request.

