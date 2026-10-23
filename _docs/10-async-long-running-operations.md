---
title: "Asynchronous & long-running operations"
order: 10
part: "Asynchronous work & jobs"
description: "Model work that outlasts one request: return 202 with a Location to an operation resource, let the client poll it, redirect with 303 to the result on completion, and offer a cancel."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Model work that outlasts one request as `202 Accepted` plus a pollable `Operation` resource, instead of blocking the connection or returning a premature `200`.
- Redirect a completed operation with `303 See Other` rather than folding the resource it produced into the operation's own body.
- Implement a race-safe cancel (`DELETE /operations/{opId}`) where whichever of cancel or completion finalizes first wins, using a lock on Quarkus and cooperative single-threaded scheduling in `asyncio`.
- Recognize why a FastAPI handler calling `asyncio.create_task()` must be declared `async def`, not plain `def`.
- Decide, from the Chapter 2 axes, when synchronous handling is enough and when `202`/poll/`303` is warranted.

## Why this matters

Every chapter so far has assumed a request finishes inside the response that answers it: the server does the work, builds the representation, and the client has what it asked for before the connection closes. Confirming a booking breaks that assumption. A real confirmation runs a routing check against carrier schedules and a capacity check against the destination terminal: calls to systems this service doesn't own, with latency this service doesn't control. Modeling that as a single request/response forces a choice between two bad options, and this chapter exists because both of them are wrong in a specific, nameable way.

## Why one request can't hold this work

The first bad option is to block: hold the HTTP connection open while routing and capacity resolve, and return `200` once they do. This works until it doesn't: a carrier lookup that's usually 200ms occasionally takes eight seconds, a client's own timeout fires at five, and the server has done real work (and possibly already mutated state) that the client never learns about. The client retries into a resource that's mid-transition, the server now has two confirmation attempts racing against one booking, and nothing about the API's contract explains what either side should do next. Blocking couples the client's patience to a dependency this service doesn't control, and HTTP request timeouts are measured in single-digit seconds precisely because a client holding a connection open indefinitely is also a client that can't be told anything else is wrong.

The second bad option is to return a premature `200`: accept the confirmation request, kick off the routing and capacity checks in the background without telling the client, and report success immediately as if the work were already done. This is worse than blocking, not better, because it lies. The response claims a `CONFIRMED` booking that doesn't exist yet, and if the background checks later fail (no route available, terminal at capacity), there is no mechanism in the contract for the server to take that claim back. A `200` is supposed to mean the state described in the body is the state that exists; manufacturing one early breaks that guarantee for every client that trusts it.

The fix is to stop claiming the work finished and instead report that it started. RFC 9110 §15.3.3 gives this an exact status code: `202 Accepted` means the request has been accepted for processing, but the processing has not completed, and the eventual result may or may not match what was requested. Admitting that up front is the whole pattern; what follows is how to give the client something useful to do while it waits.

## The pattern: 202, poll, 303

`POST /bookings/{id}/confirmation` starts the async path. If the booking doesn't exist, that's a `404 Problem` exactly as every other chapter's missing-resource case has been. If the booking exists but isn't `PENDING` (already `CONFIRMED`, already `CANCELLED`), that's `409 Problem`, the same state-conflict code Chapter 6 built out for the synchronous case, because confirming is still a state-machine transition even when it takes longer than one request. When the booking is `PENDING`, the server does three things in the same response: it creates an **operation resource** to represent the in-progress work, it returns `202 Accepted` with that operation's body, and it sets `Location` to the operation's URI. The booking itself is left exactly as it was (still `PENDING`) because the confirmation hasn't happened yet, only started.

The operation is not an opaque job id tucked in a response field; it's a first-class resource with its own address, `/operations/{opId}`, and its own representation. The contract's shared `Operation` type (`contracts/schemas/shipping.schema.json`) fixes the shape: `id`, a `status` drawn from the `OperationStatus` enum (`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`), `createdAt`, and three fields that only populate once the operation finishes: `completedAt`, `resource` (the URI of whatever the operation produced or changed), and `error` (a `Problem`, present only on `FAILED`). Modeling it this way, as a GET-able resource with a lifecycle rather than a bare identifier the client has to know a separate endpoint shape for, means an operation obeys the same rules every other resource in this contract obeys: it has one canonical address, one media type, and one schema a client validates against regardless of which long-running action produced it. A reconcile job (Chapter 11) and a confirmation both resolve to the same `Operation` type; a client that knows how to poll one knows how to poll the other.

Polling is `GET /operations/{opId}`, and its response depends entirely on `status`. While the operation is `PENDING`, `RUNNING`, or terminally `FAILED`, the endpoint returns `200` with the full `Operation` body: the client reads `status` and decides whether to ask again. The moment `status` becomes `SUCCEEDED`, the response changes shape: `303 See Other` with `Location` pointing at the resource the operation produced, in this case the now-`CONFIRMED` booking. RFC 9110 §15.4.4 describes exactly this use: a `303` tells the client the result of the request isn't the operation resource itself but something else the client should `GET` separately. That distinction matters here specifically because the operation and the booking are different resources with different lifecycles: the operation is done and immutable the moment it reaches `SUCCEEDED`, while the booking it produced keeps living its own lifecycle afterward (loaded, in transit, delivered). Returning `303` rather than folding the booking's representation into the operation's body keeps that boundary intact: the operation records that work happened and where it landed, not what the thing it touched currently looks like.

{% include excalidraw.html file="10-async-lifecycle" alt="A sequence diagram showing a client POSTing a confirmation request and receiving 202 Accepted with a Location header pointing at a new operation resource, the client polling that operation and receiving 200 with status RUNNING while a background worker completes the confirmation, the poll eventually receiving 303 See Other with a Location pointing at the confirmed booking, and a parallel cancel branch where a DELETE on the still-running operation moves it to FAILED and leaves the booking PENDING instead of reaching SUCCEEDED." caption="Figure 10.1: The 202 -> poll -> 303 lifecycle, with cancel." %}

## 202 on the wire, in both stacks

The handler that returns `202` looks almost identical across the two stacks at the level of what it checks (existence, then state), but the Python side carries a gotcha worth reading closely, because it's the kind of mistake that fails silently rather than loudly:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@POST
@Path("/{id}/confirmation")
@Produces(MediaType.APPLICATION_JSON)
public Response requestConfirmation(@PathParam("id") String id) {
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
    # which has no running asyncio event loop — asyncio.create_task() inside
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

Every other handler in this example's FastAPI app is a plain `def`, and that's deliberate: a synchronous function FastAPI dispatches to a thread pool, which is the right default for handlers that don't need to await anything. `request_confirmation` is the one exception, and it has to be, because `operations.start_confirmation()` calls `asyncio.create_task()` to schedule the background worker, and `create_task` requires a running event loop in the calling context. A `def` endpoint runs in a worker thread with no event loop of its own; call `asyncio.create_task()` from inside one and it raises `RuntimeError: no running event loop`: not a wrong answer, a crash, and one that's easy to miss in development if the confirmation path isn't the first thing exercised. Declaring the endpoint `async def` puts it back on the loop the scheduling call needs. Quarkus has no equivalent trap: `OperationStore.startConfirmation()` hands the delayed work to a `ScheduledExecutorService` that the application scope owns independently of which thread happened to be running the JAX-RS method, so the resource method itself can stay however it's declared without the runtime having an opinion about it.

## Cancel, and the race it has to win

An operation that's still running is one a client can reasonably want to stop: the routing check hasn't resolved, the client changed its mind, or the booking needs to be edited before it's confirmed. `DELETE /operations/{opId}` is the cancel affordance, and it returns `204 No Content` on success, the same empty-body convention Chapter 5 established for `DELETE /bookings/{id}`. What `204` means here is specific: the operation moves to `FAILED`, its `error` field explains it was cancelled by client request rather than by any check actually failing, and (this is the part that takes real care to get right) the booking the operation was confirming is left exactly as it started, `PENDING`. A cancel that let the background worker finish anyway, confirming a booking the client had just told the server to stop confirming, would make the cancel endpoint a lie in the same way a premature `200` would have been.

Getting that right means resolving a real race: the cancel request and the background worker's completion can both be in flight at the same instant, and whichever one finalizes the operation first has to win, cleanly, with no window where both think they succeeded. `OperationStore.java` and `operations.py` reach the same guarantee by using the concurrency primitive each runtime already gives them (a lock on the Quarkus side, cooperative single-threaded scheduling on the FastAPI side) rather than inventing a new one:

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

The Quarkus scheduler runs on its own daemon threads, concurrently with the thread handling the `DELETE` request, so `cancel()` and `completeConfirmation()` both `synchronize` on the same per-operation record and check `cancelled` inside that lock before mutating anything; whichever one acquires the lock first wins outright, and the loser's branch is a no-op. The Python side needs no lock at all, because `asyncio` is single-threaded and cooperative: `cancel()` runs start-to-finish with no `await` in it, so nothing can interleave mid-mutation, and `_complete_confirmation()` only ever yields once, at its single `await asyncio.sleep(...)`; by the time it wakes up and checks `record.cancelled`, any cancel that happened during the sleep has already landed completely. Two different runtimes, two different reasons the race can't be lost, and the same observable guarantee: whichever one finalizes first, the other backs off instead of overwriting it. `DELETE` is also idempotent the way `DELETE /bookings/{id}` is: cancelling an operation that's already `SUCCEEDED` or `FAILED` is a no-op that still answers `204`, so a client that retries a cancel it isn't sure landed never gets a surprising error for asking twice.

## Polling etiquette

Nothing in this example's contract mandates a poll interval, and that gap should be named rather than left implicit: a server that knows roughly how long an operation takes can say so with a `Retry-After` header on the `202` or on a `200` poll response, giving the client a number instead of making it guess a backoff. This example skips `Retry-After` to keep the contract surface narrow, but a production confirmation flow with a less deterministic completion time is exactly where that header pays for itself: it turns "poll until you get tired" into "poll when the server expects to have an answer." `verify.sh` polls on a fixed one-second interval with a ten-second ceiling, which is a test harness's patience, not a recommendation for a real client; the lesson to take from the example isn't the interval, it's that the client is in a loop at all rather than blocked on one connection.

## Proof

The script brings up Quarkus on port `8090` and FastAPI on port `8010` (a pair chosen, like every other chapter's example, to avoid colliding with any other stack already running), waits for both health checks, then drives the full lifecycle against each: create a `PENDING` booking, `POST` the confirmation and check for `202` with a `Location` header and a schema-valid `RUNNING` `Operation`, confirm the booking is *still* `PENDING` immediately afterward, poll until the operation reaches `303`, follow that redirect and check the booking is now `CONFIRMED`, then run the whole sequence a second time but issue `DELETE` on the operation well inside its completion delay and confirm the booking stays `PENDING` forever after. It also checks the failure paths this chapter named: `409` on confirming an already-`CONFIRMED` booking, `404` on confirming or polling an id that was never issued, and a repeat `DELETE` on an already-terminal operation still returning `204`. Every body (`Operation`, `Booking`, `Problem`) is validated against `contracts/schemas/shipping.schema.json` before any assertion about it is trusted, and the script prints `PASS` only when both stacks agree on every one of those outcomes.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>A FastAPI handler that needs <code>asyncio.create_task()</code> (to kick off background work, not just to <code>await</code> something) must itself be <code>async def</code>. A plain <code>def</code> endpoint runs on a thread-pool thread with no event loop attached, and scheduling a task from inside one raises at request time rather than producing a silently wrong result. This is easy to miss because most handlers in an API this size have no reason to be anything but synchronous, which makes the one that does stand out only if you're looking for it.</p></div>

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to the sync-vs-async choice itself. Stay synchronous when the work's latency is bounded and small relative to a client's request timeout, and when there's nothing meaningful for the client to do between request and response except wait a few hundred milliseconds: forcing a poll loop onto work that's already fast adds a round trip for no benefit. Reach for <code>202</code> + poll + <code>303</code> specifically when the work's duration is variable, dependent on a system this service doesn't control, or long enough that holding a connection open risks a client-side timeout regardless of whether the work eventually succeeds. Model the in-progress work as its own resource (an <code>Operation</code> with an id, a status, and an address) rather than an ad hoc job token, so the same polling and schema-validation machinery serves every long-running action in the contract, not a bespoke shape per endpoint. And offer a cancel specifically when the work is meaningfully abortable before it commits any side effect; if cancelling can only race a side effect that's already irreversible by the time the client decides to stop, say so in the documentation rather than exposing a <code>DELETE</code> that sometimes quietly does nothing.</p></div>

## Build, run, observe

```bash
cd examples/10-async-operations && ./verify.sh
```

`verify.sh` brings up Quarkus and FastAPI with `docker compose`, drives a booking through the `202`/poll/`303` confirmation lifecycle and a cancel against both stacks, and schema-validates every `Operation`, `Booking`, and `Problem` body against the shared contract. It prints `PASS` once every assertion holds for both stacks; the full run output is in `examples/10-async-operations/README.md`.

## For deeper coverage

- [RFC 9110 §15.3.3: 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110#section-15.3.3) and [§15.4.4: 303 See Other](https://www.rfc-editor.org/rfc/rfc9110#section-15.4.4): the two status codes this chapter's lifecycle is built on.
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): async and long-running-operation patterns.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): the long-running-operation pattern and its resource shape.
- James Gough, Daniel Bryant & Matthew Auburn, *Mastering API Architecture* (O'Reilly, 2022): operational patterns for work that outlasts a request.
