# Ch24 — Testing REST APIs

A REST API is only as trustworthy as the tests wrapped around it. This
chapter builds the **test pyramid** for the booking create/read surface
(the same shape as `examples/04-contract-first`, trimmed to just
`POST`/`GET` — the subject here is the testing layers, not the resource
model) and vendors/adapts the Newman/load harness from
`cloud-native-design-patterns/examples/28-newman` to drive it end to end
against **both** the Quarkus and FastAPI stacks.

```
        ▲  tiny
        │  ┌─────────────────────────────┐
        │  │ 4. Load (Newman, n=30)       │  bounded, deterministic
        │  ├─────────────────────────────┤
        │  │ 3. E2E API (Newman)          │  both stacks, 0 failures
        │  ├─────────────────────────────┤
        │  │ 2. Integration (@QuarkusTest │  real, local/build-time
        │  │    / pytest)                 │
        │  ├─────────────────────────────┤
        │  │ 1. Contract (validate_       │  live, both stacks
        │  │    response.py + schema      │
        │  │    assertions)               │
        │  └─────────────────────────────┘
        ▼  many
```

## The four layers

1. **Contract tests** — every live response from both stacks is validated
   against `contracts/schemas/shipping.schema.json`'s `$defs` using
   `examples/_lib/validate_response.py` (the same gate `examples/
   04-contract-first` uses). This is the strict check: `additionalProperties:
   false`, full required-field and pattern enforcement.
2. **Integration tests** — a real `@QuarkusTest` class
   (`quarkus/src/test/java/com/patterncatalyst/shipping/BookingResourceTest.java`)
   and a real `pytest` suite (`python/tests/test_bookings.py`), both
   exercising the booking create/read endpoints in-process (RestAssured
   against the booted Quarkus app; FastAPI's `TestClient` against the ASGI
   app directly — no network, no container). These are genuine,
   runnable test files, not stubs.
3. **End-to-end API tests** — `collections/shipping.postman_collection.json`,
   a Postman collection (vendored/adapted from CNDP's `28-newman` example)
   with a `Functional` folder: create → 201 + `Location` + schema, get →
   200 + schema, a negative create (missing `cargo`) → 400 + `Problem`
   shape, and a negative get (nonexistent id) → 404 + `Problem` shape.
   Run with Newman against **both** live stacks.
4. **Load test** — the same collection's `Load` folder (a single `POST
   /bookings`), run with `newman -n 30` against one stack. Tiny, bounded,
   and deterministic: it asserts every one of the 30 iterations returns
   `201` with a schema-conforming body — **never** an absolute latency
   number, so it stays fast and non-flaky in CI.

## What runs where

| Layer | Where | Why |
|---|---|---|
| Contract tests | `verify.sh` (CI) | Fast, no extra toolchain — reuses the shared venv `lib.sh` already builds. |
| `@QuarkusTest` | Local / `mvn test` only | Booting the JVM + Quarkus test harness per CI matrix leg is too heavy for this script's bounded, fast path. Demonstrated and runnable, not CI-gated. |
| `pytest` | Local / `uv run pytest` only | Symmetric with the Quarkus side: both integration layers are build-time/local, while `verify.sh`'s job is the live-container contract + Newman + load layers. |
| Newman functional | `verify.sh` (CI) | The E2E gate — 0 failures required on both stacks. |
| Newman load | `verify.sh` (CI) | Bounded (`n=30`), deterministic, asserts success/schema — not timing. |

## Run it

```bash
cd examples/24-testing
./verify.sh
```

This brings both services up with `docker compose`, waits for health, then
for **each** stack: drives a live contract-checked create → get →
nonexistent-get sequence, then runs the Newman `Functional` folder (0
failures required). It then runs the Newman `Load` folder 30 times against
the Quarkus stack and tears everything down. Prints `PASS` only if every
layer holds for both stacks.

To run the integration layers locally:

```bash
# @QuarkusTest (in-process, boots the full Quarkus app)
cd examples/24-testing/quarkus
mvn test

# pytest (in-process, FastAPI TestClient against the ASGI app)
cd examples/24-testing/python
uv sync
uv run pytest -v
```

To poke at the Newman collection by hand:

```bash
docker compose up --build

npx --yes newman@6 run collections/shipping.postman_collection.json \
  --folder Functional --env-var baseUrl=http://localhost:8103   # Quarkus
npx --yes newman@6 run collections/shipping.postman_collection.json \
  --folder Functional --env-var baseUrl=http://localhost:8023   # FastAPI

# Bounded load run, 30 iterations, against either stack:
npx --yes newman@6 run collections/shipping.postman_collection.json \
  --folder Load -n 30 --env-var baseUrl=http://localhost:8103

docker compose down -v
```

Ports are **unique** across the repo's examples: Quarkus on `8103`→8080,
FastAPI on `8023`→8000, compose project `ch24-testing`.

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## Ports

| Service | Host port | Container port |
|---|---|---|
| Quarkus  | 8103 | 8080 |
| FastAPI  | 8023 | 8000 |

## Endpoints implemented

Trimmed from `examples/04-contract-first` to just the create/read surface
this chapter's test pyramid exercises:

| Method | Path | Success | Notes |
|---|---|---|---|
| POST | `/bookings` | 201 | `Location: /bookings/{id}`, body = `Booking` |
| GET | `/bookings/{id}` | 200/404 | `Booking` or `Problem` |

Errors are always `Problem` (`application/problem+json`): 400 for an
invalid create request (e.g. missing `cargo`), 404 for a missing booking.
The quote formula (`quote.amount = sum(cargo[].dimensions.weightKg) * 2.50`,
formatted as a decimal string) is identical to Ch4 — see that chapter's
README for the full explanation of why `amount` must be a string, never a
JSON number.

## The drift probe

To see the contract gate actually reject a response — not just a response
that's wrong in some other way — introduce this edit and re-run
`./verify.sh`:

In `python/app/quote.py`, change:

```python
amount = f"{total_weight_kg * _RATE_PER_KG:.2f}"
```

to:

```python
amount = total_weight_kg * _RATE_PER_KG  # BUG: number, not string
```

Re-run `./verify.sh`. Pydantic's own `Money.amount: str` field rejects the
float at response-construction time, so the FastAPI stack now returns a
bare `500` instead of a schema-conforming `201` — and `verify.sh`'s Step 3
live contract check fails immediately:

```
lib.sh: FAIL — python POST /bookings: expected HTTP 201, got 500
```

Revert the edit and re-run — it goes back to `PASS`. (This repo's own
`validate_response.py`/pydantic strictness catches the bug even before a
response body reaches the schema validator or the Newman collection; the
equivalent bug in `examples/04-contract-first`, which uses a looser
dict-based Python response path, is a good side-by-side to compare against
if you want to see the schema validator itself catch a value that *does*
reach the wire.)

## Vendoring note

`collections/shipping.postman_collection.json` and the `verify.sh` Newman
invocation pattern (CLI reporter, `--timeout-request`, parsing the
`assertions` row of the summary table, `-n` for a bounded load run) are
adapted from `cloud-native-design-patterns/examples/28-newman`. The CNDP
version tests a standalone orders service against a single backend; this
version adapts the same mechanics to run the **same** collection against
**two** independently-implemented stacks sharing one contract, plus a
schema assertion (`pm.response.to.have.jsonSchema`) layered on top of the
stricter `validate_response.py` contract check already covered in Step 3.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/24-testing-rest-apis.{svg,excalidraw}`) show the test
pyramid and which layer runs against which live/in-process target.
