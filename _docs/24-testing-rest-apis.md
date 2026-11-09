---
title: "Testing REST APIs"
order: 24
part: "Testing"
description: "A test pyramid for a REST API: contract tests against the shared schema, in-process integration tests in both stacks, Newman end-to-end checks and a bounded load layer, and which belong in CI."
duration: "26 min"
---

## Learning objectives

By the end of this chapter you can:

- Layer a REST API's tests into contract, integration, end-to-end and bounded-load tiers, and say what each tier proves that the others can't.
- Validate a live response against a shared JSON Schema (`$defs`) as the oracle instead of hand-written assertions.
- Write in-process integration tests with `@QuarkusTest` and RestAssured, and with FastAPI's `TestClient`, that assert on behavior a contract check can't reach.
- Run a Postman collection with Newman against two independently deployed stacks to show both honor one contract.
- Tell a bounded correctness-under-repetition check from a latency benchmark, and decide which tiers run in CI.

## Why this matters

A response is correct only against something. For a REST API that something is the schema it promised to serve, and the tests that check it come in four tiers with different costs: a schema check on a live response, an in-process test of the application's logic, a client driving the deployed stacks over the network, and a short repetition run. Which of them to write, in what order, and which to run on every push is a cost decision.

The booking resource here is trimmed to `POST /bookings` and `GET /bookings/{id}`, with one runnable instance of each tier in both stacks.

## Four tiers for a REST API

The classic test pyramid puts many fast unit tests at the bottom and a thin sliver of end-to-end tests at the top. A REST API adds a contract tier underneath everything, because correctness is measured against a document.

| Tier | Checks | Cost | Where it runs |
|---|---|---|---|
| Contract | A live response matches the shared schema | An HTTP call and a schema validation | CI |
| Integration | The logic behind the response is right | A JVM or ASGI app in-process | Developer loop, build time |
| End-to-end | The deployed stacks answer correctly on the wire | Containers, a Node-based runner | CI |
| Bounded load | Thirty repetitions of one request stay correct | Seconds | CI |

Cost rises and confidence shifts going up: from "the shape is right" to "the behavior is right" to "the deployed system is right" to "it holds up under repetition." No tier replaces another. A contract check catches a shape regression that hand-written assertions never thought to cover, and an integration test catches a wrong value that a structural check can't see.

{% include excalidraw.html file="24-testing-rest-apis" alt="A test pyramid for a REST API with contract tests validating live responses against the shared JSON Schema at the base, in-process @QuarkusTest and pytest integration tests above that running locally and at build time, a Newman end-to-end layer running the same Postman collection against both live stacks in CI, and a thin bounded load layer on top running the same collection thirty times and asserting success and schema conformance rather than latency." caption="Figure 24.1: The test pyramid for a REST API: contract, integration, end-to-end and bounded load tiers, split by what runs in CI and what runs locally." %}

## Contract tests: the schema as the oracle

A contract test has no opinion about what "correct" means. It defers to `contracts/schemas/shipping.schema.json`, the one place a field's shape is decided. Every response body from a create, a read and a 404 goes through a validator that enforces the full strictness of the `$defs` entry: `additionalProperties: false`, every `required` field present, every pattern matched. A booking missing `createdAt`, or carrying a field nobody declared, fails regardless of its status code.

The validator is checked against known-good and known-bad fixtures before it sees a live response. A gate nobody has shown can reject a bad shape may be passing everything.

The same idea covers events. A message on `shipping.bookings.lifecycle` validates against `#/$defs/BookingEvent` in the same file, and its CloudEvents envelope against the required context attributes: `specversion`, `id`, `source`, `type`, `time`, `datacontenttype`. The two differ in what they point at, a synchronous response or an asynchronous message, not in the question they answer.

The Postman collection adds a looser layer: inline `pm.response.to.have.jsonSchema(...)` fragments scoped to each request. The `Booking` fragment requires `id`, `status`, `origin`, `destination`, `cargo` and `createdAt` plus a few `pattern` and `enum` constraints; the `Problem` fragment requires `title` and `status`. They drop `additionalProperties: false` and full field coverage, because their job is to make the collection readable cold, without cross-referencing the schema file, while the strict check proves the contract holds.

## Integration tests in both stacks

Integration tests close the gap a schema check leaves. `@QuarkusTest` boots the full application (CDI, JAX-RS routing, Jackson) in the JVM and drives it with RestAssured. FastAPI's `TestClient` runs requests against the ASGI app object with an `httpx`-backed client: no uvicorn, no port, no container.

They assert on values: the quote for a known cargo weight is exactly `"3001.25"`, a missing booking returns a `Problem` titled `"Booking not found"`, and a request without `cargo` is rejected before a booking exists.

{% include codetabs.html langs="Quarkus|Python" %}

```java
@Test
void createBooking_returns201WithLocationAndBookingBody() {
    given()
            .contentType("application/json")
            .body(VALID_BOOKING)
            .when().post("/bookings")
            .then()
            .statusCode(201)
            .header("Location", matchesPattern("^/bookings/bkg_[0-9A-HJKMNP-TV-Z]{26}$"))
            .body("id", matchesPattern("^bkg_[0-9A-HJKMNP-TV-Z]{26}$"))
            .body("status", equalTo("PENDING"))
            .body("quote.currency", equalTo("USD"))
            .body("quote.amount", equalTo("3001.25"));
}
```

```python
def test_create_booking_returns_201_with_location_and_booking_body(client):
    resp = client.post("/bookings", json=VALID_BOOKING)

    assert resp.status_code == 201
    assert BOOKING_ID_RE.match(resp.json()["id"])
    assert resp.headers["location"] == f"/bookings/{resp.json()['id']}"
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["quote"] == {"currency": "USD", "amount": "3001.25"}
```

These tests stay out of the CI gate. Booting a JVM and the Quarkus test harness on every matrix leg makes the fast path heavier for a layer already proven locally. `mvn test` and `uv run pytest` are quick on a developer machine, so they run in the inner loop and at build time. CI is for the live, deployed, cross-stack assertions nothing else can make.

## End-to-end with Newman

A Postman collection, adapted from the Newman harness in Cloud Native Design Patterns, drives the deployed stacks over the network. Its `Functional` folder has four requests: create a booking and check `201`, `Location` and schema; fetch it and check `200`; submit a booking without `cargo` and check `400` with a `Problem` body; fetch a missing id and check `404` with a `Problem` body.

The same unmodified collection runs against the Quarkus container on port 8103 and the FastAPI container on port 8023, with zero failed assertions required on each. That shows the contract constrains both implementations, not just one that happened to pass. The run parses Newman's summary row instead of trusting the reporter's exit framing, so a failed count other than `0` fails the run.

This tier proves what in-process tests can't: real routing, serialization and error handling over the wire, including negative cases.

## Load testing: bounded, not benchmark

The `Load` folder is one `POST /bookings`, run thirty times against the Quarkus stack with `newman -n 30`. Every iteration must return `201` with a schema-conforming body. No latency, percentile or throughput is asserted: a gate on "p95 under 200 ms" fails on a slow shared runner with nothing wrong in the code, and teaches a team to re-run CI until it's green. Success across repetition still catches a counter that corrupts under concurrent writes or a connection pool that exhausts on the fifth call, without asking CI timing to be reproducible.

Thirty iterations is not capacity planning. A team that needs sustained concurrency, ramping rates and real percentiles uses k6, Gatling or Locust on its own schedule and environment.

## Deciding what to build

Build as much of the pyramid as the cost of being wrong justifies.

| Tier | Build it when | Run it |
|---|---|---|
| Contract | A shared schema exists, nearly always | CI |
| Integration | Logic exists beyond passing a request to a datastore: a quote formula, a state rule, error shaping | Build time and the developer loop |
| End-to-end | More than one deployable must agree on one contract: two stacks, a second team, a public client | CI |
| Bounded load | You want a repetition check | CI, as correctness only, never a latency gate |

A single-implementation API can often get by on contract and integration tests alone.

> **🤖 Explore with your agent**
>
> "In examples/24-testing, add `GET /bookings/{id}` negative cases to both stacks: a malformed id should return 400 with a `Problem` body that validates against `#/$defs/Problem` in contracts/schemas/shipping.schema.json. Put the logic assertion in BookingResourceTest.java and tests/test_bookings.py, add the request to the Functional folder of collections/shipping.postman_collection.json, and keep both tests out of verify.sh."
>
> Check: `mvn test` and `uv run pytest` pass, then `./verify.sh` ends in `PASS` with zero failed Newman assertions on both stacks.

## Build, run, observe

```bash
cd examples/24-testing && ./verify.sh
```

The script brings up both stacks with `docker compose`, validates create, read and 404 responses against the shared schema, runs the Newman `Functional` folder against both, and runs the thirty-iteration load check against Quarkus. It ends in `PASS`. Quarkus listens on 8103 and FastAPI on 8023.

- In `python/app/quote.py`, return `amount` as a number instead of a quantized string: pydantic's `Money.amount: str` rejects it, the FastAPI stack answers `500`, and the live check fails with `expected HTTP 201, got 500`.
- Change `_RATE_PER_KG` in `python/app/quote.py`: `uv run pytest` fails on the exact `3001.25` quote, while the schema check, which sees only a string matching the pattern, still passes.

## For deeper coverage

- Cloud Native Design Patterns, "Appendix O: Newman": the harness this collection is adapted from.
- [Postman Learning Center: Newman command-line integration](https://learning.postman.com/docs/collections/using-newman-cli/command-line-integration-with-newman/): the official Newman CLI reference.
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): contract-driven validation patterns behind the schema-as-oracle approach.
- Jakub Gough, Daniel Bryant & Matthew Auburn, *Mastering API Architecture* (O'Reilly, 2022): where testing fits across an API's delivery lifecycle.
