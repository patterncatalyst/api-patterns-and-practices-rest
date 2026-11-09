---
title: "Content negotiation & status codes"
order: 6
part: "HTTP semantics done right"
description: "Serve the representation the client's Accept names, reject the wrong Content-Type, and return the status code the spec defines: 406, 415, and the 2xx, 4xx and 409 set."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Distinguish `Accept` (what the client will take back) from `Content-Type` (what the client is sending), and map each failure to its status code (`406` vs. `415`).
- Enforce content negotiation declaratively with `@Produces`/`@Consumes` on Quarkus, and by hand with `_check_accept()`/`_check_content_type()` on FastAPI.
- Place `200`, `201` (with `Location`), `204`, `400`, `404` and `409` against the booking domain's state machine.
- Explain why `POST /bookings/{id}/confirm` against an already-`CONFIRMED` booking returns `409`, not `400` or `404`.
- Return every error as an `application/problem+json` `Problem` body with `title`, `status` and a `detail` that names the blocking state.

## Why this matters

A request can fail without being wrong in any way the client controls casually: it asks for a representation the server can't produce, sends a body format the server won't parse, or names a valid operation at the wrong moment in a booking's life. RFC 9110 gives each failure its own status code. A client that gets the right code knows which header, field or precondition to change. A client that gets a vague one has to guess.

## Two headers, two questions

`Accept` is the client asking which representations it will take back. `Content-Type` declares what the request body is. One governs the response and the other describes the request, and each has its own failure.

- **`406 Not Acceptable`** (RFC 9110 §12.5.1): the resource exists, but the server can't express it in any form the `Accept` header allows.
- **`415 Unsupported Media Type`**: the server won't parse a body labeled with that `Content-Type`.

Conflating them leaves a client guessing which header to fix.

The booking API keeps both directions narrow. Every endpoint that returns a body produces exactly `application/json` for success and `application/problem+json` for errors. Every endpoint that accepts a body consumes `application/json`, except `PATCH`, which consumes `application/merge-patch+json`. Narrow declarations make `406` and `415` signals that fire only when a client asks for or sends something the API never handles.

| Header | Client sends | Server behavior |
|---|---|---|
| `Accept` | `application/json`, `*/*`, or absent | 200, 201 or 204, body in the default shape |
| `Accept` | `application/xml`, or anything neither JSON type satisfies | **406**, `Problem` body |
| `Content-Type` (write) | `application/json` (`application/merge-patch+json` on `PATCH`) | Body parsed and validated |
| `Content-Type` (write) | `text/plain`, or anything the endpoint doesn't declare | **415**, `Problem` body |

An absent `Accept` header is not a `406`. RFC 9110 §12.5.1 treats it as `*/*`, so a client that never thinks about negotiation gets the default representation. `406` is reserved for a client that names types and names only ones the server can't produce.

## The status codes in the booking domain

| Code | Use in the booking API |
|---|---|
| `200 OK` | A representation of an existing or just-modified resource: `GET`, `PUT`, a successful `confirm` |
| `201 Created` | `POST /bookings`, with `Location: /bookings/{id}` **and** the full `Booking` body |
| `204 No Content` | `DELETE /bookings/{id}`: the cancellation has nothing left to restate |
| `400 Bad Request` | The request is malformed or fails validation: no cargo items, a cargo entry with no weight, invalid merge-patch JSON |
| `404 Not Found` | The request is well formed but its target doesn't exist, or is cancelled and so treated as gone |
| `409 Conflict` | The request is well formed and the resource exists, but its current state makes the operation impossible |

RFC 9110 §15.3.2 expects a `201` for a created resource with a URI to carry a `Location` header. The body tells the client what got created and `Location` tells it where, so it never derives the id by convention.

`400` and `404` differ in where the problem lives: the request is broken, or the request is fine and its target isn't there. `409` is the one most often confused with both. Confirming a booking is a transition valid from exactly one state, `PENDING`. Confirming one that is already `CONFIRMED` or `CANCELLED` is valid syntax against a real resource, so `400` would blame the request for nothing it got wrong and `404` would claim the booking doesn't exist. The request conflicts with the resource's state, and `409` says so.

## Negotiation as annotations, negotiation as code

Quarkus declares the types on each resource method with `@Produces` and `@Consumes`, and RESTEasy Reactive enforces them with the JAX-RS content-negotiation algorithm before resource code runs. An unsatisfiable `Accept` or `Content-Type` raises `NotAcceptableException` or `NotSupportedException`, and `ProblemMappers.java` turns either into a `Problem` body. The resource method needs no negotiation code. FastAPI has no equivalent: a pydantic body parameter is parsed as JSON whatever `Content-Type` arrived, and Starlette never inspects `Accept`. The FastAPI handler takes the raw `Request` and calls the guards itself, then parses and validates the body:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@POST
@Consumes(MediaType.APPLICATION_JSON)
@Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
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
async def create_booking(request: Request) -> JSONResponse:
    if (problem := _check_content_type(request)) is not None:
        return problem
    if (problem := _check_accept(request)) is not None:
        return problem

    raw, problem = await _parse_json_body(request)
    if problem is not None:
        return problem
    try:
        payload = BookingRequest.model_validate(raw)
    except ValidationError as exc:
        return _problem(400, "Invalid booking request", str(exc.errors()))

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

The two guards in `app/main.py`:

```python
def _check_accept(request: Request) -> JSONResponse | None:
    """406 guard: an absent/empty Accept header means "anything" (RFC 9110
    §12.5.1), so only a header that NAMES types and excludes every type this
    API can produce is a conflict.
    """
    accepted = _parse_media_types(request.headers.get("accept", ""))
    if not accepted:
        return None
    for media_type in accepted:
        if media_type in ("*/*", "application/*") or media_type in _PRODUCIBLE_MEDIA_TYPES:
            return None
    return _problem(
        406,
        "Not Acceptable",
        "The Accept header does not match a media type this endpoint can produce "
        f"(application/json, application/problem+json); got Accept: {request.headers.get('accept', '')}",
    )


def _check_content_type(request: Request, expected: str = "application/json") -> JSONResponse | None:
    """415 guard: the request body's Content-Type must match `expected`
    exactly (ignoring any ``; charset=...`` parameter); a body sent with
    the wrong media type never reaches the pydantic parser.
    """
    content_type = _parse_media_types(request.headers.get("content-type", ""))
    if content_type and content_type[0] == expected:
        return None
    return _problem(
        415,
        "Unsupported Media Type",
        f"The request's Content-Type is not one this endpoint accepts (expected {expected}); "
        f"got Content-Type: {request.headers.get('content-type') or '(none)'}",
    )
```

Quarkus pays once, in a declaration the framework enforces wherever it appears. FastAPI pays per handler, with a call that must be remembered at every site. Comment out `_check_accept(request)` in `get_booking` and the endpoint quietly returns `200` to `Accept: application/xml`. Breaking the Quarkus side means deleting an annotation element and removing the `NotAcceptableException` case from `ProblemMappers.java`. Annotation-driven negotiation fails loudly because something must be dismantled. Hand-rolled negotiation fails quietly because one missing call is easy to lose in a diff.

{% include excalidraw.html file="06-content-negotiation" alt="A request's Accept and Content-Type headers are checked against what the matched endpoint can produce and consume, branching to a 200/201/204 success response when both are satisfied or to a 406/415 Problem response when either is not, alongside a separate status-code map showing 400 for a malformed request, 404 for a missing resource, and 409 for a well-formed request against a resource in the wrong state." caption="Figure 6.1: Negotiation outcomes and the status-code map." %}

## `application/problem+json` as the one error shape

Every error (`400`, `404`, `406`, `409`, `415`) comes back as `application/problem+json`, never a bare string, an empty body or a framework's HTML error page. RFC 9457 defines the shape:

- `title`: a short summary.
- `status`: the numeric code from the status line, restated so a client reading only the payload still has it.
- `detail`: the specifics, such as which field failed, which id was missing or which state blocked the transition.

The shared `Problem` type in `contracts/schemas/shipping.schema.json` requires only `title` and `status`. A caller that unmarshals `Problem` once handles every error through the same path and branches on `status`.

The `409` path shows the shape at work. The state check is nearly identical in both languages and only the error-construction idiom differs:

{% include codetabs.html langs="Quarkus|Python" %}

```java
/**
 * 409 Conflict path: confirming a booking is only valid from
 * {@code PENDING}: confirming it twice, or confirming one that's
 * already cancelled/in transit/delivered, is a state conflict, not a
 * validation error (the request is well-formed; the resource just
 * isn't in a state that allows it). This rounds out the status-code
 * table: 200 on success, 404 if the booking doesn't exist, 409 if it
 * exists but is in the wrong state.
 */
@POST
@Path("/{id}/confirm")
@Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
public Response confirmBooking(@RestPath String id) {
    Booking existing = store.get(id);
    if (existing == null) {
        return notFound(id);
    }
    if (existing.status() != BookingStatus.PENDING) {
        return problem(409, "Conflict",
                "Booking " + id + " cannot be confirmed from status " + existing.status()
                        + "; only a PENDING booking can be confirmed");
    }
    Booking confirmed = new Booking(
            existing.id(), BookingStatus.CONFIRMED, existing.origin(), existing.destination(),
            existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(), nowUtc());
    store.put(confirmed);
    return Response.ok(confirmed).build();
}
```

```python
@app.post("/bookings/{booking_id}/confirm")
def confirm_booking(booking_id: str, request: Request) -> JSONResponse:
    """409 Conflict path: confirming a booking is only valid from PENDING:
    confirming it twice, or confirming one that's already
    cancelled/in-transit/delivered, is a state conflict, not a validation
    error (the request is well-formed; the resource just isn't in a state
    that allows it). This rounds out the status-code table: 200 on success,
    404 if the booking doesn't exist, 409 if it exists but is in the wrong
    state. Mirrors Quarkus's confirmBooking.
    """
    if (problem := _check_accept(request)) is not None:
        return problem
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    if existing.status != BookingStatus.PENDING:
        return _problem(
            409,
            "Conflict",
            f"Booking {booking_id} cannot be confirmed from status {existing.status.value}; "
            "only a PENDING booking can be confirmed",
        )
    confirmed = existing.model_copy(update={"status": BookingStatus.CONFIRMED, "updatedAt": _now_utc()})
    store.put(confirmed)
    return _json(200, confirmed)
```

Both handlers check existence before state, so a missing booking is always `404`. Both build the `409` `detail` from the same facts: what was asked, what state blocked it and what state would allow it. Without that, a client with only `409 Conflict` has to fetch the booking to learn why.

## Choosing the code

| Situation | Return |
|---|---|
| A resource can be served in several shapes | Declare each one explicitly; a wildcard makes `406` and `415` unreachable |
| A write creates a resource | `201` with `Location`, never a bare `200` |
| Failure comes from the resource's current state | `409`, with the current and required states in `detail` |
| Negotiation is hand-rolled | The same status as the annotated stack; confirm it with a behavioral check |

> **🤖 Explore with your agent**
>
> "In `examples/06-content-negotiation/`, add `POST /bookings/{id}/load` on both the Quarkus and FastAPI stacks, following `confirmBooking` and `confirm_booking`. It moves a `CONFIRMED` booking to `IN_TRANSIT` and returns `200`, returns `409` with a `Problem` whose `detail` names the current and required states from any other state, `404` for an unknown id, and `406` to `Accept: application/xml`."
>
> Check: confirm a booking, then call `load` twice with `curl -i`. The first returns `200` and the second returns `409` with `Content-Type: application/problem+json`.

## Build, run, observe

```bash
cd examples/06-content-negotiation && ./verify.sh
```

These stacks run on ports `8086` (Quarkus) and `8006` (FastAPI), so they can sit beside the other examples. The script drives the negotiation and status-code table against both stacks, schema-validates every body and prints `PASS` when both agree. `examples/06-content-negotiation/README.md` has the full output.

Experiments:

- Disable `_check_accept()` in `get_booking`. The FastAPI service returns `200` for an unsatisfiable `Accept`, and the run fails with `expected HTTP 406, got 200`.
- Return `400` instead of `409` from a repeated `confirm` in either stack. The run fails on that stack's second `confirm`.

## For deeper coverage

- [RFC 9110 §12, HTTP Semantics: Content Negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#section-12): `Accept`, `Content-Type` and the `406` and `415` status codes.
- [RFC 9457, Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): the `application/problem+json` shape every error returns.
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): status-code selection patterns, including `409` versus `400` versus `404`.
- Cloud Native Design Patterns, [Appendix E: Errors](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/18-appendix-e-errors.md): error representation across API styles.
- Cloud Native Design Patterns, [Appendix A: Protocols](https://github.com/patterncatalyst/cloud-native-design-patterns/blob/main/_docs/14-appendix-a-protocols.md): HTTP status-code semantics as a protocol-level reference.
