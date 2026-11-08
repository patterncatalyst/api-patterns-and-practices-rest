---
title: "Contract-first with OpenAPI"
order: 4
part: "Designing resources with a contract"
description: "Write the bookings and cargo contract as one OpenAPI document, implement it on both stacks, and fail the build when a response drifts from the schema."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Explain why contract-first (one `shipping-api.yaml` plus one `shipping.schema.json`) prevents the drift that generating a document from code invites.
- Reference a shared type from an OpenAPI operation with `$ref: '../schemas/shipping.schema.json#/$defs/Booking'` instead of redefining it inline.
- Explain what `additionalProperties: false` enforces on a response that JSON Schema doesn't check by default.
- Implement the identical `POST /bookings` contract on both stacks, matching status code, `Location` header and body shape.
- Validate live response bodies against the schema to catch a response that returns the right status code with the wrong shape.

## Why this matters

`Booking` is the aggregate root, `Cargo` nests beneath it, and `Location` is reference data outside the boundary. None of that becomes an API until someone writes down the exact shape of each request and response and decides where that writing lives. Put it in one OpenAPI document before either stack has a line of handler code, and add a CI job that fails the build when an implementation stops matching it. Every later hands-on chapter starts from that contract, not from whichever stack was written first.

## Contract-first versus code-first

Code-first looks faster. Write the Quarkus resource, let a generator derive an OpenAPI document from the annotations, and call that document the contract. It works until a second team writes the Python implementation from a different mental model and produces a response shape that is reasonable on its own terms and incompatible with the first. Nothing catches the divergence, because no contract exists independent of either codebase. Each client's accidental contract is whichever implementation it integrated against.

A generated document also describes whatever the code does today, including behavior nobody meant to commit to. Rename a field and the document updates with it, with no conversation about whether the rename breaks a client. The document is a shadow of the code, one deploy behind.

Contract-first inverts the order. `contracts/openapi/shipping-api.yaml` is written and version-controlled as its own artifact, describing `Booking`, `Cargo`, every status code and every error shape before a resource class or route exists. Both stacks implement it. A field rename happens in the contract first, as a diff both teams review, and only then ripples into each stack's models. CI validates every response against the same document, so the decision has mechanical enforcement.

| | Code-first | Contract-first |
|---|---|---|
| Source of truth | The code | A reviewed document |
| A rename shows up as | A changed generated file | A diff to the contract |
| Second implementation | Drifts silently | Checked against the same schema |
| Fits | One team, one consumer | Several stacks, clients that can't read the server, years of evolution |

## Anatomy of the shipping contract

Two files divide the work. `contracts/schemas/shipping.schema.json` is JSON Schema 2020-12, the draft modern OpenAPI aligns with, and holds every payload type under `$defs`: `Booking`, `Cargo`, `Money`, `Location`, `Problem` and more. `contracts/openapi/shipping-api.yaml` holds what JSON Schema doesn't describe: paths, methods, status codes and headers. It never redefines a payload; it references one.

`POST /bookings` reaches into the shared schema for both its request and its success response:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '../schemas/shipping.schema.json#/$defs/BookingRequest'
responses:
  '201':
    description: Booking created.
    headers:
      Location:
        description: URI of the created booking.
        required: true
        schema: { type: string, format: uri-reference }
    content:
      application/json:
        schema:
          $ref: '../schemas/shipping.schema.json#/$defs/Booking'
```

`BookingRequest` and `Booking` are defined once, in the schema file. The same `$defs/Booking` can describe the event payload an AsyncAPI channel emits on a status change, or the `data` of a CloudEvents envelope. Inline types can't be shared with a document that isn't OpenAPI, which is why the contract is split in two.

Types compose inside the schema: `Booking.cargo` is an array of `#/$defs/Cargo`, `Booking.quote` is a `#/$defs/Money`, and `Money.amount` is a decimal-string pattern rather than a bare number. The `bkg_` id prefix, the five-value `BookingStatus` enum and `additionalProperties: false` on every object are promises about every response. The last does the most structural work. JSON Schema allows extra properties by default, so without it a server could add an undeclared field and no validator would object. Set to `false`, "the response has exactly these fields" becomes enforceable.

CI checks the contract files before any implementation. Spectral and Redocly lint `shipping-api.yaml` for structural problems such as an operation with no response or a `$ref` that resolves to nothing, and `scripts/validate_schemas.py` confirms the shared schema is valid JSON Schema 2020-12.

## The resources served

`/bookings` carries `GET`, which lists a page as a `BookingCollection`, and `POST`, which creates one and returns `201` with a `Location` header. `/bookings/{bookingId}` carries `GET`, `PUT` for an idempotent full replace, `PATCH` for a partial update, and `DELETE` for the soft cancel that flips `status` to `CANCELLED` instead of erasing the row. `/bookings/{bookingId}/cargo` is the sub-resource inside the aggregate: `GET` lists its items and `POST` adds one with its own `Location`.

Every error path converges on one shape: `application/problem+json`, the RFC 9457 `Problem` type, with a `title`, a `status` and an optional `detail`. A client that has handled one `404` from this API has handled every `404`. That is the uniform interface applied to failure.

Both stacks implement the full `bookings` and `cargo` surface against an in-memory store. Hypermedia links stay unpopulated, and `PATCH` accepts merge-patch only. Every line in either implementation answers to a line in `shipping-api.yaml`.

## Both stacks, one contract

`examples/04-contract-first/` ships Quarkus (`quarkus/`, port 8080) and FastAPI (`python/`, port 8000) as independent implementations of the same paths. Neither generates code from the other. `POST /bookings` on both:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@POST
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public Response createBooking(@Valid BookingRequest request) {
    List<Cargo> cargoItems = toCargoItems(request.cargo());
    String now = nowUtc();
    Booking booking = new Booking(
            "bkg_" + Ulid.generate(),
            BookingStatus.PENDING,
            request.origin(),
            request.destination(),
            cargoItems,
            QuoteCalculator.compute(cargoItems),
            request.requestedPickup(),
            now,
            null);
    store.put(booking);

    // A literal header string, NOT Response.created(URI): per the
    // JAX-RS spec, ResponseBuilder.location(URI) resolves a relative
    // URI into an absolute one against the base URI, which would make
    // Quarkus's Location header shape diverge from the Python stack's
    // relative `/bookings/{id}`. Setting the header directly keeps the
    // two stacks byte-for-byte identical.
    return Response.status(Response.Status.CREATED)
            .header("Location", "/bookings/" + booking.id())
            .entity(booking)
            .build();
}
```

```python
@app.post("/bookings")
def create_booking(payload: BookingRequest) -> JSONResponse:
    cargo_items = [
        Cargo(id=f"crg_{generate_ulid()}", **item.model_dump())
        for item in payload.cargo
    ]
    booking = Booking(
        id=f"bkg_{generate_ulid()}",
        status=BookingStatus.PENDING,
        origin=payload.origin,
        destination=payload.destination,
        cargo=cargo_items,
        quote=compute_quote(cargo_items),
        requestedPickup=payload.requestedPickup,
        createdAt=_now_utc(),
    )
    store.put(booking)
    return _json(201, booking, headers={"Location": f"/bookings/{booking.id}"})
```

Both assign a `bkg_`-prefixed id, set status to `PENDING`, compute a quote and return `201` with a `Location` header built as a literal relative path. Request validation happens before the handler runs: Bean Validation on the `@Valid` record in Quarkus, the Pydantic model in FastAPI, each mapped to a `400` `Problem`.

The quote is arithmetic running through two number-formatting stacks:

{% include codetabs.html langs="Quarkus|Python" %}

```java
private static final double RATE_PER_KG = 2.50;

private QuoteCalculator() {
}

public static Money compute(List<Cargo> cargo) {
    double totalWeightKg = 0;
    for (Cargo item : cargo) {
        totalWeightKg += item.dimensions().weightKg();
    }
    String amount = BigDecimal.valueOf(totalWeightKg * RATE_PER_KG)
            .setScale(2, RoundingMode.HALF_UP)
            .toPlainString();
    return new Money("USD", amount);
}
```

```python
_RATE_PER_KG = 2.50


def compute_quote(cargo_items: Iterable[Cargo | CargoRequest]) -> Money:
    total_weight_kg = sum(item.dimensions.weightKg for item in cargo_items)
    amount = str(
        Decimal(str(total_weight_kg * _RATE_PER_KG)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    return Money(currency="USD", amount=amount)
```

Each language's default formatter rounds differently: Java's `%.2f` rounds half-up and Python's `:.2f` rounds half-to-even, so a value that lands exactly on a cent boundary can come out a cent apart. Both stacks therefore name the rounding mode explicitly, `BigDecimal.setScale(2, RoundingMode.HALF_UP)` and `Decimal.quantize(..., rounding=ROUND_HALF_UP)`, and agree on every input. A contract that computes money on two stacks has to state the rounding rule, or move the computation to one service both call. The schema settles the representation: `Money.amount` is a decimal string, never a JSON number. An ambiguous numeric type would let a two-language disagreement leak into the wire format.

## The CI gate

A contract that nothing checks against is a comment with YAML syntax. `.github/workflows/contracts.yml` runs three jobs on every push: one lints and validates the contract files (Spectral, Redocly, a JSON Schema structural check), one builds the Jekyll site, and one runs every example's `verify.sh`.

A status code check alone passes a `200` with the wrong body. The examples check the status and then schema-validate the full body against `shipping.schema.json` with `examples/_lib/validate_response.py`.

Prove a validator before trusting it. A quietly broken one (a bad `$ref`, the wrong JSON Schema draft) approves every response. `validate_response.py --selftest` needs no app or network: it must accept a known-good `Booking` and reject altered copies with an undeclared field, an out-of-enum `status` and a corrupted `id`, and it runs before any container starts.

A `200` that silently carries the wrong shape is the failure a contract exists to rule out, and the schema check is the step that catches it.

{% include excalidraw.html file="04-contract-first-flow" alt="The shared OpenAPI and JSON Schema contract scaffolds both the Quarkus and the FastAPI stack, each stack serves live HTTP responses, CI's verify.sh schema-validates every live response body against the same contract, and the pipeline either merges on a match or fails the build on drift." caption="Figure 4.1: Contract-first: one schema, two stacks, CI as the drift gate." %}

## When not to use it

With a single internal consumer that reads one team's source, a contract independent of the code buys little. The payoff scales with client diversity and evolution pressure. Where there are several stacks, clients that can't read the server's source and a shape that must keep working for years, write the contract before the first handler. Treat a response that returns the right status code as unverified until a schema check confirms its body.

> **🤖 Explore with your agent**
>
> "Add an optional `notes` string to `Booking` in `contracts/schemas/shipping.schema.json`, then return it from `POST /bookings` and `GET /bookings/{bookingId}` in both `examples/04-contract-first/quarkus` and `examples/04-contract-first/python`. Contract first: change no implementation until `python3 scripts/validate_schemas.py` passes."
>
> Check: `cd examples/04-contract-first && ./verify.sh` passes, and returning `notes` from a stack before the schema declares it fails on `additionalProperties`.

## Build, run, observe

```bash
cd examples/04-contract-first && ./verify.sh
```

The script starts both stacks, drives the full booking sequence against each, schema-validates every response body and prints `PASS` once both stacks agree with the contract. `examples/04-contract-first/README.md` has the full output.

Experiments:

- Change `quote.amount` to a bare JSON number in either stack. The status stays `200` and the schema step fails on that field.
- Add an undeclared field such as `internalNotes` to a `Booking` response. `additionalProperties: false` rejects it with `'internalNotes' was unexpected`. Revert either change and the run returns to `PASS`.

## For deeper coverage

- Lukasz Dynowski & Marcin Dulak, *Learning API Styles* (O'Reilly, 2025): contract-first workflows across multiple API styles.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): schema design patterns for shared types defined once and referenced everywhere.
- [OpenAPI Specification v3.1](https://spec.openapis.org/oas/latest.html) and [JSON Schema 2020-12](https://json-schema.org/specification): the two specs `shipping-api.yaml` and `shipping.schema.json` are authored against.
- Cloud Native Design Patterns, [API registry](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/09-api-registry.md): publishing and governing a contract as its own artifact.
- Cloud Native Design Patterns, [API metadata](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/10-api-metadata.md): describing a contract's shape and provenance beyond the schema itself.
