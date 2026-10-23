---
title: "Contract-first with OpenAPI"
order: 4
part: "Designing resources with a contract"
description: "Author the bookings and cargo contract as one OpenAPI document, scaffold both stacks to serve it, and wire the CI gate that fails the build when a response drifts from the schema."
duration: "30 min"
---

## Learning objectives

By the end of this chapter you can:

- Explain why contract-first (one `shipping-api.yaml` plus one `shipping.schema.json`) prevents the drift that generating a document from code invites.
- Reference a shared type from an OpenAPI operation with `$ref: '../schemas/shipping.schema.json#/$defs/Booking'` instead of redefining it inline.
- Explain what `additionalProperties: false` enforces on a response that JSON Schema doesn't check by default.
- Implement the identical `POST /bookings` contract on both stacks, matching status code, `Location` header, and body shape byte-for-byte.
- Run `verify.sh`'s schema-validation step (`examples/_lib/validate_response.py`) to catch a response that returns the right status code with the wrong body shape.

## Why this matters

Chapter 3 named the resources: `Booking` as the aggregate root, `Cargo` nested beneath it, `Location` as reference data outside the boundary. None of that becomes an API until someone writes down the exact shape of a request and a response, and decides where that writing lives. This chapter puts it in one place (a single OpenAPI document) before either stack has a line of handler code, and wires a CI job that fails the build the moment an implementation stops matching it. That ordering is the pivot every later hands-on chapter turns on: each one starts from the contract, not from whichever stack happened to get written first.

## Contract-first versus code-first

Code-first looks faster at the start. Write the Quarkus resource, annotate it, let a generator derive an OpenAPI document from the annotations, and call that document "the contract." It works right up until a second team writes the Python implementation from a different mental model of the same domain and produces a response shape that's reasonable on its own terms and incompatible with the first. Nothing catches that divergence, because there's no contract independent of either codebase to check either one against: there are two descriptions of two implementations, and whichever one a given client happened to integrate against becomes that client's accidental contract.

The failure mode compounds over time even with one implementation. A generated OpenAPI document describes whatever the code currently does, which means every behavior (including the ones nobody meant to commit to) becomes part of the public shape. Rename a field, and the generated document updates along with it; nothing forces a conversation about whether that rename breaks a client. The document that's supposed to be the source of truth for what the API promises is instead a shadow of the code, always one deploy behind, describing the past rather than constraining the future.

Contract-first inverts the order. `contracts/openapi/shipping-api.yaml` is written and version-controlled as its own artifact, describing `Booking`, `Cargo`, every status code, and every error shape before a Quarkus resource class or a FastAPI route exists. Both stacks are implementations of that document, not sources for it. A field rename now has to happen in the contract first, where it's visible as a diff against a file both teams review, and only then ripples into each stack's model classes. The shape of the API becomes a decision instead of an accident. Because the same document is what CI validates every response against, it's a decision with mechanical enforcement, not just a convention Part 2 asks engineers to remember.

## Anatomy of the shipping contract

The contract spans two files with a strict division of labor. `contracts/schemas/shipping.schema.json` is JSON Schema 2020-12 (the same draft modern OpenAPI aligns with, which is what makes the next part possible) and holds every payload type the domain needs under `$defs`: `Booking`, `Cargo`, `Money`, `Location`, `Problem`, and more. `contracts/openapi/shipping-api.yaml` holds everything JSON Schema doesn't describe: the paths, the HTTP methods, the status codes, the headers. It never redefines a payload shape; it references one.

Here's the `POST /bookings` operation reaching into the shared schema for both its request and its success response:

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

`BookingRequest` and `Booking` are each defined exactly once, in the schema file, and that single definition is what every operation that touches a booking points back to. The same `$defs/Booking` is what Chapter 21's AsyncAPI document will reference for the event payload emitted on a status change, and what a CloudEvents envelope will carry as its `data`. Define the type once; reference it everywhere a sync endpoint, an async channel, or a workflow step needs it. That reuse rule is the whole reason the contract is split into a schema file and an API file instead of one flat OpenAPI document with inline types: inline types can't be shared with a document that isn't OpenAPI at all.

Inside the schema, the types compose the same way: `Booking.cargo` is an array of `#/$defs/Cargo`, `Booking.quote` is a `#/$defs/Money`, `Money.amount` is constrained to a decimal-string pattern rather than a bare number. Every one of those constraints (the `bkg_` prefix pattern on an id, the five-value `BookingStatus` enum, `additionalProperties: false` on every object) is a promise the contract makes about every response, not a hint. `additionalProperties: false` does the most structural work of the three: without it, a server could add an undeclared field to a response and no validator would object, because JSON Schema treats extra properties as allowed by default. Setting it to `false` on `Booking`, `Cargo`, and every other object type turns "the response has exactly these fields" into an enforceable claim instead of a convention the two stacks would otherwise have to keep in sync by hand.

CI checks the contract files themselves before it ever checks an implementation against them: Spectral and Redocly lint `shipping-api.yaml` for structural problems (an operation missing a response, a `$ref` that resolves to nothing), and a small `jsonschema`-based script in `scripts/validate_schemas.py` confirms the shared schema itself parses as valid JSON Schema 2020-12. Lint failures here are cheap to fix and expensive to skip, because every later check, including the drift probe this chapter builds toward, assumes the contract it's validating against is itself well-formed.

## The resources served

The contract's `/bookings` path carries the full method set Chapter 3 described: `GET` lists a page as a `BookingCollection`, `POST` creates one and returns `201` with a `Location` header. `/bookings/{bookingId}` carries the item operations: `GET` to fetch, `PUT` for an idempotent full replace, `PATCH` for a partial update, `DELETE` for the soft-cancel that flips `status` to `CANCELLED` rather than erasing the row. `/bookings/{bookingId}/cargo` is the sub-resource from the aggregate boundary: `GET` lists the items embedded in a booking, `POST` adds one and returns its own `Location`.

None of these operations is new; Chapter 3 argued for exactly this shape on paper, as a diagram of nouns and the methods that act on them. What's new here is that the shape now lives in a document a computer can parse: a request body that doesn't match `BookingRequest`, a response missing a required field, or a status code the contract never declared for that operation all become things a validator can catch mechanically, rather than things a reviewer has to notice by eye against a diagram.

Every error path across all of these converges on one shape: `application/problem+json`, the RFC 9457 `Problem` type from the shared schema, with a `title`, a `status`, and an optional `detail`. A client that's handled one `404` from this API has handled every `404`, because the error representation doesn't change per endpoint; only `status` and `detail` do. That's the same uniform-interface argument from Chapter 1 applied to failure instead of success: a fixed, predictable shape a generic client can parse without endpoint-specific error handling.

This chapter's example implements the full `bookings` and `cargo` surface against an in-memory store: no persistence yet, no HATEOAS links (`_links` stays unpopulated until Chapter 12), no JSON Patch (Chapter 7 adds that alongside the merge-patch `PATCH` already here). Scoping the example down to what the contract already specifies keeps it a clean test subject: every line in either implementation answers directly to a line in `shipping-api.yaml`, with nothing added that the contract doesn't already call for.

## Both stacks, one contract

`examples/04-contract-first/` ships Quarkus (`quarkus/`, port 8080) and FastAPI (`python/`, port 8000) as two independent implementations of the identical paths. Neither generates code from the other, and neither reads the other's source: each was written by reading the contract and the shared schema. Here's `POST /bookings` on both sides:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@POST
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public Response createBooking(BookingRequest request) {
    Response invalid = validateBookingRequest(request);
    if (invalid != null) {
        return invalid;
    }

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

Different languages, different frameworks, and the same decisions at every point that touches the wire: assign a `bkg_`-prefixed id, set status to `PENDING`, compute a quote, return `201` with a `Location` header built as a literal relative path rather than resolved through either framework's URI builder. That last detail matters more than it looks: Quarkus's `Response.created(URI)` would resolve a relative path into an absolute one against the server's base URI, which would make its `Location` header diverge in shape from FastAPI's. Setting the header string directly on both sides is what keeps `verify.sh` able to compare them.

The quote computation is where byte-for-byte compatibility gets interesting, because it's arithmetic running through two different number-formatting stacks:

{% include codetabs.html langs="Quarkus|Python" %}

```java
private static final double RATE_PER_KG = 2.50;

public static Money compute(List<Cargo> cargo) {
    double totalWeightKg = 0;
    for (Cargo item : cargo) {
        totalWeightKg += item.dimensions().weightKg();
    }
    String amount = String.format(Locale.ROOT, "%.2f", totalWeightKg * RATE_PER_KG);
    return new Money("USD", amount);
}
```

```python
_RATE_PER_KG = 2.50

def compute_quote(cargo_items: Iterable[Cargo | CargoRequest]) -> Money:
    total_weight_kg = sum(item.dimensions.weightKg for item in cargo_items)
    amount = f"{total_weight_kg * _RATE_PER_KG:.2f}"
    return Money(currency="USD", amount=amount)
```

Both sides sum the cargo weights, multiply by the same rate, and format to two decimal places. Java's `%.2f` rounds half-up; Python's `:.2f` rounds half-to-even. Those two rounding rules don't agree on every input: feed either formatter a value that lands exactly on the boundary between two cent amounts and the two languages can round opposite directions. They agree on inputs that already land on two decimal places without rounding, which is why `verify.sh` books `1200.5 kg` at `2.50` per kg: `3001.25` comes out identically on both sides, and the test sequence can assert one literal value against both stacks without special-casing either one's number formatting.

This gap is left open by design: a production contract that cared about every edge of floating-point rounding would need to say which rounding mode applies, or push the computation onto a server that both stacks call rather than letting each reimplement it (a design question outside this chapter's scope). What the schema does settle, unconditionally, is the representation: `Money.amount` is a decimal **string** on both sides, never a JSON number, per the schema's pattern constraint. A contract that left the numeric type ambiguous would invite exactly this kind of two-language disagreement to leak past the type system and into the wire format; pinning the representation to a string closes that specific door even while the rounding-mode question stays open.

## The CI gate that has teeth

A contract that nothing checks against is a comment with YAML syntax. `.github/workflows/contracts.yml` runs three jobs on every push: one lints and validates the contract files themselves (Spectral, Redocly, a JSON Schema structural check), one builds the Jekyll site, and a third (`examples`) runs every chapter's `verify.sh`, including this one.

`verify.sh` brings both stacks up with Docker Compose, then drives the same sequence against each: create a booking, follow its `Location`, list the collection, add a cargo item, replace the booking with `PUT`, apply a merge-patch `PATCH`, request an unsupported patch media type, fetch a nonexistent id, delete, and confirm the cancelled booking disappears from the default listing. Every one of those steps checks the HTTP status code, and then does the step that makes this chapter's claim real: it schema-validates the full response body against `contracts/schemas/shipping.schema.json`, using `examples/_lib/validate_response.py`.

That script matters enough to prove it works before trusting it for anything. Its `--selftest` mode runs first, with no app and no network: it builds a known-good `Booking`, confirms the validator accepts it, then tampers with a copy (adds an undeclared field, sets `status` to a value outside the enum, corrupts the `id` pattern) and confirms the validator rejects every tampered copy. `verify.sh` runs this self-test before it ever starts a container, so a validator that's been quietly broken (a bad `$ref`, a validator pinned to the wrong JSON Schema draft) fails loudly before it has the chance to rubber-stamp bad responses from either stack as passing.

The example's README documents a drift probe worth running once to see the gate's teeth directly: change `quote.amount` from a formatted string to a bare JSON number in either stack, or add an undeclared field like `internalNotes` to a `Booking` response, and re-run `verify.sh`. Both breakages return a `200` (nothing about the HTTP status code is wrong) and both get caught at the schema-validation step, with the exact field and the exact schema rule it violated printed to the terminal. Revert the change and the same run goes back to green. A `200` that silently carries the wrong shape is the lie Chapter 2's cacheability and client-diversity axes assume a contract rules out; this is the step that makes the assumption true.

## Running it

The script prints `PASS` only after every assertion holds for both stacks, then tears the containers down. Run it once clean, then try the drift probe from the README and watch it fail: that round trip, breaking the contract and watching the gate catch it, is worth more than reading about it.

{% include excalidraw.html file="04-contract-first-flow" alt="The shared OpenAPI and JSON Schema contract scaffolds both the Quarkus and the FastAPI stack, each stack serves live HTTP responses, CI's verify.sh schema-validates every live response body against the same contract, and the pipeline either merges on a match or fails the build on drift." caption="Figure 4.1: Contract-first: one schema, two stacks, CI as the drift gate." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to contract-first versus code-first: the payoff scales with client diversity and evolution pressure. A single internal consumer reading one team's source barely needs a contract independent of the code; every chapter from here on assumes the opposite: multiple stacks, clients that can't read either server's source, and a shape that has to keep working as fields and endpoints are added for years. Where those conditions hold, write the contract before the first handler, and treat a response that merely returns the right status code as unverified until a schema check (not a code review) confirms its body matches what was written down.</p></div>

## Build, run, observe

```bash
cd examples/04-contract-first && ./verify.sh
```

`verify.sh` brings both stacks up with `docker compose`, then drives create, read, list, add-cargo, replace, merge-patch, and delete calls against each one, schema-validating every response body against the shared contract. It prints `PASS` only once every assertion holds on both stacks; see `examples/04-contract-first/README.md` for the full run output.

## For deeper coverage

- Lukasz Dynowski & Marcin Dulak, *Learning API Styles* (O'Reilly, 2025): contract-first workflows across multiple API styles.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): schema design patterns for the shared types this chapter's contract defines once and references everywhere.
- [OpenAPI Specification v3.1](https://spec.openapis.org/oas/latest.html) and [JSON Schema 2020-12](https://json-schema.org/specification): the two specs `shipping-api.yaml` and `shipping.schema.json` are authored against.
- Cloud Native Design Patterns, [API registry](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/09-api-registry.md): the companion book's treatment of publishing and governing a contract as its own artifact.
- Cloud Native Design Patterns, [API metadata](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/10-api-metadata.md): describing a contract's shape and provenance beyond the schema itself.
