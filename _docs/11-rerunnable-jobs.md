---
title: "Rerunnable jobs"
order: 11
part: "Asynchronous work & jobs"
description: "Model recurring, server-owned work: separate the schedule from each execution's run record, so a job fires on a timer and on demand without the client driving every run."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Split a recurring job into a server-owned job definition (`PUT /jobs/manifest-reconcile`) and independent run records.
- Reuse the `Operation` type for a job run instead of inventing a parallel `JobRun` shape.
- Re-arm a periodic timer (`scheduleAtFixedRate` or `_tick_loop`) so a reconfigured `intervalSeconds` takes effect immediately.
- Route a scheduled tick and an on-demand `POST .../runs` through the same `startRun()` or `_start_run()`, so every run is created identically.
- Distinguish disabling a job (`enabled: false`) from cancelling a run that is already `RUNNING`.

## Why this matters

A long-running operation belongs to one request: a client confirms a booking, polls the `Operation`, and the episode ends when it reaches `SUCCEEDED`. Re-checking every manifest against the bookings it should cover has no triggering request. It must happen every few minutes, whether or not anyone is watching. That's a **job**, and treating it as an operation with a longer poll timeout misses the question that matters: who decides when it runs.

## Pattern: Rerunnable Job

### The problem

Without a server-owned schedule, the cadence lives on the client: a cron entry on a laptop, or a CI trigger that calls `POST .../runs` when enough time has passed. That fails in predictable ways:

- A migration deletes the cron entry, and nobody notices the reconcile stopped until a customer reports a stale manifest.
- Two clients each believe they keep the job alive, and duplicate runs scan the same bookings.
- Client timer and server state drift, because they were never the same clock.

A job the client must keep re-triggering is client-owned polling, and the client's downtime and bugs become the job's reliability story.

### The solution

**Split the job into a schedule the client configures and a run record the server creates, so the server owns the clock and every execution is its own resource.**

| Resource | Owner | Endpoints |
| --- | --- | --- |
| Job definition: `enabled`, `intervalSeconds` | Client configures | `PUT /jobs/manifest-reconcile` with `{"enabled": true, "intervalSeconds": 2}`; `GET /jobs/manifest-reconcile` |
| Run: one execution | Server creates | `GET /jobs/manifest-reconcile/runs`, `GET /jobs/manifest-reconcile/runs/{runId}` |

Exactly two things create a run: the job's own clock, ticking at the last configured `intervalSeconds` while `enabled` is `true`, and an explicit `POST /jobs/manifest-reconcile/runs` ("run now") that adds one execution without touching the schedule. Both produce the same run record, `PENDING`, `RUNNING`, then `SUCCEEDED` or `FAILED`.

A client configures a schedule and may request one extra execution, but it never executes anything. `POST .../runs` returns `202 Accepted` with a `Location` to the new run, as a confirmation does, because starting a run and finishing it are different moments. Only the server flips a run's status.

A run record is a long-running operation that a timer can also start, so the shared `Operation` type from `contracts/schemas/shipping.schema.json` is used verbatim. A client that can poll a confirmation can poll a run.

Keeping runs separate from the definition also gives queryable history. `GET .../runs` answers "did it run, how many times, did any fail", the question an operator asks at 3 a.m. A definition alone says the job is `enabled`; it can't say the last six ticks failed.

{% include excalidraw.html file="11-job-lifecycle" alt="A schedule configured once by PUT /jobs/manifest-reconcile feeds a server-owned periodic scheduler that fires runs at the interval. An on-demand POST adds a run outside the schedule. Every run follows PENDING, RUNNING, then SUCCEEDED or FAILED as its own queryable record." caption="Figure 11.1: Configure the schedule once; each run is its own record." %}

### How Quarkus and FastAPI model it

Each stack keeps a periodic timer whose period comes from the client's latest configuration, not a constant. Quarkus uses the same `ScheduledExecutorService` as a one-shot delay, called with `scheduleAtFixedRate`, and cancels the previous tick before arming a new one. FastAPI runs a task that loops on `asyncio.sleep(interval_seconds)` and cancels the previous task the same way:

{% include codetabs.html langs="Quarkus|Python" %}

```java
/**
 * Upserts the job definition (server-owned schedule) and re-arms the
 * periodic ticker at the new {@code intervalSeconds}; this is what
 * makes "the client configures the schedule" literally true: the
 * scheduler's cadence comes from the configured value, not a hardcoded
 * constant.
 */
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
```

```python
def configure(enabled: bool, interval_seconds: int) -> tuple[JobDefinition, bool]:
    """Upserts the job definition (server-owned schedule) and re-arms the
    periodic ticker at the new `interval_seconds`; this is what makes "the
    client configures the schedule" literally true: the ticker's cadence
    comes from the configured value, not a hardcoded constant. Must be
    called from a coroutine running on the event loop (an `async def`
    endpoint), since it creates an asyncio task, the same gotcha as
    an `async def` confirmation handler.
    """
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
```

The FastAPI `PUT` handler is `async def` because `asyncio.create_task()` needs a running event loop, and a plain `def` endpoint runs on a worker thread without one. Quarkus has no such trap: `JobStore` hands scheduling to an application-scoped executor that doesn't depend on the request thread.

Disabling the job doesn't cancel the timer in either stack. Each tick reads the current definition and returns at once if it is missing or `enabled` is false; otherwise it calls the same run-start method as "run now". The schedule and the on/off switch are separate facts, so re-enabling needs no reconstruction of when the next tick lands.

### Run execution

A run flips to `RUNNING`, does its work and flips to `SUCCEEDED` with `completedAt`. A reconcile run produces no new addressable resource, so `resource` stays empty and the run record is the complete record of what happened. The work here is a scan counting `PENDING` bookings; a real reconciliation replaces that, and the schedule, run shape and scheduler don't change.

```java
private Operation startRun() {
    // "op_" prefix (not "run_"): this run record reuses
    // #/$defs/Operation verbatim, including its id pattern
    // (^op_[0-9A-HJKMNP-TV-Z]{26}$); see model/Operation.java's javadoc.
    String runId = "op_" + Ulid.generate();
    RunRecord record = new RunRecord(runId, nowUtc());
    runs.put(runId, record);
    scheduler.execute(() -> executeRun(record));
    return record.toOperation();
}
```

The scheduler's tick and the "run now" handler call the same `startRun()`. One code path creates a run and hands it to the executor, so both triggers produce the same resource by construction.

## Disabling versus cancelling

`enabled: false` stops new scheduled runs. It doesn't cancel a run already `RUNNING`, and it shouldn't. Whether the schedule produces new work and whether a run in flight may finish are independent. Conflating them gives a client that flips a job off mid-run a truncated, inconsistent pass instead of a clean completion or an explicit cancel. If runs must be interruptible, put a cancel on the run resource, as an operation has.

## When to use it

| Situation | Choice |
| --- | --- |
| One bounded request, the client wants one thing now | A synchronous call, or `202`, poll and `303` if it is slow |
| Correctness depends on a cadence no single request starts (reconciliation, cleanup, periodic sync) | A rerunnable job |
| Who configures and who guarantees | Client configures when and whether; the server owns that it happens |
| An impatient caller | "Run now" adds to the schedule, never replaces the server's clock |
| Run record shape | Reuse `Operation` |

> **🤖 Explore with your agent**
>
> "In `examples/11-rerunnable-jobs`, add `DELETE /jobs/manifest-reconcile/runs/{runId}` on both the Quarkus `JobStore` and the FastAPI `app/jobs.py`. It cancels a `RUNNING` run to `FAILED` with a 499 Problem and answers `204`, is a no-op `204` on a finished run, and leaves `enabled` and the tick untouched."
>
> Check: PUT a job with `intervalSeconds: 2`, `POST .../runs`, then `DELETE` the new run within its work delay and expect `204`; the run reads `FAILED`, and a later scheduled tick still creates a new run.

## Build, run, observe

Quarkus listens on `8091` and FastAPI on `8011`.

```bash
cd examples/11-rerunnable-jobs && ./verify.sh
```

It starts both stacks, checks that `GET /jobs/manifest-reconcile` and `POST .../runs` return `404 Problem` before the job is configured, then `PUT`s `intervalSeconds=2` (`201` the first time, `200` after), runs "run now" to `SUCCEEDED`, and waits past the interval to confirm the server's own scheduler created another run. Every run body is validated against the shared `Operation` type. It prints `PASS` when both stacks agree. Full output is in `examples/11-rerunnable-jobs/README.md`.

Experiments:

- Hardcode `intervalSeconds` to `0` in the job-definition conversion. The first `PUT` fails, because the configured value no longer round-trips.
- Remove the line that flips a run to `SUCCEEDED`. The run never finishes and the check times out, which is how a job stuck `RUNNING` looks from outside.

## For deeper coverage

- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): resource-oriented patterns for background and recurring work.
- Justin Higginbotham, *Principles of Web API Design* (Addison-Wesley, 2021): resource-modeling principles applicable to a job definition and its run records.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): standard-method and long-running-operation patterns behind the run and operation split.
- [RFC 9110 §15.3.3: 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110#section-15.3.3): the status code a `POST .../runs` still returns, since starting a run is not the same moment as finishing one.

