---
title: "Content negotiation & status codes"
order: 6
part: "HTTP semantics done right"
description: "Serve the right representation for the client's Accept, reject the wrong Content-Type, and return status codes that mean exactly what the spec says — 406, 415, and the 2xx/4xx/409 set."
duration: "28 min"
---

Chapter 4 built the `bookings` and `cargo` surface against the contract and got the happy path right: a `POST` creates, a `GET` reads, a `PUT` replaces. What it left loose is the part of HTTP that decides what happens when a request asks for something the server was never going to give it — a representation it can't produce, a body format it won't parse, an operation that's well-formed but arrives at the wrong moment in a booking's life. Those are not edge cases to bolt on later; RFC 9110 defines them as the server's half of a negotiation, with precise status codes for each way the negotiation can fail. This chapter builds that half out: `Accept` and `Content-Type` as two different questions, `406` and `415` as the two different ways to answer "no," and the rest of the status-code set (`200`, `201` with `Location`, `204`, `400`, `404`, `409`) placed exactly where the booking domain's state machine says each one belongs.

## Two headers, two different questions

`Accept` and `Content-Type` get confused for the same thing often enough that the distinction comes first: `Accept` is the client asking "what representations will you give me back," and `Content-Type` is the client declaring "here is what this request body actually is." One governs the response, the other describes the request. A client can send `Accept: application/json` on a `GET` with no body at all — there's nothing to label — and it can send `Content-Type: application/json` on a `POST` while sending `Accept: */*`, perfectly happy to take whatever comes back. The two headers travel together on a write, but they're answering independent questions, and the server has an independent failure mode for each one.

When a server can't produce anything the client's `Accept` header will take, RFC 9110 §12.5.1 says the response is `406 Not Acceptable` — the request was fine, the server has a perfectly good resource to return, it just can't express that resource in a form this particular client declared acceptable. When a server won't parse the `Content-Type` a request body arrived with, the response is `415 Unsupported Media Type` — again, nothing wrong with the request's intent, the server simply doesn't know how to read a body labeled that way. Both are 4xx client errors in the sense that the client is the one that needs to change something, but they sit on opposite sides of the request/response boundary, and conflating them produces exactly the kind of API where a client has to guess which header to fix.

The booking API in this chapter's example narrows both directions by design. Every endpoint that returns a body produces exactly two media types — `application/json` for success and `application/problem+json` for errors — never a wildcard, and every endpoint that accepts a body consumes exactly `application/json`, except `PATCH`, which (unchanged from Chapter 5) consumes `application/merge-patch+json`. That narrowness is what makes `406` and `415` meaningful signals instead of noise: they fire exactly when a client asks for, or sends, something this particular API was never going to produce or accept, not as a generic catch-all for anything unexpected.

| Header | Client sends | Server behavior |
|---|---|---|
| `Accept` | `application/json`, `*/*`, or absent | 200/201/204, body in the default shape |
| `Accept` | `application/xml`, or anything neither JSON type satisfies | **406 Not Acceptable**, `Problem` body |
| `Content-Type` (write) | `application/json` (or `application/merge-patch+json` on `PATCH`) | request accepted, body parsed and validated |
| `Content-Type` (write) | `text/plain`, or anything the endpoint doesn't declare | **415 Unsupported Media Type**, `Problem` body |

An absent `Accept` header is not a 406 trigger — RFC 9110 §12.5.1 treats a missing header the same as `*/*`, "anything will do," so a client that never thinks about content negotiation at all gets the default representation rather than an error it never asked for. The failure mode is reserved for a client that *names* a type, and names only types the server has no way to produce.

## The status-code set, placed in the booking domain

Content negotiation is one axis of "did this request succeed." The other axis is the broader status-code vocabulary, and the booking domain is specific enough to place every member of it precisely rather than by rule of thumb.

`200 OK` is the default success code for anything that returns a representation of an existing or just-modified resource: a `GET` on a booking, a `PUT` replace, a successful `confirm` transition. `204 No Content` is for a successful operation that has nothing left to say — `DELETE /bookings/{id}` cancels the booking and returns an empty body, because there's no representation of a cancelled booking that the response needs to restate; the client already knows what it asked for. `201 Created` is the one that carries an obligation beyond the status line: RFC 9110 §15.3.2 requires that a `201` response, when the created resource has a URI, include a `Location` header pointing at it. `POST /bookings` returns `201` with `Location: /bookings/{id}` and the full `Booking` body — both the header and the body, not one or the other, because a client creating a resource needs to know both what got created and where to find it again without re-deriving the id from the body by convention.

`400 Bad Request` is for a request the server can't act on because the request itself is malformed or fails validation — a booking with no cargo items, a cargo entry missing a weight, a merge-patch document that isn't valid JSON. `404 Not Found` is for a request that's perfectly well-formed but names a resource that doesn't exist, or no longer exists in a form this operation can see — `GET /bookings/{id}` against an id nobody ever created, or against a booking that's been cancelled, which Chapter 5 already taught the store to treat as gone for every single-item read. The distinction between `400` and `404` is about *where* the problem lives: `400` says the request is broken, `404` says the request is fine but its target isn't there.

`409 Conflict` is the status this chapter spends the most care on, because it's the one most often confused with the other two. `409` means the request is well-formed and the resource exists, but the resource's *current state* makes the requested operation impossible. `POST /bookings/{id}/confirm` is the clean example: confirming a booking is a state-machine transition valid from exactly one starting state, `PENDING`. Confirming a booking that's already `CONFIRMED`, or one that's been `CANCELLED`, isn't a bad request — the confirm operation itself is entirely valid syntax against a real resource — and it isn't a missing resource either. It's a conflict between what the client is asking for and the state the resource is actually in. Returning `400` here would blame the request for something the request didn't get wrong; returning `404` would claim a booking doesn't exist when it clearly does. `409` is the code that matches what happened.

## Negotiation as annotations, negotiation as code

The two stacks implement the same negotiation rules at very different cost, and the two handlers below show that gap directly. On the Quarkus side, every resource method declares its `@Produces` and `@Consumes` media types, and RESTEasy Reactive enforces them per the JAX-RS 2.1 §3.8 content-negotiation algorithm before `BookingResource`'s code ever runs:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@POST
@Consumes(MediaType.APPLICATION_JSON)
@Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
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
            request.origin(), request.destination(),
            cargoItems, QuoteCalculator.compute(cargoItems),
            request.requestedPickup(), now, null);
    store.put(booking);

    return Response.status(Response.Status.CREATED)
            .header("Location", "/bookings/" + booking.id())
            .entity(booking)
            .build();
}
```

```python
async def _parse_json_body(request: Request) -> tuple[Any, JSONResponse | None]:
    """Parse the raw request body as JSON, returning a 400 Problem on
    failure instead of letting an unhandled JSONDecodeError 500.
    """
    try:
        return await request.json(), None
    except Exception:
        return None, _problem(400, "Invalid request body", "request body is not valid JSON")


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
    # ... build and store the booking, unchanged from Ch4/Ch5 ...
    return _json(201, booking, headers={"Location": f"/bookings/{booking.id}"})
```

If a request's `Accept` or `Content-Type` can't be satisfied by `createBooking`'s declared types, RESTEasy Reactive raises `NotAcceptableException` or `NotSupportedException` itself, and `ProblemMappers.java` turns either one into a schema-conforming `Problem` body — the negotiation logic needed no new code in the resource method, only the right annotations. FastAPI has no equivalent mechanism: a pydantic body parameter is parsed as JSON regardless of what `Content-Type` the request actually carried, and nothing in Starlette ever inspects `Accept`. `app/main.py` implements both checks by hand, `_check_accept()` and `_check_content_type()`, and calls them explicitly at the top of every handler that needs them:

```python
_PRODUCIBLE_MEDIA_TYPES = ("application/json", "application/problem+json")


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
        406, "Not Acceptable",
        "The Accept header does not match a media type this endpoint can produce "
        f"(application/json, application/problem+json); got Accept: {request.headers.get('accept', '')}",
    )


def _check_content_type(request: Request, expected: str = "application/json") -> JSONResponse | None:
    """415 guard: the request body's Content-Type must match `expected`
    exactly (ignoring any `; charset=...` parameter).
    """
    content_type = _parse_media_types(request.headers.get("content-type", ""))
    if content_type and content_type[0] == expected:
        return None
    return _problem(
        415, "Unsupported Media Type",
        f"The request's Content-Type is not one this endpoint accepts (expected {expected}); "
        f"got Content-Type: {request.headers.get('content-type') or '(none)'}",
    )
```

Same observable behavior on the wire, radically different cost on each side. Quarkus pays once, in a declaration, and the framework enforces it everywhere that declaration appears. FastAPI pays per handler, in a function call that has to be remembered at every call site — and the chapter's example README documents exactly what happens when that call gets forgotten: comment out `_check_accept(request)` in `get_booking` and the endpoint quietly starts returning `200` for an `Accept: application/xml` request that should have failed. The same mistake on the Quarkus side requires deleting an annotation element *and* removing the `NotAcceptableException` case from `ProblemMappers.java` — more code to delete, which is itself a kind of guardrail: annotation-driven negotiation fails loud (something has to be actively dismantled), hand-rolled negotiation fails quiet (a single missing function call, easy to lose in a diff).

## `application/problem+json` as the one error shape

Every error response in this chapter (`400`, `404`, `406`, `409`, `415`) comes back as `application/problem+json`, never a bare string, an empty body, or a framework's default HTML error page. RFC 9457 defines the shape: `title` (a short, human-readable summary), `status` (the same numeric code already on the status line, restated in the body so a client reading only the payload still knows what happened), and `detail` (the specifics, such as which field failed, which id was missing, or which state made the transition impossible). The contract's shared `Problem` type in `contracts/schemas/shipping.schema.json` requires only `title` and `status`, kept to that minimum: a client can always get the summary and the code, and `detail` is there when there's something more specific to say, like the exact state a `409` was raised against.

The payoff of a single error shape is uniform client code. A caller that unmarshals `Problem` once can handle `400`, `404`, `406`, `409`, and `415` with the same deserialization path, branching only on the `status` field it already has — no special-casing one endpoint's error body against another's, no distinguishing "this failure came back as JSON" from "this failure came back as an HTML stack trace because something upstream never set `Content-Type` on its 500." The `409` conflict path shows the shape doing real work, and it's the clearest side-by-side of the chapter because the state check itself is nearly identical code in both languages — only the error-construction idiom differs:

{% include codetabs.html langs="Quarkus|Python" %}

```java
@POST
@Path("/{id}/confirm")
@Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
public Response confirmBooking(@PathParam("id") String id) {
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
    if (problem := _check_accept(request)) is not None:
        return problem
    existing = store.get(booking_id)
    if existing is None:
        return _problem(404, "Booking not found", f"No booking with id {booking_id}")
    if existing.status != BookingStatus.PENDING:
        return _problem(
            409, "Conflict",
            f"Booking {booking_id} cannot be confirmed from status {existing.status.value}; "
            "only a PENDING booking can be confirmed",
        )
    confirmed = existing.model_copy(update={"status": BookingStatus.CONFIRMED, "updatedAt": _now_utc()})
    store.put(confirmed)
    return _json(200, confirmed)
```

Both handlers check existence before state — a missing booking is always `404`, even if the `id` happens to look like it could never have been `PENDING` — and both build the `409` `Problem` with the same three facts: what was asked, what state blocked it, and what state would have allowed it. That last detail isn't decoration. A client (or a person reading a log) that only gets `409 Conflict` with no `detail` has to go fetch the booking separately just to find out why; putting the current and required states in `detail` turns the error into something actionable on its own.

## Proof, not assertion

This chapter's example runs on ports `8086` (Quarkus) and `8006` (FastAPI) rather than the `8080`/`8000` every other chapter uses, so it can sit alongside the Chapter 4 and Chapter 5 stacks without a port collision:

```bash
cd examples/06-content-negotiation
./verify.sh
```

`verify.sh` brings both services up with `docker compose`, waits for health, then drives the full negotiation and status-code table against both: a `201` with `Location` and a schema-valid `Booking` body on create; `415` against a `text/plain` body on the same endpoint; `406` against `Accept: application/xml` on a read; a `confirm` → `200`, then the identical `confirm` call again → `409`, checking both the status and that the `Problem` body's `detail` names the blocking state; and a `DELETE` → `404`-on-retry sequence carried over from Chapter 5. It schema-validates every response against `contracts/schemas/shipping.schema.json` and prints `PASS` only when every assertion holds on **both** stacks — a `200` where a `406` belongs fails the run immediately, with the exact expected-versus-actual status printed, the same way a contract-drift probe failed loud in Chapter 4.

The README's drift probe makes the point concrete: disable `_check_accept()` in `get_booking` and the FastAPI service starts returning `200` for an unsatisfiable `Accept` header, which `verify.sh` catches as `FAIL — python GET /bookings/{id} (Accept: application/xml): expected HTTP 406, got 200`. Revert it and the run goes back to green. That failure mode is exactly what a code review easily misses and a schema-aware integration test never does — a status code is a one-line change to get wrong, and this chapter's whole claim is that getting it right is worth verifying, not assuming.

{% include excalidraw.html file="06-content-negotiation" alt="A request's Accept and Content-Type headers are checked against what the matched endpoint can produce and consume, branching to a 200/201/204 success response when both are satisfied or to a 406/415 Problem response when either is not, alongside a separate status-code map showing 400 for a malformed request, 404 for a missing resource, and 409 for a well-formed request against a resource in the wrong state." caption="Figure 6.1 — Negotiation outcomes and the status-code map." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to representation and status-code choices. When a resource can truly be served in more than one shape, declare every shape explicitly in <code>Accept</code>/<code>Content-Type</code> handling rather than defaulting to a wildcard that silently accepts anything — a narrow declaration is what makes <code>406</code> and <code>415</code> meaningful signals instead of dead code nobody can trigger. When a write succeeds and creates a new resource, return <code>201</code> with <code>Location</code>, never a bare <code>200</code> — a client that has to re-derive the new resource's URI from convention is a client the contract failed to serve. When an operation fails because of the resource's current state rather than a bad request or a missing target, reach for <code>409</code> specifically, and put the current and required states in the <code>Problem</code> body's <code>detail</code> — a conflict a caller can't diagnose from the response alone is barely better than a bare <code>500</code>. And treat a framework's automatic negotiation (Quarkus's <code>@Produces</code>/<code>@Consumes</code>) and a hand-rolled equivalent (FastAPI's explicit guards) as carrying the same obligation despite the cost difference: the status code a client receives has to be identical either way, and only a behavioral <code>verify.sh</code> — not a glance at the annotations — proves that it is.</p></div>
