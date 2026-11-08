---
title: "HATEOAS"
order: 12
part: "Evolution & lifecycle"
description: "Let the response carry the links: expose exactly the state transitions valid from a resource's current state, so a client drives the booking lifecycle by following links instead of hard-coding URLs and rules."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Compute a `_links` map (`self`, `confirm`, `cancel`) from a booking's current `status`, so a client discovers legal next actions from the representation.
- Model a hypermedia link as `{href, method, title}` so a client never needs a verb or a path out of band.
- Route every response through one `withLinks`/`_with_links` helper so `_links` can't drift from the resource it describes.
- Decide when a resource's lifecycle justifies Richardson maturity level 3 and when level 2 is the better default.
- Treat `_links` as a derived view computed at read time, never a stored column.

## Why this matters

At Richardson level 2 a booking has proper resources, methods and status codes, and no hypermedia. A booking also moves through a real sequence of states (created, confirmed, in transit, delivered, or cancelled along the way), and which action makes sense next depends on the state it's in now. Level 2 publishes that sequence once, in documentation, and trusts every client to keep its own copy of the rules in sync. Level 3 puts the rules in the response.

The server owns the state machine and the URLs that drive it. A client that follows a link never needs the path shape, the verb, or that the path moved between releases. It asks "what can I do with this booking right now?" and the booking answers.

The shared contract fixes what a link looks like. `Link` is `{href, method, title}`: the URI-reference to follow, the HTTP verb to use (default `GET`), and a short label a UI can show. `Links` maps a relation name to a `Link` and attaches to `Booking` as `_links`. Carrying `method` next to `href` matters: without it a client must know out of band that `confirm` is a `POST` and `cancel` a `DELETE`, which brings the hard-coded knowledge back through a side door.

## The response as a finite-state machine

A `PENDING` booking can be confirmed or cancelled. A `CONFIRMED` booking can be cancelled or moved into transit. `IN_TRANSIT` leads only to `DELIVERED`. `DELIVERED` and `CANCELLED` are terminal. The keys of `_links` are computed from `status` alone:

| Status | `_links` relations | What a client can follow |
|---|---|---|
| `PENDING` | `self`, `confirm`, `cancel` | `GET` the booking, `POST` a confirmation, `DELETE` to cancel |
| `CONFIRMED` | `self`, `cancel` | `GET` the booking, `DELETE` to cancel |
| `IN_TRANSIT` | `self` | `GET` the booking only |
| `DELIVERED` | `self` | `GET` the booking only |
| `CANCELLED` | `self` | `GET` the booking only |

A client that offers a "cancel booking" button checks whether `_links` has a `cancel` key. It doesn't inspect `status` and re-implement the state machine. If the key is absent there is nothing to offer, and the client never needs to know why. The rules live in one place, and every client that reads `_links` stays correct when that place changes.

{% include excalidraw.html file="12-hateoas-state-machine" alt="The booking finite-state machine: PENDING moves via confirm to CONFIRMED and via cancel to CANCELLED, CONFIRMED moves via load to IN_TRANSIT and via cancel to CANCELLED, IN_TRANSIT moves via deliver to DELIVERED. Each state's box lists the _links relations its response exposes: PENDING shows self, confirm, cancel; CONFIRMED shows self, cancel; IN_TRANSIT, DELIVERED and CANCELLED show self only." caption="Figure 12.1: The response as a finite-state machine: each state exposes only its valid links." %}

## Relations that outlive the URL

Every state carries `self`, a link back to the representation the client holds. A client that bookmarks `self.href` instead of rebuilding `/bookings/{id}` survives a change to how bookings are addressed. The same holds for `confirm` and `cancel`: a client that calls `POST` on `_links.confirm.href` never needs to know that confirmation lives at `/bookings/{id}/confirmation`. The relation name is the stable contract and the URL behind it is the server's to change, because the next response carries the new one. That is what "evolvable" means here: not that the API never changes, but that a client needs no advance notice of a change that only moves URLs. A client that hard-codes the path has taken on a dependency the contract never promised; one that reads `_links.confirm.href` depends only on the name `confirm`, which is far cheaper to keep stable.

The same relations appear wherever a `Booking` appears. Each item in a `BookingCollection` carries `_links` computed from its own `status`: a `PENDING` booking next to a `DELIVERED` one shows `confirm` and `cancel` on the first and only `self` on the second. A client renders each row from that row's links, with no blanket rule for the page.

## The cost, and when to pay it

Every response carries a `_links` object the client may never read, for every booking in a collection. Clients also need discipline: one that reads `status` and re-implements the rules behaves the same today and breaks silently when the server's rules change. Hypermedia pays only when clients follow the links.

| Resource | Level | Why |
|---|---|---|
| Booking | 3 | Five states, state-dependent actions, real cost when a client gets the rules wrong |
| `Location` and other fixed-field resources | 2 | No state machine to expose, so `_links` is overhead |

Use level 3 when a resource's valid next actions depend on a lifecycle rich enough that out-of-band documentation can drift from reality, and when many independent clients would otherwise each re-implement the rules. Stay at level 2 for a resource with no lifecycle, or when one team controls both ends of the contract and a shared library is cheaper.

The `POST /bookings/{id}/confirmation` here runs synchronously and returns `200` with the updated booking. That's separate from a long-running confirmation that returns `202`, a poll and `303`: this pattern is about which actions a representation advertises, whatever time each takes. Keeping them apart keeps each handler about one mechanism. `/transit` and `/delivery` aren't in the shared OpenAPI contract at all; they exist only as the minimum machinery to drive a booking through every state and observe every shape `_links` takes.

## Computing links, not storing them

A booking's `status` changes, and `_links` has to change with it. If `_links` is stored beside `status`, a transition handler that updates one field and forgets the other produces a response that is still schema-valid, since every link is a legitimate `{href, method, title}`, yet offers an action the booking no longer allows. Nothing in the shape of the response reveals it. So `_links` is computed from the current status on every response and never stored.

The relation map is a pure function of an id and a status, a switch over the status enum and nothing else:

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
            // self only; no further client-driven transition from here.
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
    # IN_TRANSIT, DELIVERED, CANCELLED: self only; no further
    # client-driven transition from here.

    return links
```

The function touches no database row and no request, so it is trivial to test against every status, and it can't return links inconsistent with the status it was given. The stored `Booking` never has a `_links` value. Every `Booking` that leaves a handler goes through one helper, built just before the response:

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
    a transition can never leave a stale link behind. Mirrors
    ../quarkus/.../BookingResource.java#withLinks.
    """
    return booking.model_copy(update={"links": links_for_booking(booking.id, booking.status)})
```

Create, get, list, replace, patch and the three transition endpoints (`confirmBooking`, `startTransit`, `deliverBooking`) all call the helper on the booking they return, never on the one they persist. `_links` exists only on the copy built for the wire. Because `_links` is never stored, there is nothing to forget: the next read computes it from the new status.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>A stale link is more dangerous than a missing one, because it tells the client an illegal transition is available. Treat <code>_links</code> as a derived view, never a column.</p></div>

## When not to use it

Skip `_links` on a resource with no lifecycle, and when one team owns both client and server. The payload and the discipline buy nothing a shared library or one documented rule wouldn't buy more cheaply. Where links do appear, compute them from current state on every response.

> **🤖 Explore with your agent**
>
> "In examples/12-hateoas, add a `hold` transition to the booking: `POST /bookings/{id}/hold` moves a `CONFIRMED` booking to a new `ON_HOLD` status that can only be released back to `CONFIRMED` or cancelled. Update `HateoasLinks.forBooking` and `links_for_booking` so `_links` offers `hold`, `release` and `cancel` only in the states where they are legal, keep `_links` out of the stored `Booking`, and route the new endpoint through `withLinks`/`_with_links`."
>
> Check: `GET /bookings/{id}` on a `CONFIRMED` booking shows a `hold` link, an `ON_HOLD` booking shows `release` and `cancel` and no `hold`, and the stored record has no `_links` field.

## Build, run, observe

```bash
cd examples/12-hateoas && ./verify.sh
```

The script starts Quarkus on port 8092 and FastAPI on port 8012, drives one booking through `PENDING`, `CONFIRMED`, `IN_TRANSIT` and `DELIVERED` and a second through cancellation, and prints `PASS` when the `_links` keys match the table at every state on both stacks. Schema validation alone isn't enough, since `confirm` is a valid `Link` whether or not confirming is legal.

- Change `forBooking` (or `links_for_booking`) to always emit `confirm`. Every response stays schema-valid, and the run fails on a `CONFIRMED` booking: `expected _links keys [cancel,self], got [cancel,confirm,self]`.

## For deeper coverage

- *Versioning & Evolution* (Appendix B, [Cloud Native Design Patterns](https://github.com/patterncatalyst/cloud-native-design-patterns)): the evolve-without-breaking-clients stance that hypermedia links provide by default.
- [RFC 8288: Web Linking](https://www.rfc-editor.org/rfc/rfc8288): the standard notion of a typed link relation that `_links` specializes.
- Leonard Richardson & Mike Amundsen, *RESTful Web APIs* (O'Reilly, 2013): the Richardson maturity model and hypermedia as the engine of application state.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): resource relationship patterns adjacent to hypermedia-driven navigation.
