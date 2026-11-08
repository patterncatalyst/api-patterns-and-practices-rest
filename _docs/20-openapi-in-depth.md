---
title: "OpenAPI in depth"
order: 20
part: "Multi-protocol contracts & framework deep-dives"
description: "OpenAPI 3.1 schemas are JSON Schema: type-array nullability, a top-level webhooks section, and a structural drift check that keeps a served document matching the shared schema."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Express nullable fields with JSON Schema's `type` array (`type: ["string","null"]`) instead of the legacy `nullable: true` flag.
- Document an outbound call with a top-level `webhooks` section (`bookingStatusChanged`) in the same shape as a path operation.
- Serve a hand-authored document (`mp.openapi.scan.disable=true`) on Quarkus and a patched generated one (`custom_openapi()`) on FastAPI for the same construct.
- Build a structural drift check (`check_openapi.py`) that compares required-field sets instead of diffing bytes.
- Decide when a living-contract drift gate is worth running on every push.

## Why this matters

A contract-first service has one JSON Schema file and an OpenAPI document that points into it. Paths, methods and status codes are the familiar half. The other half is what the document can say about the schemas themselves, what it can say about calls the server makes, and how a team keeps a served document matching the one it agreed to ship. None of this changes a response body. It changes what the document describing the responses promises, and whether a generator, a reader or a CI job can trust it.

{% include excalidraw.html file="20-openapi-in-depth" alt="A shared contract schema feeds a drift check. The Quarkus stack serves a hand-authored static OpenAPI document and the FastAPI stack serves a generated and patched one, each with a type-array nullable field and a webhooks section. CI compares each served document's required-field set against the contract, passing on a match and failing the build on divergence." caption="Figure 20.1: The living-contract loop: edit the contract, each stack serves its document, the drift check compares, CI gates on the result." %}

## The schema section is JSON Schema

OpenAPI 3.1 defines its schema object as a JSON Schema 2020-12 dialect. Earlier versions used a subset of an older draft plus OpenAPI-only extensions, so a schema written for OpenAPI and one written for a general validator only resembled each other, and a `$ref` from an OpenAPI document into a standalone schema file needed tool-specific handling. With the dialects aligned, one schema means one thing to a validator, a documentation renderer and a code generator.

Nullability shows the difference. The old spelling is a sibling flag, `nullable: true`, which exists nowhere in JSON Schema; a generic validator ignores it. The aligned spelling is a `type` array:

| Spelling | Understood by |
|---|---|
| `type: string` plus `nullable: true` | OpenAPI-aware tools only |
| `type: [string, "null"]` | Anything that speaks JSON Schema |

Both say the same thing. Only the second travels. `Booking.cancellationReason` is declared as a type array: a string once a booking is cancelled, `null` until then. The drift check accepts either spelling, because the property it guards is "nullability is expressed in a form JSON Schema recognizes," not one vintage of syntax.

The composition keywords `oneOf`, `anyOf`, `allOf` and `if`/`then`/`else` are ordinary JSON Schema in the same way. A `HAZARDOUS` cargo item that must carry a regulatory classification code, and a `GENERAL` item that never does, is an `if`/`then` pair, written exactly as it would be in a standalone schema.

## Webhooks: the call the server makes

Every path describes an inbound call. A top-level `webhooks` section describes the opposite direction: a request the server initiates to a URL the client registered. Without it, an outbound notification is either undocumented or described in prose beside the spec.

A webhook entry has the shape of a path operation, a `requestBody` and a map of responses, because a callback is still a request/response exchange. The `bookingStatusChanged` entry describes a `POST` carrying a `BookingEvent` payload whenever a booking's status changes. `BookingEvent` reuses the component types the synchronous API defines (`BookingStatus`, the `bkg_`-prefixed id pattern) and mirrors `#/$defs/BookingEvent` in the shared schema. Neither server issues the call; the entry proves the document can describe it and a validator can parse it. A production integration wires an HTTP client to send that `POST` on each status transition.

## Serving the document on each stack

The two stacks close the gap in opposite directions.

**Quarkus** builds its document by scanning JAX-RS annotations. Nothing in that model can emit a `type` array for a generated field or a top-level `webhooks` map, because a webhook corresponds to no annotated method. So the document is hand-authored: `application.properties` sets `mp.openapi.scan.disable=true`, and `smallrye-openapi` serves `META-INF/openapi.yaml` verbatim at `/q/openapi` instead of merging it with scanner output. The live `POST` and `GET /bookings` endpoints work independently of that file, which is why drift between them is possible and has to be checked.

**FastAPI** generates natively and accepts `webhooks=` on the constructor, an `APIRouter` of documentation-only routes that render under the top-level `webhooks` key of `/openapi.json`. Nullability is where the default diverges: a pydantic v2 `Optional[str]` exports as `anyOf: [{"type": "string"}, {"type": "null"}]`. That is valid JSON Schema, but it isn't the `type` array form. A `custom_openapi()` function on `app.openapi` builds the document with `get_openapi()` and patches that one field.

{% include codetabs.html langs="Quarkus|Python" %}

```yaml
cancellationReason:
  description: >
    Null until the booking is cancelled. Declared as an OpenAPI 3.1
    JSON Schema `type` ARRAY (["string", "null"]) rather than an
    OAS-3.0 `nullable: true` flag.
  type: [string, 'null']
```

```python
booking_schema["properties"]["cancellationReason"] = {
    "description": (
        "Null until the booking is cancelled. Declared as an OpenAPI "
        "3.1 JSON Schema `type` ARRAY ([\"string\", \"null\"]) rather "
        "than an OAS-3.0 `nullable: true` flag."
    ),
    "type": ["string", "null"],
}
```

Both patches appear only in the served documents. The shared `Booking` schema sets `additionalProperties: false` and doesn't declare `cancellationReason`, so a live response carrying it would fail schema validation; the field stays out of the wire format.

## Keeping the served document in step

A hand-authored document and a generator's output fail the same way: nothing stops either from quietly disagreeing with the schema the team committed to. Quarkus's static `openapi.yaml` is a second, independently maintained copy of the `Booking` shape. FastAPI's pydantic models can drift from the shared schema one field at a time under different reviewers. Remove a field from `required` and every status code and response body is still correct, while the document now promises less than the team agreed.

A living contract compares each served document with the committed schema on every build, so the document can't change meaning without a red build. Byte-equal diffing is the wrong comparison. Served documents differ from the schema in `$id`, `info`, descriptions and `$ref` layout, and a gate that fails on all of that trains a team to ignore or delete it. The check instead pulls the set of required property names for `Booking` from each stack's live document and compares it with `#/$defs/Booking.required` in the shared schema. That set is what a client integrating against either document depends on.

The check fetches each document over HTTP from the running service, not from a checked-in copy. For both stacks it asserts three things: a JSON Schema nullable construct exists somewhere, `webhooks` is non-empty, and the required sets match. Drop `cargo` from `required` in `META-INF/openapi.yaml` and the check names the field and the side it's missing from. A second document, hand-authored or independently generated, makes the check necessary.

## Decision rule

| Question | Lean toward depth and a gate | Lean toward neither |
|---|---|---|
| Who reads the document? | Partners, SDK pipelines, a portal the API team doesn't control | One team reading its own server |
| How fast does the contract change? | Fields added and renamed every sprint | Rarely; an occasional manual comparison is enough |
| Does the API call out to clients? | Yes: document the webhook | No: a webhook nobody receives reads as aspirational |
| Is there a second artifact to compare? | A static document or a separately generated one | One generated document is the only source of truth |

> **🤖 Explore with your agent**
>
> "In `examples/20-openapi-depth`, add an optional `deliveryNote` string to `Booking` in `contracts/schemas/shipping.schema.json` as a `type: [string, 'null']` array, surface it in the Quarkus `META-INF/openapi.yaml` and the FastAPI `custom_openapi()` patch, and keep it out of the required set. Then remove `cargo` from `required` in `META-INF/openapi.yaml` and tell me which assertion in `check_openapi.py` should fail."
>
> Check: `./verify.sh` passes after the first change, and fails naming `cargo` after the second.

## Build, run, observe

```bash
cd examples/20-openapi-depth && ./verify.sh
```

Quarkus listens on 8100 and FastAPI on 8020. `verify.sh` fetches each live document, runs the three structural assertions, then drives a `POST` and `GET` booking round trip validated against `#/$defs/Booking`. It prints `PASS` when both stacks hold. The full output is in `examples/20-openapi-depth/README.md`.

- Drop `cargo` from `required` in `META-INF/openapi.yaml`: the required-set check fails and names the field.
- Delete the `cancellationReason` property: the nullable check fails.
- Delete the `webhooks` section: the webhooks check fails.
- Change `cancellationReason` back to `nullable: true`: the check still passes.

## For deeper coverage

- [OpenAPI Specification 3.1.0](https://spec.openapis.org/oas/v3.1.0): the JSON Schema 2020-12 alignment and the `webhooks` object.
- J.J. Geewax, *API Design Patterns* (Manning, 2021).
- Gough, Bryant & Auburn, *Mastering API Architecture* (O'Reilly, 2022).
- *Cloud Native Design Patterns*, api-management (same series, contract governance).
