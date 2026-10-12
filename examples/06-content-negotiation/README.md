# Ch6 — Content negotiation & status codes

Extends the [Ch4 contract-first anchor](../04-contract-first/) — same
shipping/cargo Booking resource, same `contracts/openapi/shipping-api.yaml` +
`contracts/schemas/shipping.schema.json`, same `verify.sh` harness via
`examples/_lib/`. This chapter adds explicit `Accept`/`Content-Type`
negotiation (`406 Not Acceptable` / `415 Unsupported Media Type`) and a full
status-code discipline pass across the booking operations.

Quarkus (`quarkus/`) and FastAPI (`python/`) run on **different ports here
than every other example** — 8086 and 8006, not 8080/8000 — so this stack
can run alongside ch04/ch05 without a port collision.

## Run it

```bash
cd examples/06-content-negotiation
./verify.sh
```

Brings both services up with `docker compose`, waits for health, drives the
negotiation + status-code assertions against `localhost:8086` (Quarkus) and
`localhost:8006` (FastAPI), schema-validates every response, and tears the
stack down again. Prints `PASS` only if every assertion holds for **both**
stacks.

```bash
docker compose --profile observability up --build   # + Grafana LGTM, opt-in
```

To poke at it by hand:

```bash
docker compose up --build

# 201 + Location, Booking body
curl -is -X POST localhost:8086/bookings \
  -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
       "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":1000}}]}'

# 415 — wrong Content-Type on a write
curl -is -X POST localhost:8086/bookings -H 'Content-Type: text/plain' -d 'nope'

# 406 — Accept the server can't satisfy
curl -is localhost:8086/bookings/bkg_whatever -H 'Accept: application/xml'

docker compose down -v
```

## Content negotiation: Accept and Content-Type

Every endpoint that returns a body produces exactly `application/json`
(success) or `application/problem+json` (errors) — never a wildcard — and
every endpoint that accepts a body consumes exactly `application/json` (or
`application/merge-patch+json` on `PATCH`, unchanged from Ch4/Ch5). That
narrow, explicit declaration is what makes `406`/`415` meaningful: they fire
exactly when a client asks for, or sends, something this API was never going
to produce or accept in the first place.

| Header               | Client sends                      | Server behavior |
|-----------------------|------------------------------------|------------------|
| `Accept`              | `application/json`, `*/*`, or absent | 200/201/204, body in the requested/default shape |
| `Accept`              | `application/xml` (or any type neither `application/json` nor `application/problem+json` can satisfy) | **406 Not Acceptable**, `Problem` body |
| `Content-Type` (write) | `application/json`                | request accepted, body parsed and validated |
| `Content-Type` (write) | `text/plain` (or anything else the endpoint doesn't declare) | **415 Unsupported Media Type**, `Problem` body |

**Quarkus gets 406/415 for free.** Every resource method's `@Produces` lists
`{application/json, application/problem+json}` and every write method's
`@Consumes` lists `application/json` (or `application/merge-patch+json` for
`PATCH`) — never a wildcard. When a request's `Accept`/`Content-Type` can't
be satisfied by those declarations, RESTEasy Reactive raises
`NotAcceptableException` / `NotSupportedException` itself, per the JAX-RS
2.1 §3.8 content-negotiation algorithm, before `BookingResource`'s code ever
runs. `ProblemMappers.java` only has to turn those two exceptions into a
schema-conforming `Problem` body — the negotiation logic itself needed no
new code, just the right annotations.

**FastAPI does none of this automatically.** A pydantic body parameter is
parsed as JSON regardless of the request's `Content-Type` header, and
nothing in Starlette/FastAPI ever inspects `Accept`. `app/main.py`
implements both checks by hand — `_check_accept()` and
`_check_content_type()` — called explicitly at the top of every handler that
needs them. This is the chapter's clearest "same contract, different cost on
each stack" lesson: identical observable behavior, one line of annotation on
one side, a hand-rolled guard function on the other.

## Status-code discipline across the booking operations

| Method | Path                         | Status | Meaning |
|--------|------------------------------|:------:|---------|
| POST   | `/bookings`                  | 201    | Created; `Location: /bookings/{id}`, body = `Booking` |
| POST   | `/bookings`                  | 400    | Malformed/invalid request body, `Problem` |
| POST   | `/bookings`                  | 415    | Unsupported `Content-Type`, `Problem` |
| GET    | `/bookings`                  | 200    | `BookingCollection` |
| GET    | `/bookings`                  | 406    | Unsatisfiable `Accept`, `Problem` |
| GET    | `/bookings/{id}`             | 200    | `Booking` |
| GET    | `/bookings/{id}`             | 404    | No such booking, `Problem` |
| GET    | `/bookings/{id}`             | 406    | Unsatisfiable `Accept`, `Problem` |
| PUT    | `/bookings/{id}`             | 200    | Full replace (idempotent — see Ch5), `Booking` |
| PUT    | `/bookings/{id}`             | 404    | No such booking, `Problem` |
| PUT    | `/bookings/{id}`             | 415    | Unsupported `Content-Type`, `Problem` |
| DELETE | `/bookings/{id}`             | 204    | No body |
| DELETE | `/bookings/{id}`             | 404    | No such booking, `Problem` |
| POST   | `/bookings/{id}/confirm`     | 200    | `PENDING` → `CONFIRMED`, `Booking` |
| POST   | `/bookings/{id}/confirm`     | 404    | No such booking, `Problem` |
| POST   | `/bookings/{id}/confirm`     | 409    | Not in `PENDING` (already confirmed/cancelled/etc.), `Problem` |

Every error response is `application/problem+json` with a schema-conforming
`Problem` body (`#/$defs/Problem`) — never a bare string, an empty body, or
a framework's default HTML/plaintext error page.

## Why `confirm` is the 409 path

`409 Conflict` means the request is well-formed and the target resource
exists, but the resource's *current state* makes the operation impossible —
distinct from `400` (the request itself is bad) and `404` (there's no
resource to act on). Confirming a booking (`PENDING` → `CONFIRMED`) is a
state-machine transition valid from exactly one starting state; confirming a
booking that's already `CONFIRMED`, `CANCELLED`, `IN_TRANSIT`, or
`DELIVERED` is a conflict with that booking's current state, not a bad
request. `verify.sh` drives this directly: confirm a fresh `PENDING`
booking (200), confirm the SAME booking again (409 — it's `CONFIRMED` now).

## The drift probe

To see `verify.sh` actually catch a negotiation regression — not just a
response that's wrong in some other way — introduce one of these edits and
re-run `./verify.sh`:

**Break 406 — make the server accept everything.**

In `quarkus/.../BookingResource.java`, change `getBooking`'s `@Produces` back
to a single type:

```java
@Produces(MediaType.APPLICATION_JSON) // BUG: drops application/problem+json from the list
```

This alone doesn't break the 406 test (JAX-RS still rejects `Accept:
application/xml`). To actually force a 200 where a 406 is expected — the
failure this probe is meant to demonstrate — comment out the
`_check_accept(request)` guard at the top of Python's `get_booking`:

```python
def get_booking(booking_id: str, request: Request) -> JSONResponse:
    # if (problem := _check_accept(request)) is not None:   # BUG: negotiation disabled
    #     return problem
    booking = store.get(booking_id)
    ...
```

Re-run `./verify.sh`. It fails immediately:

```
lib.sh: FAIL — python GET /bookings/{id} (Accept: application/xml): expected HTTP 406, got 200
```

Revert the edit and re-run — back to `PASS` for both stacks. The same
round trip works on the Quarkus side by deleting the `NotAcceptableException`
case from `ProblemMappers.java` and widening `getBooking`'s `@Produces` to
`MediaType.WILDCARD` — more invasive on that stack precisely because 406
there is a property of the annotations, not a line of imperative code.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/06-content-negotiation.{svg,excalidraw}`) show the
negotiation flow: a request's `Accept`/`Content-Type` headers checked against
what each endpoint can produce/consume, and the `406`/`415` branch back to a
`Problem` response when they don't match.
