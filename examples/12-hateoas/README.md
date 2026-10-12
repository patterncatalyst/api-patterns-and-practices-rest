# Ch12 — HATEOAS

The response IS the state machine. This chapter extends the Ch4
contract-first Booking + Cargo resource model with state-dependent
`_links`: every `Booking` response carries exactly the relations that are
valid **from its current `status`** — not a static, always-the-same set of
links. The contract — not either codebase — is the source of truth:

- `contracts/openapi/shipping-api.yaml` — endpoints, status codes, headers.
- `contracts/schemas/shipping.schema.json` — `Booking._links` (`#/$defs/Links`,
  a map of relation name to `#/$defs/Link` = `{href, method, title}`).

Quarkus (`quarkus/`, port 8092) and FastAPI (`python/`, port 8012)
independently implement the identical state -> links mapping against an
in-memory store. `verify.sh` drives ONE booking through its entire lifecycle
(`PENDING -> CONFIRMED -> IN_TRANSIT -> DELIVERED`) and a second through
`PENDING -> CANCELLED`, schema-validating every response body AND asserting
the exact `_links` key set at each stop, against **both** stacks.

## Run it

```bash
cd examples/12-hateoas
./verify.sh
```

This brings both services up with `docker compose`, waits for health, drives
the lifecycle sequence against `localhost:8092` (Quarkus) and
`localhost:8012` (FastAPI), schema-validates every response, asserts the
`_links` set at each state, and tears the stack down again. Prints `PASS`
only if every assertion holds for **both** stacks.

To poke at it by hand instead:

```bash
docker compose up --build

# Create a booking (PENDING) — note confirm + cancel in _links.
curl -s -X POST localhost:8092/bookings \
  -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
       "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":1000}}]}' | jq .

# Follow the "confirm" link — note _links drops to just cancel.
curl -s -X POST localhost:8092/bookings/<id>/confirmation | jq ._links

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## The booking lifecycle (the finite-state machine behind HATEOAS)

```
PENDING ──confirm──▶ CONFIRMED ──load──▶ IN_TRANSIT ──deliver──▶ DELIVERED
   │                     │
   └──────cancel─────────┴──────────────▶ CANCELLED
```

`_links` exposes exactly the transitions valid from the CURRENT state — a
client follows links rather than hard-coding which verbs are legal from
which status:

| Status       | `_links` relations present | Endpoints a client can follow |
|--------------|-----------------------------|--------------------------------|
| `PENDING`    | `self`, `confirm`, `cancel` | `GET /bookings/{id}`, `POST /bookings/{id}/confirmation`, `DELETE /bookings/{id}` |
| `CONFIRMED`  | `self`, `cancel`            | `GET /bookings/{id}`, `DELETE /bookings/{id}` |
| `IN_TRANSIT` | `self`                      | `GET /bookings/{id}` |
| `DELIVERED`  | `self`                      | `GET /bookings/{id}` |
| `CANCELLED`  | `self`                      | `GET /bookings/{id}` |

Each link is `{href, method, title}` per `#/$defs/Link`, e.g.:

```json
"_links": {
  "self":    { "href": "/bookings/bkg_01H...", "method": "GET",    "title": "Get this booking" },
  "confirm": { "href": "/bookings/bkg_01H.../confirmation", "method": "POST", "title": "Confirm this booking" },
  "cancel":  { "href": "/bookings/bkg_01H...", "method": "DELETE", "title": "Cancel this booking" }
}
```

Links are computed FRESH from the booking's current status at response
time (`HateoasLinks.forBooking` / `app/hateoas.py::links_for_booking`) — the
stored `Booking` never carries `_links` itself, so a transition can never
leave a stale link behind.

## Driving transitions (this chapter's own, not the shared contract)

To let `verify.sh` observe every state's `_links` set without needing real
routing/capacity/carrier systems, this chapter adds three synchronous,
same-request-response transition endpoints, all returning `200` + the
updated `Booking`:

| Method | Path                            | Transition                  | 409 if booking is not... |
|--------|----------------------------------|------------------------------|---------------------------|
| POST   | `/bookings/{id}/confirmation`    | `PENDING` → `CONFIRMED`      | `PENDING`  |
| POST   | `/bookings/{id}/transit`         | `CONFIRMED` → `IN_TRANSIT`   | `CONFIRMED` |
| POST   | `/bookings/{id}/delivery`        | `IN_TRANSIT` → `DELIVERED`   | `IN_TRANSIT` |
| DELETE | `/bookings/{id}`                 | any non-terminal → `CANCELLED` | — (same soft-delete as Ch4) |

`POST /bookings/{id}/confirmation` has a wider meaning in the shared OpenAPI
contract — Ch10's `202 Accepted → poll Operation → 303` protocol for
confirmation that runs routing + capacity checks beyond one
request/response. This chapter deliberately keeps it a single synchronous
`200` instead: the point here is the state-dependent `_links` behavior, not
the async protocol (that's Ch10's job). `/transit` and `/delivery` aren't in
the shared contract at all — they're this chapter's own stand-ins for
"the carrier loaded the cargo" / "the cargo arrived," needed only to drive
the FSM through every `_links` shape.

## Endpoints implemented (identically, in both stacks)

| Method | Path                            | Success | Notes |
|--------|-----------------------------------|---------|-------|
| POST   | `/bookings`                       | 201     | `Location`, body = `Booking` (`PENDING`, `_links`: confirm+cancel) |
| GET    | `/bookings`                       | 200     | `BookingCollection`; each item carries its own `_links` |
| GET    | `/bookings/{id}`                  | 200/404 | `Booking` (with `_links`) or `Problem` |
| PUT    | `/bookings/{id}`                  | 200     | full replace, idempotent, preserves `status`/`_links` |
| PATCH  | `/bookings/{id}`                  | 200/415 | `application/merge-patch+json` |
| DELETE | `/bookings/{id}`                  | 204     | soft-delete: `status` → `CANCELLED` |
| GET    | `/bookings/{id}/cargo`            | 200     | array of `Cargo` |
| POST   | `/bookings/{id}/cargo`            | 201     | `Location`, body = `Cargo` |
| POST   | `/bookings/{id}/confirmation`     | 200/409 | `PENDING` → `CONFIRMED` |
| POST   | `/bookings/{id}/transit`          | 200/409 | `CONFIRMED` → `IN_TRANSIT` |
| POST   | `/bookings/{id}/delivery`         | 200/409 | `IN_TRANSIT` → `DELIVERED` |

Errors are always `Problem` (`application/problem+json`): 404 not found, 400
validation, 409 invalid state transition, 415 unsupported PATCH media type.

## The drift probe

The whole point of this chapter is that `verify.sh` actually catches a
response whose `_links` set doesn't match its state — not just a response
that's merely schema-valid in some other way. To see it happen, introduce
this edit and re-run `./verify.sh`:

**Always emit `confirm`, regardless of state.**

In `quarkus/.../HateoasLinks.java`, change `forBooking` to unconditionally
add `confirm`:

```java
static Map<String, Link> forBooking(String id, BookingStatus status) {
    Map<String, Link> links = new LinkedHashMap<>();
    links.put("self", new Link("/bookings/" + id, "GET", "Get this booking"));
    links.put("confirm", new Link("/bookings/" + id + "/confirmation", "POST", "Confirm this booking")); // BUG
    ...
```

(Or in `python/app/hateoas.py`, add the `confirm` link unconditionally at
the top of `links_for_booking` instead of only inside the `PENDING`
branch.)

Re-run `./verify.sh`. The response is still schema-valid (`confirm` is a
legitimate `#/$defs/Link`), so `validate_body Booking` still passes — but
the chapter's own state-assertion catches it the moment a `CONFIRMED`
booking's `_links` no longer matches its state:

```
lib.sh: FAIL — quarkus CONFIRMED (A): expected _links keys [cancel,self], got [cancel,confirm,self]
```

Revert the edit and re-run `./verify.sh` — it goes back to `PASS` for both
stacks. That's the thing worth internalizing: `_links` isn't just "any
object matching the `Link` shape" — it's a precise, mechanically-checked
claim about which state transitions are ACTUALLY legal right now, and a
drift between the two is a real, catchable bug, not just a style nit.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/12-hateoas-state-machine.{svg,excalidraw}`) show the
booking lifecycle finite-state machine and the `_links` set exposed at each
state.
