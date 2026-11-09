---
title: "Partial updates: JSON Patch vs Merge Patch"
order: 7
part: "HTTP semantics done right"
description: "Two standard ways to change part of a resource, RFC 7396 JSON Merge Patch and RFC 6902 JSON Patch: their media types, trade-offs and when each fits."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Distinguish `application/merge-patch+json` (RFC 7396) from `application/json-patch+json` (RFC 6902) and choose the right one for a given change.
- Apply RFC 7396's merge rules, including the rule that a `null` value in the patch deletes a field rather than setting it.
- Apply RFC 6902 operations (`add`, `remove`, `replace`, `move`, `copy`, `test`) addressed by JSON Pointer paths.
- Use a `test` operation for optimistic concurrency control, mapping a failed precondition to `409 Conflict` and a malformed patch to `422 Unprocessable Content`.
- Dispatch `PATCH /bookings/{id}` on `Content-Type` and reject anything else with `415 Unsupported Media Type`.

## Why this matters

`PUT` replaces the whole resource, and that is also its limit. A client that wants to move a booking's `requestedPickup` by one day has to re-send the entire `Booking` (origin, destination, every cargo item, the quote), and it has to read the current representation first or risk clobbering a concurrent change to a field it never meant to touch. `PATCH` describes a change instead of a replacement.

"Describes a change" is not one format. The IETF standardized two incompatible ones, and a server has to pick, document and dispatch on the one a request uses. `PATCH /bookings/{id}` accepts both, distinguished by `Content-Type`. `application/merge-patch+json` carries **RFC 7396 JSON Merge Patch**, a partial object. `application/json-patch+json` carries **RFC 6902 JSON Patch**, an ordered array of operations. Neither subsumes the other.

## JSON Merge Patch: a partial object

The body is a JSON object shaped like the target, holding only the keys to change. The server walks it key by key:

- A non-null value overwrites the target's key, or merges recursively if both sides are objects.
- A `null` value **deletes** the key from the target.
- An absent key is left alone.

Against a booking whose `requestedPickup` is `"2026-02-01"`, this patch changes that one field and leaves everything else as it was:

```json
{ "requestedPickup": "2026-03-01" }
```

This one removes `requestedPickup` altogether:

```json
{ "requestedPickup": null }
```

It doesn't set the field to `null`. RFC 7396 has no way to express that, because `null` in a patch means deletion. The first trade-off follows: a domain field that needs a `null` *value*, as distinct from "absent", can't be changed with merge patch. The booking schema models `requestedPickup` as optional rather than nullable for this reason.

The second trade-off is arrays. Merge patch recurses into objects but treats an array as a scalar: a patch that includes one replaces the whole target array. Fixing a typo in `cargo[0].description` means resending all of `cargo`, the whole-resource resend `PATCH` was meant to avoid. Merge patch fits when the change is a handful of top-level or nested-object fields, and not when an array element needs a scoped edit.

The algorithm is short enough that neither stack needs a library:

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

## JSON Patch: operations addressed by JSON Pointer

RFC 6902 describes the edits instead of the result. The body is an array of operation objects, each with an `op` and a `path` written as an RFC 6901 JSON Pointer such as `/cargo/0/description`. Operations apply in order, each against the document the previous one left.

| op | Effect |
|----|--------|
| `add` | Insert `value` at `path` (an object key, an array index, or `-` to append) |
| `remove` | Delete the value at `path` |
| `replace` | Overwrite the existing value at `path`, which must already exist |
| `move` | `remove` from `from`, then `add` that value at `path` |
| `copy` | `add` a deep copy of the value at `from`, at `path` |
| `test` | Assert the value at `path` equals `value`; on mismatch the **entire** patch fails with nothing applied |

Changing one cargo item's description and nothing else:

```json
[
  { "op": "replace", "path": "/cargo/0/description", "value": "Re-palletized electronics" }
]
```

That is the array-element edit merge patch can't express. `cargo[1..n]` are untouched because the patch never names them.

`test` is the cheapest optimistic concurrency control available. A client that read `status` as `CONFIRMED` can make the whole patch conditional on it:

```json
[
  { "op": "test", "path": "/status", "value": "CONFIRMED" },
  { "op": "replace", "path": "/cargo/0/description", "value": "Re-palletized electronics" }
]
```

If another request changed the status between the client's read and this `PATCH`, the `test` fails, the `replace` never runs, and the server reports the conflict instead of applying an edit computed against stale state. Two failures map to two codes:

| Failure | Status | Why |
|---|---|---|
| A `test` operation doesn't match | `409 Conflict` | The request is well formed, but the precondition fails against the resource's current state |
| Malformed pointer, `replace` on a missing path, array index out of range, missing `value` or `from` | `422 Unprocessable Content` | The patch can't be carried out at all |

Both stacks hand-roll RFC 6902 with no library: once JSON Pointer tokenizing is right, the algorithm is self-contained. The `replace` operation:

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

`navigateToParent` and `_navigate_to_parent` walk every token but the last, so `replace`, `add` and `remove` act on the container that holds the target. `replace` on an array index requires the index to exist, where `add` also accepts `-` to append. Both implementations deep-copy before mutating and return a new tree at every step, so a `test` failure partway through leaves the original untouched.

{% include excalidraw.html file="07-patch-vs-merge" alt="The same Booking resource shown receiving two different partial-update requests side by side: a JSON Merge Patch sent as application/merge-patch+json, a sparse object with requestedPickup changed and a null field marked for deletion, merged recursively into the target; and a JSON Patch sent as application/json-patch+json, an ordered array of add/remove/replace/test operations addressed by JSON Pointer paths like /cargo/0/description, applied in sequence to the same target, with a failing test operation shown short-circuiting the whole array before any operation after it runs." caption="Figure 7.1: JSON Patch vs JSON Merge Patch on the same booking." %}

## The media type is the dispatch key

Neither body declares which RFC it follows. A bare JSON array could be either, so `Content-Type` is the only signal, and anything else gets **415 Unsupported Media Type**.

Quarkus dispatches in the framework. `BookingResource` declares two `@PATCH` methods on the same `@Path("/{id}")`, one with `@Consumes("application/merge-patch+json")` and one with `@Consumes("application/json-patch+json")`. A request matching neither, such as plain `application/json`, `text/plain` or no body, raises `NotSupportedException`, which `ProblemMappers` turns into a 415 `Problem`.

Starlette routes on path and verb only, so FastAPI reads the header itself:

```python
@app.patch("/bookings/{booking_id}")
async def patch_booking(booking_id: str, request: Request) -> JSONResponse:
    """Dispatch on Content-Type to one of the two partial-update
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

On the wire the two behave identically. A client that guesses plain `application/json` gets 415 on both stacks, not a `200` that applied nothing or a body parsed as the wrong format.

## Server-assigned fields survive either patch

JSON Patch's `replace` and `remove` ignore a schema's `readOnly` annotation, so an operation targeting `/id` would apply like any other. Both stacks apply the patch to the full current representation, then restamp the fields a client must not control: `id` and `createdAt` come from the pre-patch booking, and `updatedAt` is set to now.

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

The Python side assigns `merged["id"] = existing.id`, `merged["createdAt"] = existing.createdAt` and `merged["updatedAt"] = _now_utc()` on both the merge-patch and JSON-Patch results before validating and storing. A client that sends `replace /id` or merge-patches `{"createdAt": "2020-01-01T00:00:00Z"}` gets `200` with its other edits applied and those fields unchanged. The invariant belongs to the resource, not to either patch format.

## Choosing between them

| | Merge Patch | JSON Patch |
|---|---|---|
| Body | A sparse object | An array of operations |
| Array element edit | Resend the whole array | Address one element by index |
| Set a field to `null` | Not expressible | `replace` with `null` |
| Precondition on current state | None | `test` |
| Typical caller | A form or client diffing local state | A reconciliation job, or a client mediating between systems that can't coordinate timing |

Use merge patch when the caller already holds a sparse object and no field needs a meaningful `null`. Use JSON Patch when an edit must land inside an array, when `null` is a real value, or when a concurrent change between read and write must fail the patch. Supporting both costs more code than one, and the gap is expensive to discover in production.

> **🤖 Explore with your agent**
>
> "In `examples/07-partial-updates/`, add a `PATCH /bookings/{id}` request that moves cargo item 0's description using JSON Patch with a `test` on `/status`, and run it against both stacks with `curl`. Then fix any place a JSON Patch operation targeting `/id` or `/createdAt` is not ignored."
>
> Check: the `test` request returns `409` when `status` differs and `200` otherwise, and `replace /id` leaves `id` unchanged in the response.

## Build, run, observe

```bash
cd examples/07-partial-updates && ./verify.sh
```

The stacks run on ports `8087` (Quarkus) and `8007` (FastAPI). The script runs a create, two merge patches (one changes a field, one removes it with `null`), a JSON Patch `replace`, a failing `test` operation and two `PATCH` calls with unsupported media types against each stack, schema-validating every response. It prints `PASS` when both stacks agree. `examples/07-partial-updates/README.md` has the full output.

Experiments:

- Make the `replace` branch in `python/app/json_patch.py` a no-op. The run fails because `cargo[0].description` kept its old value.
- Swallow `JsonPatchTestFailed` instead of mapping it to a `Problem`. The run fails with `expected HTTP 409 or 422, got 200`. A `test` that silently passes on mismatch gives a client false concurrency safety.

## For deeper coverage

- [RFC 6902: JavaScript Object Notation (JSON) Patch](https://www.rfc-editor.org/rfc/rfc6902).
- [RFC 7396: JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396).
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): partial-update patterns and the trade-offs between them.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): standard update patterns, including partial updates.
- *API Error Handling* (Appendix E, [Cloud Native Design Patterns](https://github.com/patterncatalyst/cloud-native-design-patterns)): the `409` and `422` error-contract distinction applied to a failed `test` operation versus a malformed patch.
