# Ch11 — Rerunnable jobs

Extends the [Ch4 contract-first anchor](../04-contract-first/) with a
server-owned, **rerunnable** job: `manifest-reconcile`, which re-checks
manifests against bookings on a schedule the server itself drives.

- `contracts/openapi/shipping-api.yaml` / `contracts/schemas/shipping.schema.json`
  — the `Booking`/`Cargo` resource model (unchanged from Ch4), plus
  `Operation`/`OperationStatus` (introduced in Ch10), reused here as the
  shape of a job **run record**.
- The job **definition** itself (`id`/`enabled`/`intervalSeconds`/
  `createdAt`/`updatedAt`) is a small local shape — documented below, not in
  the shared schema, since it has no shipping-domain meaning.

Quarkus (`quarkus/`, host port **8091**) and FastAPI (`python/`, host port
**8011**) independently implement the identical protocol against an
in-memory store. These ports are deliberately unique across the repo's
examples so this stack can run alongside any other chapter's without a
clash.

## Run it

```bash
cd examples/11-rerunnable-jobs
./verify.sh
```

This brings both services up with `docker compose`, waits for health,
drives the configure -> run-now -> poll -> list lifecycle against
`localhost:8091` (Quarkus) and `localhost:8011` (FastAPI), confirms each
stack's OWN scheduler produces additional runs with no further client
action, schema-validates every run-record response, and tears the stack
down again. Prints `PASS` only if every assertion holds for **both**
stacks.

To poke at it by hand instead:

```bash
docker compose up --build

# 1. Configure the schedule (server-owned; the client sets WHEN, not what
#    runs each execution). 201 the first time, 200 on every later PUT.
curl -si -X PUT localhost:8091/jobs/manifest-reconcile \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true,"intervalSeconds":2}'

# 2. Read the schedule back.
curl -s localhost:8091/jobs/manifest-reconcile | jq .

# 3. Trigger an on-demand run ("run now") — independent of the scheduler.
curl -si -X POST localhost:8091/jobs/manifest-reconcile/runs

# 4. Poll the run until it SUCCEEDS.
curl -s localhost:8091/jobs/manifest-reconcile/runs/<runId> | jq .

# 5. List every run the job has produced — both "run now" calls AND the
#    scheduler's own automatic runs show up here, in the same shape.
curl -s localhost:8091/jobs/manifest-reconcile/runs | jq .

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## The configure-vs-execute split

This chapter's point is that a rerunnable job is really **two** resources
with two different owners, not one:

| Resource | Who owns it | What it represents | Endpoints |
|----------|-------------|---------------------|-----------|
| **Job definition** (schedule) | Server, configured by the client | WHEN the job should run, and whether it's enabled at all | `PUT`/`GET /jobs/manifest-reconcile` |
| **Run** (execution) | Server, entirely | ONE execution of the job, with its own lifecycle | `POST`/`GET /jobs/manifest-reconcile/runs[/{runId}]` |

A client **configures** the job — it never drives an individual execution.
Executions happen because:

1. **The server's own scheduler** fires a run automatically, on the
   interval the client configured, for as long as the job stays `enabled`.
2. **An explicit "run now"** (`POST /jobs/manifest-reconcile/runs`) lets a
   client trigger ONE additional execution on demand — useful for "I don't
   want to wait for the next scheduled tick," not a way to replace the
   schedule.

Both paths produce the exact same kind of resource: a run record that goes
through `PENDING` -> `RUNNING` -> `SUCCEEDED`/`FAILED`, reusing the
`Operation`/`OperationStatus` shape from Ch10's shared contract rather than
inventing a parallel "JobRun" type — a rerunnable job's single execution
*is* a long-running operation, just one the server itself may also start.

```
Client                 Job definition            Scheduler            Run record
  |-- PUT (schedule) ->|                           |                     |
  |<-- 201/200 --------|                           |                     |
  |                     |-- every intervalSeconds ->|                     |
  |                     |                           |-- new run -------->|
  |-- POST .../runs --->|                           |                     |
  |<-- 202 + Location --|-------------------------- (ad hoc) ----------->|
  |-- GET .../runs/{id}------------------------------------------------->|
  |<-- 200 Operation(PENDING/RUNNING) ------------------------------------|
  |         ... poll ...                                        (~0.3s work)
  |-- GET .../runs/{id}------------------------------------------------->|
  |<-- 200 Operation(SUCCEEDED) -------------------------------------------|
```

## Scheduler per stack

Both stacks implement the SAME pattern as Ch10's background worker, just
with a periodic re-fire instead of a one-shot delay, and the period is
re-armed every time the client reconfigures the schedule — so "the client
configures the schedule" is literally true, not just a figure of speech:

- **Quarkus** (`JobStore.java`): a daemon-thread `ScheduledExecutorService`
  (the same primitive Ch10 uses for its one-shot confirmation delay).
  `configure()` cancels the current `ScheduledFuture` and re-arms
  `scheduleAtFixedRate(this::tick, intervalSeconds, intervalSeconds,
  SECONDS)` at the newly configured interval.
- **FastAPI** (`app/jobs.py`): `asyncio.create_task` running an
  `await asyncio.sleep(interval_seconds)` loop (the same primitive Ch10
  uses for its one-shot confirmation delay). `configure()` cancels the
  current ticker task and starts a fresh one at the new interval.

Both keep the actual "reconcile" work deliberately trivial and fast (a scan
of the in-memory `BookingStore`/`app.store`, counting `PENDING` bookings) —
the point of this chapter is the rerunnable-job *protocol*, not a real
manifest-reconciliation engine. `verify.sh` configures `intervalSeconds=2`
so the scheduler's own behavior is observable within a few seconds, keeping
CI bounded.

## Endpoints implemented (identically, in both stacks)

| Method | Path                                      | Success | Notes |
|--------|-------------------------------------------|---------|-------|
| PUT    | `/jobs/manifest-reconcile`                | 201/200/400 | 201 first configure, 200 on later re-configure |
| GET    | `/jobs/manifest-reconcile`                | 200/404 | 404 until the job has been configured at least once |
| POST   | `/jobs/manifest-reconcile/runs`           | 202/404 | `Location: .../runs/{runId}`, body = run record (`Operation` shape) |
| GET    | `/jobs/manifest-reconcile/runs`           | 200/404 | newest-first array of run records |
| GET    | `/jobs/manifest-reconcile/runs/{runId}`   | 200/404 | one run record |
| POST   | `/bookings`, `/bookings/{id}/cargo`, etc. | — | from Ch4 — `BookingStore` is what the reconcile run's trivial work scans |

Errors are always `Problem` (`application/problem+json`): 404 for an
unconfigured job or an unknown run, 400 for an invalid job definition
(missing `enabled`/`intervalSeconds`, or `intervalSeconds < 1`). `_links`
(HATEOAS) is intentionally omitted everywhere — that's Ch12.

## The drift probe

`verify.sh` is only worth running if it actually rejects a response that
drifts from the protocol. To see it happen, introduce one of these edits in
either stack and re-run `./verify.sh`.

**Option A — drop the schedule from the job definition.**

In `python/app/jobs.py`'s `_JobDefinitionRecord.to_job_definition`, hardcode
`intervalSeconds=0` instead of `self.interval_seconds`:

```python
intervalSeconds=0,  # BUG: schedule lost
```

(Or in `quarkus/.../JobStore.java`'s `JobDefinitionRecord.toJobDefinition`,
hardcode `0` instead of `intervalSeconds`.)

Re-run `./verify.sh`. It fails immediately after the first `PUT`:

```
lib.sh: FAIL — python job definition: expected intervalSeconds=2, got 0
```

**Option B — a run-now that never reaches SUCCEEDED.**

In `python/app/jobs.py`'s `_execute_run`, comment out the
`record.status = OperationStatus.SUCCEEDED` line (leaving the run stuck
`RUNNING` forever). Re-run `./verify.sh` — it polls for
`POLL_TIMEOUT_SECONDS` (10s) and then fails with:

```
lib.sh: FAIL — python run op_... never reached SUCCEEDED within 10s
```

(Or in `quarkus/.../JobStore.java`'s `executeRun`, comment out
`record.status.set(OperationStatus.SUCCEEDED);`.)

Revert either edit and re-run `./verify.sh` — it goes back to `PASS` for
both stacks. That round trip (break it, watch the gate catch it, fix it,
watch the gate go green again) is the thing worth internalizing: the
configure-vs-execute split and the job's own scheduler autonomy are both
enforced mechanically — not just "does the server respond to a PUT."

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/11-job-lifecycle.{svg,excalidraw}`) show the admin
configuring the schedule, the scheduler firing runs on that interval, a
caller triggering an additional ad hoc run, and a run's
PENDING -> RUNNING -> SUCCEEDED/FAILED lifecycle.
