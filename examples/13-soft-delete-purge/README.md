# Ch13 — Soft deletion & GDPR purge

"Deleted" is not one thing. This chapter extends the Ch4 contract-first
Booking + Cargo resource model with two DIFFERENT kinds of delete:

- **Soft delete** (`DELETE /bookings/{id}`) — the everyday case. The
  booking's `status` flips to `CANCELLED`, an audit entry is recorded, and
  the booking is hidden from normal reads. The record itself stays in the
  store: referential integrity, retention, and an audit trail all depend on
  it still existing.
- **Purge** (`DELETE /bookings/{id}/purge`) — the GDPR "right to erasure"
  escape hatch. It overrides the retention above: the booking AND its audit
  trail are hard-deleted, with nothing left to find afterward, by anyone.

The contract — not either codebase — is the source of truth for the
`Booking`/`Problem` shapes:

- `contracts/openapi/shipping-api.yaml` — endpoints, status codes, headers.
- `contracts/schemas/shipping.schema.json` — `Booking`, `Problem`, ...

Quarkus (`quarkus/`, port 8093) and FastAPI (`python/`, port 8013)
independently implement the identical soft-delete/audit/purge model against
an in-memory store. `verify.sh` drives create → soft-delete → hide → audit
view → purge → erase against **both** stacks, schema-validating every
`Booking`/`Problem` response body along the way.

## Run it

```bash
cd examples/13-soft-delete-purge
./verify.sh
```

This brings both services up with `docker compose`, waits for health,
drives the sequence against `localhost:8093` (Quarkus) and `localhost:8013`
(FastAPI), schema-validates every response, and tears the stack down again.
Prints `PASS` only if every assertion holds for **both** stacks.

To poke at it by hand instead:

```bash
docker compose up --build

# Create a booking.
curl -s -X POST localhost:8093/bookings \
  -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
       "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":1000}}]}' | jq .

# Soft-delete it (optional ?reason=...).
curl -s -X DELETE "localhost:8093/bookings/<id>?reason=customer-requested"

# Gone to normal clients...
curl -s -o /dev/null -w '%{http_code}\n' localhost:8093/bookings/<id>          # 404

# ...but still addressable for audit/compliance.
curl -s -D - -o /dev/null "localhost:8093/bookings/<id>?includeDeleted=true"   # 200 + X-Audit-* headers

# GDPR erasure — hard-deletes the booking AND its audit trail.
curl -s -X DELETE localhost:8093/bookings/<id>/purge                          # 204

# Now even the audit view is gone.
curl -s -o /dev/null -w '%{http_code}\n' "localhost:8093/bookings/<id>?includeDeleted=true"  # 404

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default (neither
app ships telemetry yet):

```bash
docker compose --profile observability up --build
```

## Soft delete vs. purge

```
                    DELETE /bookings/{id}                DELETE /bookings/{id}/purge
                    (soft delete)                         (GDPR purge)
                           │                                       │
                           ▼                                       ▼
  ACTIVE booking ──▶ status=CANCELLED, audit recorded ──▶ booking + audit HARD-DELETED
  (store: present)        (store: present, hidden)              (store: gone)

  GET /bookings                 visible                           absent
  GET /bookings/{id}            404 (hidden)                      404 (not found)
  GET /bookings/{id}            200, Booking                      404 (nothing to
    ?includeDeleted=true        (status=CANCELLED) + audit          find — erased)
    (the audit/compliance view) headers
```

The load-bearing distinction: a soft-deleted booking is "gone" to a normal
client but **still exists** in the store — that's what makes the audit view
and referential integrity possible. A purged booking does not exist at all
— the GDPR "right to erasure" is modeled here as a rule that overrides
retention entirely, not just another visibility filter.

## The audit view

`GET /bookings/{id}?includeDeleted=true` is the audit/compliance escape
hatch from the default-hidden behavior above. It still returns a
schema-conforming `Booking` body (`validate_body Booking` passes on it) —
the audit trail itself (`deletedAt`, `reason`) rides along as two response
headers instead of extra body fields:

```
HTTP/1.1 200 OK
Content-Type: application/json
X-Audit-Deleted-At: 2026-02-01T12:00:00Z
X-Audit-Reason: customer-requested
```

This is a deliberate modeling choice, not an accident: the shared schema
declares `additionalProperties: false` on `Booking`
(`contracts/schemas/shipping.schema.json`), so stuffing `deletedAt`/`reason`
into the body would make every `Booking` response — soft-deleted or not —
fail contract validation the moment those fields showed up. Headers are a
local, documented extension that never has to satisfy the body schema. A
real system would more likely expose a dedicated `GET
/bookings/{id}/audit` sub-resource with its own schema instead; the header
approach here keeps this chapter's surface area small while still proving
the audit trail is real and still findable until purge erases it.

The headers are present only when the booking is actually `CANCELLED` and
an audit entry exists for it — `includeDeleted=true` on a still-ACTIVE
booking just returns the normal `Booking`, no headers, because there's
nothing to audit yet.

## Endpoints implemented (identically, in both stacks)

| Method | Path                              | Success | Notes |
|--------|-----------------------------------|---------|-------|
| POST   | `/bookings`                       | 201     | `Location`, body = `Booking` |
| GET    | `/bookings`                       | 200     | `BookingCollection`; soft-deleted bookings hidden |
| GET    | `/bookings/{id}`                  | 200/404 | `Booking` or `Problem`; soft-deleted → 404 |
| GET    | `/bookings/{id}?includeDeleted=true` | 200/404 | audit view: `Booking` + `X-Audit-Deleted-At`/`X-Audit-Reason` if cancelled; 404 only if purged or never existed |
| PUT    | `/bookings/{id}`                  | 200     | full replace, idempotent |
| PATCH  | `/bookings/{id}`                  | 200/415 | `application/merge-patch+json` |
| DELETE | `/bookings/{id}?reason=...`       | 204     | soft-delete: `status` → `CANCELLED`, audit entry recorded (`reason` optional, defaults to `"user-requested cancellation"`) |
| DELETE | `/bookings/{id}/purge`            | 204/404 | GDPR hard delete: booking + audit trail erased; 404 if already purged or never existed |
| GET    | `/bookings/{id}/cargo`            | 200     | array of `Cargo` |
| POST   | `/bookings/{id}/cargo`            | 201     | `Location`, body = `Cargo` |

Errors are always `Problem` (`application/problem+json`): 404 not found,
400 validation, 415 unsupported PATCH media type.

## The drift probe

The whole point of this chapter is that `verify.sh` actually catches a
soft-delete or purge implementation that leaks state it shouldn't — not
just a response that's merely schema-valid in some other way. To see it
happen, introduce one of these edits and re-run `./verify.sh`:

**Option A — stop hiding a soft-deleted booking from the default list.**

In `python/app/store.py`, change `list_visible` to stop filtering:

```python
def list_visible() -> list[Booking]:
    return list(_bookings.values())  # BUG: no longer excludes CANCELLED
```

(Or in `quarkus/.../BookingStore.java`, drop the `status() !=
BookingStatus.CANCELLED` check from `listVisible`.)

Re-run `./verify.sh`. The cancelled booking is still schema-valid (it's a
perfectly good `Booking`), but it now shows up where it shouldn't:

```
lib.sh: FAIL — quarkus soft-deleted booking bkg_01H... is still visible in the default GET /bookings list
```

**Option B — leave the audit trail behind after a purge.**

In `python/app/store.py`, change `purge` to stop clearing the audit map:

```python
def purge(booking_id: str) -> bool:
    existed = _bookings.pop(booking_id, None) is not None
    # BUG: forgot to pop from _audit_trail — the booking is gone but its
    # deletion reason/timestamp survives the "erasure".
    return existed
```

Because `get_audit` only gets consulted once the booking itself is found,
this particular slip is actually invisible to `GET
.../{id}?includeDeleted=true` (which 404s correctly, since `_bookings` no
longer has the id) — which is itself worth noticing: it demonstrates that
checking "the thing I show the client is gone" is NOT the same as proving
"I actually erased all the data," the exact gap real GDPR erasure bugs hide
in. `verify.sh` as written only exercises the client-visible audit path,
not internal storage; a real test suite for a purge feature should assert
against the store/database directly, not only through the API surface.

Revert the edit and re-run `./verify.sh` — it goes back to `PASS` for both
stacks.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/13-soft-delete-purge.{svg,excalidraw}`) show the
soft-delete → audit view → purge flow and which views see which state.
