---
title: "Partial updates: JSON Patch vs Merge Patch"
order: 7
part: "HTTP semantics done right"
description: "Two correct ways to change part of a resource — RFC 6902 JSON Patch and RFC 7396 JSON Merge Patch — their media types, their trade-offs, and when each one is the right tool."
duration: "28 min"
---

Chapter 5 established `PUT` as idempotent whole-resource replacement: send the full representation, the server stores exactly that, and sending it again changes nothing further. That guarantee is also `PUT`'s limitation. A client that wants to move a booking's `requestedPickup` date by one day has to re-send the entire `Booking` (origin, destination, every cargo item, the quote) just to change one field, and it has to read the current representation first or risk clobbering a concurrent change to a field it never meant to touch. `PATCH` exists for exactly this gap: a request that describes a *change*, not a replacement, against a body the client didn't have to reconstruct from scratch. The catch is that "describes a change" isn't one format: the IETF standardized two incompatible ways to do it, and a server has to pick, document, and dispatch on which one a given request is using.

This chapter builds both against the Chapter 4 contract-first `Booking` and `Cargo` model, on the same `PATCH /bookings/{id}` endpoint, distinguished by `Content-Type`. `application/merge-patch+json` carries **RFC 7396 JSON Merge Patch** — a partial object. `application/json-patch+json` carries **RFC 6902 JSON Patch** — an ordered array of operations. Both are legitimate, standardized, and in production use; neither subsumes the other. Picking between them is itself a design decision, and by the end of the chapter it slots into the Chapter 2 decision framework like every other one.

## JSON Merge Patch: a partial object, applied by RFC 7396's rules

RFC 7396 defines the simplest possible answer to "send me what changed": the request body is a JSON object that structurally resembles the target resource, containing only the keys the client wants to change. The server walks the patch object key by key. A key present with a non-null value overwrites (or recursively merges into, if both sides are objects) the corresponding key on the target. A key present with a JSON `null` value **deletes** that key from the target entirely — `null` is not a value you can set a field to under this RFC, it's the deletion instruction. A key absent from the patch is left alone on the target, no matter what.

Against a booking whose `requestedPickup` is `"2026-02-01"`, this merge patch:

```json
{ "requestedPickup": "2026-03-01" }
```

changes exactly that one field and leaves `origin`, `destination`, `cargo`, and everything else byte-identical to before. This one:

```json
{ "requestedPickup": null }
```

removes `requestedPickup` from the booking altogether — not "sets it to `null`," because RFC 7396 gives a merge patch no way to express "set to `null`" at all; `null` in the patch body is reserved exclusively for deletion. That's the first trade-off worth naming: if a field in your domain legitimately needs a `null` *value* (as opposed to "doesn't exist"), merge patch cannot carry that change. The booking domain sidesteps this by treating every nullable field as "present with a value, or absent" rather than "present and explicitly null," which is exactly why Chapter 4's schema models `requestedPickup` as optional instead of nullable.

The second trade-off is arrays. RFC 7396 merges objects recursively but treats every array as an opaque scalar — if a patch includes an array, the *entire* array on the target is replaced by the *entire* array in the patch, with no concept of inserting, removing, or changing one element in place. Wanting to fix a typo in `cargo[0].description` without touching `cargo[1]` and `cargo[2]` means resending the whole `cargo` array, reconstructed client-side, which is precisely the whole-resource-resend problem `PATCH` was supposed to solve. Merge patch is the right tool when the change really is "a handful of top-level or nested-object fields," and the wrong tool the moment an array element needs a scoped edit.

The server-side implementation is small enough that this chapter doesn't reach for a library on either stack — both already had a thin version from Chapter 4, and the only change here is exercising the null-deletes-a-field case. On the Quarkus side, `applyMergePatch` recurses over Jackson's `JsonNode` tree:

{% include codetabs.html langs="Quarkus|Python" %}

```java
private JsonNode applyMergePatch(JsonNode target, JsonNode patch) {
    if (patch == null || !patch.isObject()) {
        return patch;
    }
    ObjectNode result = (target != null && target.isObject()) ? target.deepCopy() : mapper.createObjectNode();
    Iterator<Map.Entry<String, JsonNode>> fields = patch.fields();
    while (fields.hasNext()) {
        Map.Entry<String, JsonNode> entry = fields.next();
        JsonNode value = entry.getValue();
        if (value.isNull()) {
            result.remove(entry.getKey());
        } else {
            JsonNode existingValue = result.get(entry.getKey());
            JsonNode mergedValue = applyMergePatch(existingValue, value);
            result.set(entry.getKey(), mergedValue);
        }
    }
    return result;
}
```

```python
def _merge_patch(target: Any, patch: Any) -> Any:
    """RFC 7396 JSON Merge Patch, applied to plain dict/JSON-ish values."""
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = _merge_patch(result.get(key), value)
    return result
```

Same recursion, same two rules — `null` deletes, an object value recurses, anything else overwrites — expressed against each stack's native tree type. Neither needs a dependency because RFC 7396's algorithm is that short; the complexity in this chapter lives entirely in the other format.

## JSON Patch: an operation sequence, addressed by JSON Pointer

RFC 6902 answers the same question completely differently: instead of describing the *result*, the client describes the *edits*. The request body is a JSON array, and each element is an operation object naming one of six verbs — `add`, `remove`, `replace`, `move`, `copy`, `test` — and a `path` written as an RFC 6901 JSON Pointer (`/cargo/0/description`, `/status`) that addresses exactly the value the operation acts on. Operations apply in array order, each one against the document as left by the operation before it.

| op | Effect |
|----|--------|
| `add` | Insert `value` at `path` (an object key, or an array index — or `-` to append) |
| `remove` | Delete the value at `path` |
| `replace` | Overwrite the existing value at `path` with `value` (the path must already exist) |
| `move` | `remove` from `from`, then `add` the removed value at `path` |
| `copy` | `add` a deep copy of the value at `from`, at `path` |
| `test` | Assert the value at `path` equals `value`; on mismatch, the ENTIRE patch fails with no partial application |

A `replace` on one cargo item's description, leaving every other cargo item and every other field on the booking untouched, looks like this:

```json
[
  { "op": "replace", "path": "/cargo/0/description", "value": "Re-palletized electronics" }
]
```

That's the array-element edit merge patch cannot express without resending the whole array — JSON Patch addresses `cargo[0]` directly and leaves `cargo[1..n]` alone by construction, because nothing in the patch document even names them. The same precision is what makes `test` useful as the cheapest form of optimistic concurrency control this chapter covers: a client that read a booking's `status` as `PENDING` can make the whole patch conditional on it still being `PENDING` at apply time —

```json
[
  { "op": "test", "path": "/status", "value": "CONFIRMED" },
  { "op": "replace", "path": "/cargo/0/description", "value": "Re-palletized electronics" }
]
```

— and if another request confirmed the booking in between the client's read and this `PATCH`, the `test` fails, the `replace` never runs, and the server reports the conflict instead of silently applying an edit the client computed against stale state. This chapter's example maps a failed `test` to **409 Conflict**: the request is syntactically fine and the resource exists, but the precondition the client staked the whole patch on doesn't hold against the resource's current state (the same meaning Chapter 6 gave `409` for a state-machine transition attempted from the wrong state). A different failure mode, such as a malformed JSON Pointer, a `replace` naming a path that doesn't exist, an out-of-range array index, or an operation object missing its required `value` or `from`, maps to **422 Unprocessable Content** instead, because that request can't be carried out at all, which is a different problem than "your stated precondition didn't hold."

Both stacks hand-roll RFC 6902 rather than reaching for a library, for the same reason merge patch stayed hand-rolled: the algorithm is self-contained once JSON Pointer tokenizing is right, and keeping it in-repo means the walkthrough below is the actual implementation, not a black box. The `replace` operation on each side:

{% include codetabs.html langs="Quarkus|Python" %}

```java
private static JsonNode replace(JsonNode target, List<String> tokens, JsonNode value) {
    if (tokens.isEmpty()) {
        return value;
    }
    JsonNode doc = target.deepCopy();
    JsonNode parent = navigateToParent(doc, tokens);
    String last = tokens.get(tokens.size() - 1);
    if (parent.isArray()) {
        ((ArrayNode) parent).set(readIndex(last, parent.size()), value);
    } else if (parent.isObject()) {
        if (!parent.has(last)) {
            throw new JsonPatchException("path segment not found: '" + last + "'");
        }
        ((ObjectNode) parent).set(last, value);
    } else {
        throw new JsonPatchException("cannot replace into a scalar");
    }
    return doc;
}
```

```python
def _replace(target: Any, tokens: list[str], value: Any) -> Any:
    if not tokens:
        return value
    doc = copy.deepcopy(target)
    parent = _navigate_to_parent(doc, tokens)
    last = tokens[-1]
    if isinstance(parent, list):
        parent[_read_index(last, len(parent))] = value
    elif isinstance(parent, dict):
        if last not in parent:
            raise JsonPatchError(f"path segment not found: {last!r}")
        parent[last] = value
    else:
        raise JsonPatchError("cannot replace into a scalar")
    return doc
```

`navigateToParent`/`_navigate_to_parent` walk every token but the last, so `replace` (and `add`/`remove`) land on the container that directly holds the target value rather than the value itself — the same JSON Pointer traversal both files reuse for `get`, with the one difference that a `replace` on an array index demands the index already exist (`readIndex`/`_read_index`, which rejects `-`), while `add` at that same position would accept `-` to mean "append." Both implementations deep-copy before mutating, so a `test` failure partway through a multi-operation patch leaves the original document provably untouched rather than half-applied — `apply`/`apply_patch` returns a brand-new tree at every step, never mutating its input.

## The media type is the dispatch key, and getting it wrong is a 415

Nothing in either patch body self-declares which RFC it follows — a bare JSON array could plausibly be either a merge-patch value (if the target field happened to be an array-typed resource) or a JSON Patch operation list. The `Content-Type` header is the only signal, which means the server has to dispatch on it correctly and reject anything else with **415 Unsupported Media Type**, the same code Chapter 6 used for a write body in a format the endpoint never declared it would parse.

Quarkus dispatches at the framework level: `BookingResource` declares two separate `@PATCH` methods on the identical `@Path("/{id}")`, distinguished only by `@Consumes`:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@PATCH
@Path("/{id}")
@Consumes("application/merge-patch+json")
@Produces(MediaType.APPLICATION_JSON)
public Response patchBooking(@PathParam("id") String id, JsonNode mergePatchDoc) {
    // RFC 7396 merge patch — see applyMergePatch() above
}

@PATCH
@Path("/{id}")
@Consumes("application/json-patch+json")
@Produces(MediaType.APPLICATION_JSON)
public Response patchBookingJsonPatch(@PathParam("id") String id, JsonNode patchOps) {
    // RFC 6902 JSON Patch — see JsonPatch.apply() above
}
```

```python
@app.patch("/bookings/{booking_id}")
async def patch_booking(booking_id: str, request: Request) -> JSONResponse:
    """Dispatch on Content-Type to one of this chapter's two partial-update
    media types. Starlette's routing is path-based only (unlike JAX-RS's
    `@Consumes`, which can route the SAME path to different methods by
    Content-Type), so the dispatch has to happen by hand, here."""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/merge-patch+json"):
        return await _patch_merge(booking_id, request)
    if content_type.startswith("application/json-patch+json"):
        return await _patch_json_patch(booking_id, request)
    return _problem(
        415,
        "Unsupported Media Type",
        "PATCH requires Content-Type: application/merge-patch+json or application/json-patch+json",
    )
```

RESTEasy Reactive runs the JAX-RS content-negotiation algorithm the same way it already did for Chapter 6's `@Consumes`/`@Produces` pairs: a request whose `Content-Type` matches neither declared value (plain `application/json`, `text/plain`, or no body at all) never reaches either resource method, and RESTEasy raises `NotSupportedException` on its own, which `ProblemMappers` turns into a 415 `Problem`. Starlette's router has no equivalent concept; it dispatches purely on path and HTTP verb, so FastAPI's single `@app.patch` route reads the header itself and branches by hand, falling through to an explicit 415 for anything that matches neither prefix. The observable behavior on the wire is identical either way: a client that sends the "obvious but wrong" guess of plain `application/json` to this `PATCH` endpoint gets 415 on both stacks, not a silent 200 that applied nothing or, worse, a body that got parsed as a different format than the client intended. `verify.sh` checks that guess explicitly, alongside `text/plain`, precisely because it's the mistake an unfamiliar client is most likely to make.

## Server-assigned fields survive either kind of patch

Chapter 4's merge patch already protected `id` and `createdAt` from being overwritten by a client-supplied body; this chapter extends the same guarantee to JSON Patch, because nothing about RFC 6902's `replace` or `remove` operations respects a schema's `readOnly` annotation — an operation targeting `/id` would apply exactly like any other if the server didn't intervene. Both stacks apply the patch against the full current representation, then unconditionally restamp the three fields a client must never control, regardless of what the patch document asked for:

```java
Booking result = new Booking(
        existing.id(),
        patched.status(),
        patched.origin(),
        patched.destination(),
        patched.cargo(),
        patched.quote(),
        patched.requestedPickup(),
        existing.createdAt(),
        nowUtc());
```

`existing.id()` and `existing.createdAt()` come from the pre-patch booking, never from whatever the merge document or operation array produced; `nowUtc()` always re-stamps `updatedAt` on a successful patch. The Python side does the identical thing by assignment after the fact — `merged["id"] = existing.id`, `merged["createdAt"] = existing.createdAt`, `merged["updatedAt"] = _now_utc()` — applied to both the merge-patch and the JSON-Patch result before either is validated and stored. A client that tries to `replace /id` or merge-patch `{"createdAt": "2020-01-01T00:00:00Z"}` gets a `200` back with its other edits applied and those two fields exactly as they were before the request, which is the server enforcing an invariant the request format itself has no way to express.

## Choosing between them

The two formats aren't competing solutions to the same problem; they're sized for different shapes of change. Reach for **merge patch** when the typical edit is "a handful of top-level or nested-object fields changed," the client naturally already has a sparse object to send — most UI forms work this way, serializing only the fields the user touched — and nothing in the domain needs to distinguish "set this field to `null`" from "remove this field." Reach for **JSON Patch** the moment any of three things is true: the edit needs to touch one element inside an array without resending the whole array, the domain has a field where `null` is a meaningful value rather than "absent," or the client needs a `test` precondition so a concurrent change to the resource between read and write fails the whole patch instead of applying over stale assumptions. A generated client, or any client mediating between two systems that can't coordinate on timing, leans JSON Patch by default for the last reason alone.

The two are not mutually exclusive on the same resource, either — this chapter's `PATCH /bookings/{id}` accepts both, distinguished by `Content-Type`, because different callers of the same API legitimately have different shapes of change to describe. A browser-based booking-edit form sends merge patch because it already has a sparse object from a diffed form state. A reconciliation job that needs to move one cargo item's description conditionally on the booking still being `PENDING` sends JSON Patch because nothing else expresses that precondition. Supporting both is more code than picking one, but it's the same amount of code whether you write it once in a chapter or discover the gap in production when a client needs the capability the simpler format doesn't have.

## Proof, not assertion

This chapter's example runs on ports `8087` (Quarkus) and `8007` (FastAPI):

```bash
cd examples/07-partial-updates
./verify.sh
```

`verify.sh` brings both services up with `docker compose`, waits for health, then drives the full sequence against each stack: `POST /bookings` → `201`; a merge patch that changes `requestedPickup` while leaving `origin` byte-identical; a second merge patch setting `requestedPickup` to `null`, asserting the key is gone from the response entirely, not present-and-null; a JSON Patch `replace` on `cargo[0].description`, asserting only that field moved; a JSON Patch with a `test` op asserting `status == CONFIRMED` against a booking that's still `PENDING`, asserting the response is `409` or `422` with a `Problem` body; and `PATCH` with `Content-Type: text/plain` and with plain `application/json`, both asserting `415`. Every response body is schema-validated against `contracts/schemas/shipping.schema.json`, and the run prints `PASS` only when every assertion holds on **both** stacks.

The README's drift probe makes the stakes concrete: comment out the `replace` branch's effect in `python/app/json_patch.py` so it silently falls through on a no-op `continue`, and `verify.sh` fails immediately: `FAIL — python json-patch replace did not apply (got cargo[0].description=Palletized electronics)` — because the behavioral check compares the actual post-patch field, not just the status code. Swallow `JsonPatchTestFailed` instead of mapping it to a `Problem`, and the failure flips to `expected HTTP 409 or 422, got 200`: a `test` precondition that silently no-ops on mismatch is worse than useless, because a client relying on it for concurrency safety would believe its patch failed to protect against a race that it actually let through. Revert either edit and the run returns to green on both stacks.

{% include excalidraw.html file="07-patch-vs-merge" alt="The same Booking resource shown receiving two different partial-update requests side by side: a JSON Merge Patch sent as application/merge-patch+json, a sparse object with requestedPickup changed and a null field marked for deletion, merged recursively into the target; and a JSON Patch sent as application/json-patch+json, an ordered array of add/remove/replace/test operations addressed by JSON Pointer paths like /cargo/0/description, applied in sequence to the same target, with a failing test operation shown short-circuiting the whole array before any operation after it runs." caption="Figure 7.1 — JSON Patch vs JSON Merge Patch on the same booking." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to the partial-update format choice. When the typical caller already has a sparse object to send — a form, a client diffing its own local state — and the domain has no field where <code>null</code> is a meaningful value distinct from "absent," <strong>JSON Merge Patch</strong> is the lower-cost correct answer: smaller bodies, no operation vocabulary to learn, a result a caller can reason about by eye. When an edit must land on one element inside an array without resending the whole array, or a caller needs to make its write conditional on the resource's current state via <code>test</code>, reach for <strong>JSON Patch</strong> — the verbosity buys precision and a concurrency guard merge patch cannot express at all. Don't guess at the client's capability from the media type alone: declare both, dispatch on <code>Content-Type</code> exactly as this chapter's two stacks do, and return <code>415</code> for anything else — a server that silently accepts a Content-Type it never validated is a server where "which format did that body actually follow" becomes a debugging question instead of a routing fact. And regardless of format, never let either patch style touch a server-assigned field: enforce <code>id</code>/<code>createdAt</code> immutability and the <code>updatedAt</code> restamp as an invariant of the resource, not an artifact of whichever patch happened to be sent.</p></div>
