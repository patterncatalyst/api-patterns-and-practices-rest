---
title: "Rerunnable jobs"
order: 11
part: "Asynchronous work & jobs"
description: "Model recurring, server-owned work: separate the schedule (configure) from each execution (a run record), so a job can fire on a timer and on demand without the client driving every run."
duration: "28 min"
---

Chapter 10 modeled work that outlasts one request but still belongs to one request — a client confirms a booking, the server hands back an `Operation` to poll, and once that operation reaches `SUCCEEDED` the whole episode is finished. Nothing about that `Operation` exists before the `POST` that created it, and nothing about it matters after the client stops polling. This chapter is about a different shape of problem: work that has no triggering request at all. Re-checking every manifest against the bookings it's supposed to cover isn't something a client asks for once and waits on — it's something that needs to happen every few minutes, forever, whether or not anyone is watching, for as long as the system is running. That's a **job**, not an operation, and treating it like an operation with a longer poll timeout misses the part that matters: who decides when it runs.

## Why this isn't just Chapter 10 again

The surface similarity is real. A reconcile job's single execution goes through the exact same states Chapter 10's confirmation did — `PENDING`, `RUNNING`, `SUCCEEDED` or `FAILED` — and this chapter's example reuses the `Operation` type from `contracts/schemas/shipping.schema.json` verbatim rather than inventing a parallel "JobRun" shape with the same four fields under different names. If a client already knows how to poll an operation, it already knows how to poll a job run. That reuse is deliberate, not incidental: a run record *is* a long-running operation, specifically one the server itself may also be the one to start.

The difference is what happens before that run record exists. Chapter 10's operation came into being because a client called `POST /bookings/{id}/confirmation` — no request, no operation, ever. A reconcile run comes into being because either a client asked for one on demand, or because a clock the server owns ticked over to the next scheduled interval, with no client involved at all. A naive way to approximate "runs periodically" without a server-owned schedule would be to have a client poll a `GET /jobs/manifest-reconcile/runs` endpoint and `POST` a new run every time enough time has passed since the last one. That design fails the moment two clients do it at slightly different cadences, or one client's cron job dies silently and nobody notices for a week, or the client-side timer and the server-side state drift because they were never the same clock. A job the client has to keep re-triggering isn't really server-owned work — it's client-owned polling wearing a job's clothes, with all of the client's downtime and bugs now part of the job's reliability story.

## The configure-vs-execute split

The fix is to stop treating "the job" as a single resource and recognize it's really two resources with two different owners. The **job definition** (whether the job is `enabled` and how often it should fire, `intervalSeconds`) is a schedule the client configures: `PUT /jobs/manifest-reconcile` with a body of `{"enabled": true, "intervalSeconds": 2}`. The **run** is a single execution of that job, and it is a resource the client never creates directly in the scheduled case; `GET /jobs/manifest-reconcile/runs` lists them, `GET /jobs/manifest-reconcile/runs/{runId}` reads one, and they come into existence because something, either the scheduler or an explicit request, decided it was time to execute.

That "something" is exactly two things, and only two: the job's own internal clock, ticking at the `intervalSeconds` the client most recently configured for as long as `enabled` stays `true`, and an explicit `POST /jobs/manifest-reconcile/runs` — a "run now" — that a client can call to get one additional execution without touching the schedule or waiting for the next tick. Both paths converge on the identical run-record resource, `PENDING → RUNNING → SUCCEEDED`/`FAILED`, because from the job's point of view there is no difference between a run the clock started and a run a human impatient for a result started; the only difference is which event triggered `startRun()`.

This is the part worth naming precisely, because it's easy to blur in casual conversation about "triggering a job": a client *configures* a schedule and may *additionally* request one ad hoc execution, but a client never *executes* anything directly. `POST .../runs` doesn't run the reconcile logic inline and block until it's done — it still returns `202 Accepted` with a `Location` pointing at the new run, exactly like Chapter 10's confirmation `POST`, because starting a run and finishing a run are still two different moments even when a client asked for the run by name. The server is the only thing that ever flips a run's status; the client only ever asks for one to exist and then watches.

{% include excalidraw.html file="11-job-lifecycle" alt="A diagram showing a server-owned schedule configured once by PUT /jobs/manifest-reconcile on one side, feeding a periodic scheduler that fires automatic runs at the configured interval, alongside an on-demand run-now POST that produces an additional run outside the schedule, with every run — whether scheduled or on-demand — following the identical PENDING to RUNNING to SUCCEEDED-or-FAILED lifecycle as its own queryable record." caption="Figure 11.1 — Configure the schedule once; each run is its own record." %}

## Why the server has to own the clock

It's worth being explicit about why this split buys reliability rather than just being architectural tidiness. If the schedule lived on the client — a cron entry on someone's laptop, a CI pipeline's scheduled trigger calling the API every few minutes — the job's cadence depends on infrastructure the API has no visibility into and no control over. The cron entry gets deleted during a migration and nobody notices the reconcile job stopped running until a customer complains about a stale manifest weeks later. Two different clients, each convinced they're the one responsible for keeping the job alive, both fire `POST`s on overlapping schedules, and now there are duplicate runs scanning the same bookings for no reason. A server-owned schedule collapses all of that into one source of truth: there's exactly one place the interval lives, exactly one thing deciding when the next run starts, and `GET /jobs/manifest-reconcile` is always able to answer "is this running right now, and how often" without reconstructing the answer from whichever external scheduler happens to still exist.

Keeping the run as its own resource, independent of the job definition, earns a second thing: queryable history. `GET /jobs/manifest-reconcile/runs` doesn't just answer "is it configured" — it answers "did it run, how many times, and did any of those runs fail," which is the question an operator has at 3 a.m. when a manifest looks wrong. A job definition with no separate run history can tell you the job is `enabled`; it can't tell you whether the last six ticks silently failed.

## The schedule, armed and re-armed, in both stacks

Both stacks keep a periodic timer whose period comes from whatever the client most recently configured, not a hardcoded constant — reconfiguring the interval has to visibly change the timer's behavior, or "the client configures the schedule" is a claim the code doesn't back up. Quarkus reaches for the same `ScheduledExecutorService` Chapter 10 used for its one-shot confirmation delay, just called with `scheduleAtFixedRate` instead of a single delayed task, and cancels the previous tick before arming a new one:

{% include codetabs.html langs="Quarkus|Python" %}

```java
public synchronized ConfigureResult configure(boolean enabled, int intervalSeconds) {
    JobDefinitionRecord existing = definition.get();
    boolean created = existing == null;
    String now = nowUtc();
    String createdAt = created ? now : existing.createdAt;
    JobDefinitionRecord updated = new JobDefinitionRecord(enabled, intervalSeconds, createdAt, now);
    definition.set(updated);
    rearmTick(intervalSeconds);
    return new ConfigureResult(updated.toJobDefinition(), created);
}

private void rearmTick(int intervalSeconds) {
    if (tickFuture != null) {
        tickFuture.cancel(false);
    }
    tickFuture = scheduler.scheduleAtFixedRate(
            this::tick, intervalSeconds, intervalSeconds, TimeUnit.SECONDS);
}

private void tick() {
    JobDefinitionRecord def = definition.get();
    if (def == null || !def.enabled) {
        return;
    }
    startRun();
}
```

```python
def configure(enabled: bool, interval_seconds: int) -> tuple[JobDefinition, bool]:
    global _definition
    created = _definition is None
    now = _now_utc()
    created_at = _definition.created_at if _definition else now
    _definition = _JobDefinitionRecord(
        enabled=enabled, interval_seconds=interval_seconds, created_at=created_at, updated_at=now,
    )
    _rearm_tick(interval_seconds)
    return _definition.to_job_definition(), created


def _rearm_tick(interval_seconds: int) -> None:
    global _tick_task
    if _tick_task is not None:
        _tick_task.cancel()
    _tick_task = asyncio.create_task(_tick_loop(interval_seconds))


async def _tick_loop(interval_seconds: int) -> None:
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            if _definition is not None and _definition.enabled:
                _start_run()
    except asyncio.CancelledError:
        pass
```

The FastAPI side reaches for the exact primitive Chapter 10's confirmation delay already used (`asyncio.create_task` running a loop that `await`s `asyncio.sleep`), just looped instead of one-shot, cancelling the previous ticker task the same way the Quarkus side cancels its `ScheduledFuture`. In both languages, `configure()` has to be reachable from a context where scheduling a background timer is legal: the FastAPI `PUT` handler is declared `async def` for the identical reason Chapter 10's `request_confirmation` was: `asyncio.create_task()` requires a running event loop, and a plain `def` endpoint runs on a worker thread that doesn't have one. Quarkus has no equivalent trap here either, for the same reason it didn't in Chapter 10: `JobStore` hands scheduling to an application-scoped `ScheduledExecutorService` that exists independently of whichever thread happened to handle the `PUT`.

Disabling the job (`PUT` with `enabled: false`) doesn't cancel the timer outright in either stack — the tick keeps firing on schedule, it just checks `enabled` first and returns immediately if the job is off. That's a deliberate choice: the schedule and the on/off switch are two different facts about the same job definition, and leaving the timer armed means re-enabling the job later doesn't require reconstructing when the next tick should land — it's already scheduled, waiting for `enabled` to flip back.

## Run execution and what it actually does

A run record, once started, moves through its lifecycle the same way Chapter 10's confirmation did — flip to `RUNNING`, do the work, flip to `SUCCEEDED` with a `completedAt` timestamp — except there's no booking resource at the far end for it to redirect to, because a reconcile run doesn't produce a new addressable resource the way a confirmation produces a `CONFIRMED` booking. Its `resource` field stays empty; the run record itself, once `SUCCEEDED`, *is* the complete record of what happened:

```java
private Operation startRun() {
    String runId = "op_" + Ulid.generate();
    RunRecord record = new RunRecord(runId, nowUtc());
    runs.put(runId, record);
    scheduler.execute(() -> executeRun(record));
    return record.toOperation();
}

private void executeRun(RunRecord record) {
    record.status.set(OperationStatus.RUNNING);
    int pendingCount = (int) bookingStore.listVisible().stream()
            .filter(b -> b.status() == BookingStatus.PENDING)
            .count();
    try {
        Thread.sleep(WORK_DELAY_MS);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
    record.completedAt = nowUtc();
    record.status.set(OperationStatus.SUCCEEDED);
}
```

The actual "reconcile" work in this example is kept small and trivial — a scan of the booking store, counting how many bookings are still `PENDING` — because the point of this chapter is the job *protocol*, not a real manifest-reconciliation engine comparing cargo manifests against carrier schedules line by line. A production version of this job would do that real comparison in place of the count; nothing about the configure/execute split, the run-record shape, or the scheduler changes based on what the work inside `executeRun` does. That's the design paying off in the direction a tutorial can't fully demonstrate: the protocol around the work is reusable across completely different "what does a run do" implementations, because the run record never needed to know.

Notice, too, what `startRun()` is called from: both the scheduler's own tick and the "run now" `POST` handler call the identical private method. There is exactly one code path that creates a run record and hands it to the executor — the scheduler doesn't have a parallel, slightly-different implementation of "start a run" from the one the on-demand endpoint uses. That's what makes the claim "both paths produce the same kind of resource" true in the code, not just true in the documentation describing the code.

## Proof

```bash
cd examples/11-rerunnable-jobs
./verify.sh
```

Quarkus comes up on port `8091`, FastAPI on `8011`, both chosen, as with every example in this book, to avoid colliding with another chapter's stack running at the same time. `verify.sh` starts by confirming both the job definition and the run endpoints correctly refuse to do anything before the job has ever been configured (`GET /jobs/manifest-reconcile` and `POST .../runs` both return `404 Problem`) because a job that hasn't been given a schedule yet shouldn't quietly accept run requests for one. It then `PUT`s a schedule of `intervalSeconds=2`, confirming `201` on the first configure and `200` on every subsequent one (the same create-vs-update distinction Chapter 6 established for `PUT`), issues a "run now," polls the resulting run until it reaches `SUCCEEDED`, and lists all runs to confirm that run shows up in the collection. Then it does the part a `202`-and-poll test alone can't prove: it waits past the configured two-second interval with no further client action and confirms the run count went up anyway — proof that the server's own scheduler, not the test script, produced that run. Every run-record body from both stacks is schema-validated against the shared `Operation` type before any assertion trusts it, and the script prints `PASS` only when both stacks agree on every step, including the scheduler firing on its own.

The example's README documents a drift probe worth running once: hardcode `intervalSeconds` to `0` in either stack's job-definition conversion, and `verify.sh` fails immediately on the first `PUT` with a mismatch between what was configured and what came back — proof the schedule round-trips through the server rather than being echoed from the request body unchecked. A second probe (commenting out the line that flips a run to `SUCCEEDED`) makes `verify.sh` time out waiting for a run that never finishes, which is the failure mode a job stuck `RUNNING` forever looks like from the outside.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>Disabling a job (<code>enabled: false</code>) stops new scheduled runs from being produced; it does not, and should not, cancel a run that's already <code>RUNNING</code>. The two are independent facts — whether the schedule is currently producing new work, and whether a specific run in flight should be allowed to finish — and conflating them means a client flipping a job off mid-run gets a truncated, inconsistent reconcile pass instead of either a clean completion or an explicit cancel. If a run truly needs to be interruptible, that's a cancel affordance on the run resource itself, the same shape Chapter 10 built for operations, not a side effect of disabling the schedule.</p></div>

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to recurring work. When the interaction shape is a single, bounded request/response — a client wants one thing to happen once, right now, and cares about the outcome of that specific call — model it as a direct synchronous call or, if it's long-running, Chapter 10's <code>202</code>/poll/<code>303</code> operation. Reach for a rerunnable job specifically when the work's correctness depends on it happening on a cadence no single client request initiates — reconciliation, cleanup, periodic sync against an external system — because client diversity and evolution pressure both argue against making any one caller responsible for triggering it. Split the schedule from the execution as two resources with two owners: the client configures <em>when</em> and <em>whether</em>, the server owns <em>that it actually happens</em>, and an on-demand run is an addition to the schedule for an impatient caller, never a substitute for the server owning the clock. Reuse the operation shape for a run record rather than inventing a parallel type — a run is a long-running operation that happens to also be startable by a timer, and a client that already knows how to poll one knows how to poll the other.</p></div>
