# Ch7 — Partial updates: JSON Merge Patch vs JSON Patch

Extends the [Ch4 contract-first anchor](../04-contract-first/)'s Booking +
Cargo resource model with **both** partial-update media types on
`PATCH /bookings/{id}`, implemented identically on Quarkus (`quarkus/`,
port **8087**) and FastAPI (`python/`, port **8007**):

- `application/merge-patch+json` — **RFC 7396 JSON Merge Patch** (kept from
  Ch4's thin version, now with the null-removes-a-field case exercised).
- `application/json-patch+json` — **RFC 6902 JSON Patch** (new this
  chapter): an ordered array of operations addressed by JSON Pointer
  (RFC 6901).

Both are hand-rolled against each stack's native JSON tree
(`JsonNode`/Jackson on Quarkus, plain `dict`/`list` on FastAPI) — no extra
dependency, same choice Ch4 made for merge patch. `verify.sh` drives create
→ merge-patch (change a field) → merge-patch (null removes a field) →
json-patch (replace) → json-patch (failing `test` → 409/422) → unsupported
Content-Type (→ 415) against **both** stacks and schema-validates every
response body.

## Run it

```bash
cd examples/07-partial-updates
./verify.sh
```

This brings both services up with `docker compose`, waits for health,
drives the sequence above against `localhost:8087` (Quarkus) and
`localhost:8007` (FastAPI), schema-validates every response, and tears the
stack down again. Prints `PASS` only if every assertion holds for **both**
stacks.

To poke at it by hand instead:

```bash
docker compose up --build

# create a booking
curl -s -X POST localhost:8087/bookings \
  -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC"},"destination":{"unLocode":"NLRTM"},
       "cargo":[{"description":"Pallet","type":"GENERAL","dimensions":{"weightKg":1000}}],
       "requestedPickup":"2026-02-01"}' | jq .

# merge patch: change requestedPickup, leave everything else alone
curl -s -X PATCH localhost:8087/bookings/<id> \
  -H 'Content-Type: application/merge-patch+json' \
  -d '{"requestedPickup":"2026-03-01"}' | jq .

# merge patch: null REMOVES the field
curl -s -X PATCH localhost:8087/bookings/<id> \
  -H 'Content-Type: application/merge-patch+json' \
  -d '{"requestedPickup":null}' | jq .

# json patch: replace a nested value by JSON Pointer
curl -s -X PATCH localhost:8087/bookings/<id> \
  -H 'Content-Type: application/json-patch+json' \
  -d '[{"op":"replace","path":"/cargo/0/description","value":"Re-palletized"}]' | jq .

docker compose down -v
```

The Grafana LGTM observability stack is opt-in and off by default:

```bash
docker compose --profile observability up --build
```

## JSON Merge Patch vs JSON Patch

Both are legitimate answers to "how does a client send a partial update",
but they solve different problems and have different failure shapes:

| | JSON Merge Patch (RFC 7396) | JSON Patch (RFC 6902) |
|---|---|---|
| Media type | `application/merge-patch+json` | `application/json-patch+json` |
| Body shape | A partial **object** that structurally resembles the target resource | An **array of operations**: `{op, path, value?, from?}` |
| Addressing | By object key, recursively (one level of object-shaped nesting merges; anything else — including every array — is wholesale-replaced) | By JSON Pointer (RFC 6901): `/cargo/0/description`, `/status`, ... |
| Deleting a field | Set it to JSON `null` | `{"op":"remove","path":"/..."}` |
| Modifying an array element | Not expressible — you must resend the WHOLE array | `replace`/`add`/`remove` at a specific index, or `move`/`copy` between positions |
| Preconditions | None — it's unconditional | `test`: assert a path's current value before applying the rest of the patch; a mismatch fails the WHOLE patch |
| Ambiguity | A patch body is just "the fields I want to change" — easy to write by hand, easy to read in a diff | More verbose, but unambiguous: every edit names its exact target, so two patches can never be confused with each other |
| Typical client | A form/UI sending "here's what changed" as a sparse object | A generated client, or any client that needs a precise edit against a possibly-concurrent resource (the `test` op is the cheapest form of optimistic concurrency control this chapter has) |

In short: reach for **merge patch** when the update is "a handful of
top-level fields changed" and the client naturally has a partial object to
send (most UI forms). Reach for **JSON Patch** when the update needs to
touch something inside an array, needs to delete-and-not-just-null a value
in a context where `null` is itself meaningful, or needs a `test`
precondition so the server rejects the whole patch if the resource moved
out from under the client between read and write.

### JSON Patch operations implemented

All six RFC 6902 §4 operations are implemented (`JsonPatch.java` /
`app/json_patch.py`), though `verify.sh` only exercises `replace` and the
failure path of `test` directly:

| op | Effect |
|----|--------|
| `add` | Insert `value` at `path` (object key, or array index / `-` to append) |
| `remove` | Delete the value at `path` |
| `replace` | Overwrite the existing value at `path` with `value` (the path must already exist) |
| `move` | `remove` from `from`, then `add` the removed value at `path` |
| `copy` | `add` a deep copy of the value at `from`, at `path` |
| `test` | Assert the value at `path` equals `value`; on mismatch, the ENTIRE patch fails (no partial application) — this chapter maps that to **409 Conflict** |

A malformed patch document (bad JSON Pointer, missing `value`, out-of-range
array index, an unknown `op`) maps to **422 Unprocessable Content** instead
— the request is addressable but can't be carried out, which is a
different failure mode than "your stated precondition didn't hold."

## Content-Type dispatch, and the 415 path

- **Quarkus**: two `@PATCH` methods share the same `@Path("/{id}")`, each
  declaring a different `@Consumes` (`application/merge-patch+json` /
  `application/json-patch+json`). RESTEasy Reactive dispatches on
  Content-Type the same way it already dispatches `@Produces` for Accept
  negotiation (Ch6); a Content-Type matching neither method —
  `application/json`, `text/plain`, or no body at all — never reaches
  either resource method. RESTEasy raises `NotSupportedException`, which
  `ProblemMappers` turns into a 415 `Problem`.
- **FastAPI**: Starlette's router is path-based only — it has no
  per-Content-Type dispatch the way JAX-RS does — so `patch_booking` reads
  the `Content-Type` header itself and dispatches by hand to
  `_patch_merge` / `_patch_json_patch`, falling through to an explicit 415
  `Problem` for anything else.

Either way, the **shape of the guarantee is identical**: a PATCH with a
Content-Type other than the two this chapter implements always comes back
415, with a `Problem` body, on both stacks.

## Server-assigned fields are still protected

Exactly as in Ch4's merge patch, `id` and `createdAt` are
readOnly in the schema and get forced back to their pre-patch values after
EITHER kind of patch is applied, regardless of what the client's merge
document or JSON Patch operations tried to do to them. `updatedAt` is
always re-stamped by the server on a successful patch.

## The drift probe

To see `verify.sh` catch a real regression, introduce one of these edits
and re-run `./verify.sh`:

**Option A — make JSON Patch silently ignore the `replace` op.**

In `python/app/json_patch.py`'s `apply_patch`, comment out the `replace`
branch's call to `_replace(...)` and just `continue` instead:

```python
elif op == "replace":
    continue  # BUG: silently drops the operation instead of applying it
```

(Or in `quarkus/.../JsonPatch.java`, change the `"replace"` case in
`apply()`'s switch to `doc = doc;` — same idea.)

Re-run `./verify.sh`. It fails at the json-patch replace assertion for that
stack:

```
lib.sh: FAIL — python json-patch replace did not apply (got cargo[0].description=Palletized electronics)
```

**Option B — make a failed `test` op return 200 instead of 409/422.**

In `python/app/main.py`'s `_patch_json_patch`, swallow `JsonPatchTestFailed`
instead of mapping it to a Problem:

```python
except JsonPatchTestFailed:
    pass  # BUG: treat a failed precondition as a no-op success
```

Re-run `./verify.sh`. It fails because the response comes back 200 (a
`Booking`, not a `Problem`) where the test expects 409 or 422:

```
lib.sh: FAIL — python json-patch failing test op: expected HTTP 409 or 422, got 200
```

Revert either edit and re-run `./verify.sh` — it goes back to `PASS` for
both stacks.

## Diagram

`architecture.svg` / `architecture.excalidraw` (copied from
`assets/diagrams/07-patch-vs-merge.{svg,excalidraw}`) contrast the merge
patch and JSON Patch request shapes against the same target resource.
