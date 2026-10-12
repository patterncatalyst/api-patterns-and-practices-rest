---
title: "HATEOAS"
order: 12
part: "Evolution & lifecycle"
description: "Let the response carry the links: expose exactly the state transitions valid from a resource's current state, so a client drives the booking lifecycle by following links instead of hard-coding URLs and rules."
duration: "28 min"
---

Chapter 1 named Richardson's maturity model and placed this book's contract at level 2 until the domain justified more: proper resources, proper methods, proper status codes, no hypermedia. The booking lifecycle is where that justification arrives. A booking moves through a real sequence of states — created, confirmed, loaded onto a carrier, delivered, or cancelled along the way — and which actions make sense next depends entirely on which state it's in right now. A client that wants to act correctly has to know that sequence somehow. Level 2 answers that by publishing it once, in documentation, and trusting every client to keep its own copy of the rules in sync with the server forever. Level 3 answers it by putting the rules in the response.

That's the whole payoff of hypermedia as the engine of application state: the client discovers what it can do next by reading the representation it already has, not by consulting an out-of-band contract and hoping the server hasn't changed the rules since the client was written. The server owns the state machine. It also owns the URLs that drive it — a client that follows a link never has to know the path shape, the verb, or even that the path changed between one release and the next. It asks "what can I do with this booking right now?" and the answer comes back embedded in the booking.

The shared contract fixes what a link looks like so every consumer can parse it the same way regardless of which relation it's reading: `contracts/schemas/shipping.schema.json` defines `Link` as `{href, method, title}` — `href` the URI-reference to follow, `method` the HTTP verb to use against it (defaulting to `GET`), and `title` a short human-readable label a UI can surface directly. `Links` is simply a map of relation name to `Link`, attached to `Booking` as `_links`. Carrying `method` alongside `href` matters more than it looks: without it, a client would have to know out of band that `confirm` means `POST` and `cancel` means `DELETE`, which smuggles the same hard-coded knowledge hypermedia is supposed to eliminate back in through a side door. With it, the response tells the client everything it needs to issue the request — the address and the verb both — and the client's only remaining job is deciding whether to act on the relation it's looking at.

## The response as a finite-state machine

The booking lifecycle (`_plans/domain-glossary.md`) is a small, fixed graph: a `PENDING` booking can be confirmed or cancelled; a `CONFIRMED` booking can be cancelled or moved into transit; `IN_TRANSIT` leads only to `DELIVERED`; `DELIVERED` and `CANCELLED` are terminal. Every one of those edges is a state-dependent affordance, and `_links` is the field that exposes it. Each `Booking` response carries a `_links` map — relation name to `{href, method, title}` — and the set of keys in that map is computed from nothing but the booking's current `status`:

| Status | `_links` relations | What a client can follow |
|---|---|---|
| `PENDING` | `self`, `confirm`, `cancel` | `GET` the booking, `POST` a confirmation, `DELETE` to cancel |
| `CONFIRMED` | `self`, `cancel` | `GET` the booking, `DELETE` to cancel |
| `IN_TRANSIT` | `self` | `GET` the booking only |
| `DELIVERED` | `self` | `GET` the booking only |
| `CANCELLED` | `self` | `GET` the booking only |

A client that wants to offer a "cancel booking" button doesn't ask whether cancellation is legal right now by inspecting `status` and re-implementing the state machine client-side; it checks whether the response's `_links` map has a `cancel` key. If the key is absent, there is nothing to offer, and the client never has to know why — only that this particular representation, at this particular moment, doesn't carry that affordance. The state machine lives in exactly one place, and every client that reads `_links` instead of hard-coding transition rules stays correct automatically when that one place changes.

{% include excalidraw.html file="12-hateoas-state-machine" alt="The booking finite-state machine showing PENDING transitioning via confirm to CONFIRMED and via cancel to CANCELLED, CONFIRMED transitioning via load to IN_TRANSIT and via cancel to CANCELLED, IN_TRANSIT transitioning via deliver to DELIVERED, with each state's box annotated with the exact _links relation set its response exposes: PENDING shows self, confirm, cancel; CONFIRMED shows self, cancel; IN_TRANSIT, DELIVERED and CANCELLED each show self only." caption="Figure 12.1 — The response as a finite-state machine: each state exposes only its valid links." %}

## Self links and relations that outlive the URL

Every state in that table carries `self` regardless of what else it carries. It's the one relation every hypermedia format agrees on, a link back to the exact representation the client is holding. A client that bookmarks a booking by its `self.href` rather than by reconstructing `/bookings/{id}` from a remembered id survives a path restructuring that changes how bookings are addressed, because it never built the path itself — it copied a value the server handed it. The same logic extends to `confirm` and `cancel`: a client that calls `POST` on `_links.confirm.href` with `_links.confirm.method` never needs to know that confirmation lives at `/bookings/{id}/confirmation` rather than, say, `/bookings/{id}/confirm` or a query parameter on the booking itself. The relation name is the stable contract between server and client; the URL behind it is an implementation detail the server is free to change, because the next response will carry the new one.

This is the property hypermedia advocates mean by "evolvable": not that the API never changes, but that a well-behaved client doesn't need advance notice of changes that only move URLs around. A client that hard-codes `/bookings/{id}/confirmation` has quietly taken on a dependency the contract never promised to honor long-term. A client that reads `_links.confirm.href` has taken on nothing but the relation name `confirm`, which is far cheaper to keep stable than every path in the API surface.

The same relations appear everywhere a `Booking` representation appears, not only on the single-resource endpoint. `GET /bookings` returns a `BookingCollection`, and each item in it carries its own `_links` computed from its own `status` — a `PENDING` booking sitting next to a `DELIVERED` one in the same page of results shows `confirm` and `cancel` on the first and only `self` on the second, because each item's affordances depend solely on that item's state, never on the collection it happens to be listed in. A client rendering a list of bookings reads each row's own `_links` rather than applying one blanket rule to the whole page, which is exactly the behavior a single relation vocabulary, reused consistently, is meant to make trivial.

## The cost, and when it's worth paying

None of this is free, and naming the cost matters as much as naming the benefit. Every response now carries a `_links` object the client may never read, which is extra bytes on the wire for every booking in a collection response, not just the one a client is currently acting on. It also demands client discipline that's easy to skip under deadline pressure: a client that reads `status` and reimplements the transition rules instead of checking `_links` gets the same behavior today and a silent correctness gap the moment the server's rules change — hypermedia only pays for itself when clients actually follow links instead of treating `_links` as documentation they glance at once and then ignore. And it adds a server-side obligation this chapter spends its second half on: the links have to be recomputed on every single response, because a stale link is worse than no link — it's a server actively telling a client that an illegal transition is available.

That cost is exactly why this book's contract sits at level 2 everywhere except here. A `Location` resource with a fixed set of fields and no interesting lifecycle gains nothing from `_links` — there's no state machine to expose, so the field would be overhead with no corresponding payoff. The booking is different because its lifecycle is the thing worth modeling: five states, state-dependent legal actions, and real consequences for a client that gets the rules wrong (attempting to confirm a `DELIVERED` booking, say). Reach for hypermedia when a resource's valid next actions depend on where it is in a lifecycle rich enough that out-of-band documentation can drift from reality. Stay at level 2 — proper resources, proper methods, proper status codes — everywhere else; adding `_links` to a resource with no meaningful state machine behind it is constraint for its own sake, the same mistake Chapter 2 named when picking a style the team already knows regardless of fit.

This chapter's `POST /bookings/{id}/confirmation` is a narrower endpoint than Chapter 10's, by design: it runs synchronously and returns `200` with the updated booking in the same request/response cycle, rather than the `202` → poll → `303` protocol built for a confirmation that depends on a routing check and a capacity check this service doesn't own. The two aren't in conflict — they answer different questions. Chapter 10 is about work that outlasts one request; this chapter is about which actions a representation should advertise given its current state, regardless of how long any one of those actions takes to complete. Isolating the two lets each chapter's example stay focused on the mechanism it's teaching instead of combining two orthogonal concerns into one harder-to-read handler. `/transit` and `/delivery` don't appear in the shared OpenAPI contract at all; they exist only in this chapter's example, as the minimum machinery needed to drive a booking through every state in the lifecycle and observe every shape `_links` takes.

## Computing links, not storing them

The implementation decision that makes any of this trustworthy is where `_links` gets computed. It is not a field on the stored `Booking` — the in-memory record this chapter's `BookingStore` holds never has a `_links` value at all. It's the output of a pure function that takes an id and a status and returns the relation map for exactly that status, called fresh every time a response goes out:

{% include codetabs.html langs="Quarkus|Python" %}

```java
static Map<String, Link> forBooking(String id, BookingStatus status) {
    Map<String, Link> links = new LinkedHashMap<>();
    links.put("self", new Link("/bookings/" + id, "GET", "Get this booking"));

    switch (status) {
        case PENDING -> {
            links.put("confirm", new Link("/bookings/" + id + "/confirmation", "POST", "Confirm this booking"));
            links.put("cancel", new Link("/bookings/" + id, "DELETE", "Cancel this booking"));
        }
        case CONFIRMED -> links.put("cancel", new Link("/bookings/" + id, "DELETE", "Cancel this booking"));
        case IN_TRANSIT, DELIVERED, CANCELLED -> {
            // self only — no further client-driven transition from here.
        }
    }
    return links;
}
```

```python
def links_for_booking(booking_id: str, status: BookingStatus) -> dict[str, Link]:
    links: dict[str, Link] = {
        "self": Link(href=f"/bookings/{booking_id}", method="GET", title="Get this booking"),
    }

    if status == BookingStatus.PENDING:
        links["confirm"] = Link(
            href=f"/bookings/{booking_id}/confirmation", method="POST", title="Confirm this booking"
        )
        links["cancel"] = Link(href=f"/bookings/{booking_id}", method="DELETE", title="Cancel this booking")
    elif status == BookingStatus.CONFIRMED:
        links["cancel"] = Link(href=f"/bookings/{booking_id}", method="DELETE", title="Cancel this booking")
    # IN_TRANSIT, DELIVERED, CANCELLED: self only — no further
    # client-driven transition from here.

    return links
```

Both functions take the same two inputs and return the same shape, and neither one touches a database row or a request object — a switch (or an `if`/`elif` chain) over the status enum is the entire mechanism. That simplicity is deliberate: a function this small and this pure is trivial to unit-test exhaustively against every status value, and there's no path through it that can return links inconsistent with the status it was given, because the status it was given is the only thing it looks at.

## Routing every response through the same computation

A pure function only keeps its guarantee if every response actually calls it. Both stacks enforce that by funneling every `Booking` that leaves a handler through one helper — `withLinks` on the Quarkus side, `_with_links` in FastAPI — immediately before the response is built, rather than letting any handler construct a response body by hand:

{% include codetabs.html langs="Quarkus|Python" %}

```java
private Booking withLinks(Booking booking) {
    Map<String, Link> links = HateoasLinks.forBooking(booking.id(), booking.status());
    return new Booking(
            booking.id(), booking.status(), booking.origin(), booking.destination(), booking.cargo(),
            booking.quote(), booking.requestedPickup(), booking.createdAt(), booking.updatedAt(), links);
}
```

```python
def _with_links(booking: Booking) -> Booking:
    """Computes `_links` fresh from `booking`'s CURRENT status and returns a
    copy carrying them. Every response-building call site routes through
    here rather than storing links on the Booking kept in app/store.py, so
    a transition can never leave a stale link behind.
    """
    return booking.model_copy(update={"links": links_for_booking(booking.id, booking.status)})
```

`createBooking`, `getBooking`, `listBookings`, `replaceBooking`, `patchBooking`, and the three transition endpoints (`confirmBooking`, `startTransit`, `deliverBooking`) all call `withLinks` on the booking they're about to return — never on the booking they're about to persist. The stored record stays link-free in both stacks; `_links` exists only on the copy built for the wire, computed from whatever `status` that copy currently holds. That ordering closes off the one bug class this pattern is designed to prevent: a transition that updates `status` but forgets to recompute `_links` to match. Because `_links` is never stored, there's nothing to forget — the next read computes it from the new status whether anyone remembers to or not.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>Storing <code>_links</code> alongside <code>status</code> instead of computing it on the way out reopens exactly the bug this chapter exists to close. A transition handler that updates one field and not the other produces a response that is still schema-valid — every link is a legitimate <code>{href, method, title}</code> — while asserting an affordance the booking no longer legally offers, which is a more dangerous failure than a missing field because nothing about the shape of the response reveals it. Treat <code>_links</code> as a derived view, never a column, in any resource with a lifecycle rich enough to need one.</p></div>

## Proof

```bash
cd examples/12-hateoas
./verify.sh
```

The script brings up Quarkus on port `8092` and FastAPI on port `8012`, then drives one booking through the full `PENDING → CONFIRMED → IN_TRANSIT → DELIVERED` sequence and a second through `PENDING → CANCELLED`, schema-validating every `Booking` body against `contracts/schemas/shipping.schema.json` and asserting the exact `_links` key set at every stop against both stacks. It isn't enough for a response to be schema-valid — `confirm` is a perfectly legitimate `Link` shape whether or not confirming is actually legal right now — so the assertion checks the precise set of relation names present at each state, not merely that whatever's there parses.

The example's README documents a deliberate regression to make that distinction concrete: hard-code `HateoasLinks.forBooking` (or `links_for_booking`) to always emit `confirm`, regardless of status, and re-run `verify.sh`. Every response stays schema-valid — `confirm` still matches `#/$defs/Link` — but the moment a `CONFIRMED` booking's response claims a `confirm` relation it has no business offering, the state assertion fails: `expected _links keys [cancel,self], got [cancel,confirm,self]`. That failure is the whole point of building a dedicated assertion rather than trusting schema validation alone — schema validation checks that a link looks like a link, and only a check against the state machine itself can catch a link that looks right but is lying about what's legal.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to the level-2-vs-level-3 choice. Add <code>_links</code> when a resource's evolution axis is rich — a multi-state lifecycle where the legal next actions depend on where the resource currently sits, and where client diversity means many independent clients would otherwise each re-implement (and each independently get wrong) the same transition rules. Skip it when a resource has no meaningful lifecycle, or when there's exactly one client and the team controls both ends of the contract — the payload and discipline cost buys nothing a shared library or a single documented rule wouldn't buy more cheaply. And wherever links do appear, compute them from current state on every response rather than storing them, so the server can never serve a response whose affordances have drifted from what the underlying resource actually allows.</p></div>
