---
title: "Soft deletion & GDPR purge"
order: 13
part: "Evolution & lifecycle"
description: "Delete without losing the audit trail, then erase for good under compliance: soft-delete hides a booking from normal reads while keeping it addressable for audit, and a purge honours the GDPR right to erasure."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Implement soft delete (`DELETE /bookings/{id}`) that flips `status` to `CANCELLED`, records a `DeletionAudit`, and leaves the row in place for referential integrity.
- Filter both single-resource and collection reads (`getVisible`/`get_visible`, `listVisible`/`list_visible`) from one shared predicate, so a cancelled booking can't leak through one path while hidden on another.
- Expose an audit escape hatch (`GET /bookings/{id}?includeDeleted=true`) via response headers (`X-Audit-Deleted-At`, `X-Audit-Reason`) instead of loosening the `Booking` schema's `additionalProperties: false`.
- Implement `DELETE /bookings/{id}/purge` as a distinct, unconditional GDPR-erasure path that removes both the booking and its audit entry.
- Explain why soft delete's idempotent re-`DELETE` returns `204` while a repeat purge returns `404`.

## Why this matters

Chapter 5 settled `DELETE`'s contract at the HTTP level: idempotent, `204` on success, safe to retry. It left one question unanswered: what happens to the resource underneath. For a booking, "the record disappears from the store the instant a client calls `DELETE`" is the naive answer, and it is wrong often enough to be worth a whole chapter. A booking that a customer cancels is evidence: of what was agreed, of who cancelled it and why, of a billing dispute three months from now that needs the original cargo manifest to resolve, or a carrier insurance claim that hinges on exactly when a shipment was called off. A row that vanishes on `DELETE` takes that evidence with it, and it can also leave dangling references behind (a shipment event, an invoice line, a support ticket) that pointed at an id which no longer resolves to anything. None of that is particular to bookings; it is the generic cost of hard-deleting anything a system has other reasons to remember.

That's the case for soft delete: flip a status flag instead of removing a row, so the record stays in the store for audit, for referential integrity, and for the mundane but entirely real scenario of a support agent needing to undo an accidental cancellation. It is also not the whole story, and the gap matters. Regulation like the GDPR's right to erasure draws a hard line in the opposite direction: a data subject can demand that their data actually be gone, not merely hidden behind a status check, and "we kept it for audit purposes" is not a defense against that demand once it's been invoked. A single `DELETE` endpoint can't honor both instincts at once: keep everything, and erase everything. So this chapter's example builds two different operations and spends its effort on the line between them: `DELETE /bookings/{id}`, which cancels and retains, and `DELETE /bookings/{id}/purge`, which erases without exception. Retention and erasure are not two settings on the same dial reachable by a query parameter; they are opposing policies, and conflating them into one endpoint is how a system ends up unable to prove either one.

## Soft delete: hide, don't destroy

`DELETE /bookings/{id}` in this chapter's example (`examples/13-soft-delete-purge/`) does three things, in order: flip the booking's `status` to `CANCELLED`, record a deletion audit entry capturing when and why, and leave the row itself exactly where it was. `BookingStore.softDelete` on the Quarkus side and `store.soft_delete` on the FastAPI side both do the same two writes (update the booking in place, insert into a separate audit map), and neither one calls anything resembling a delete against the underlying collection:

{% include codetabs.html langs="Quarkus|Python" %}

```java
/** Soft delete: cancel the booking in place and record why/when. */
public void softDelete(String id, Booking cancelled, String reason, String deletedAt) {
    bookings.put(id, cancelled);
    auditTrail.put(id, new DeletionAudit(deletedAt, reason));
}
```

```python
def soft_delete(booking_id: str, cancelled: Booking, reason: str, deleted_at: str) -> None:
    """Soft delete: cancel the booking in place and record why/when."""
    _bookings[booking_id] = cancelled
    _audit_trail[booking_id] = DeletionAudit(deletedAt=deleted_at, reason=reason)
```

The handler that calls this on both stacks looks up the booking with the *raw* lookup, not the one normal reads use, and that distinction is worth tracing all the way through. `store.get(id)` on Quarkus and `store.get(booking_id)` on FastAPI return a booking regardless of its current status, which means `DELETE` on an already-cancelled booking is a legal, idempotent no-op-ish re-cancel (it still returns `204`, it just re-records the audit entry) rather than a `404`. Only a booking that was never created, or one that's been purged, produces `404` from this endpoint. That's `DELETE`'s idempotency contract from Chapter 5 holding exactly where the chapter said it would: calling it twice in a row has the same observable effect on the booking's reachability as calling it once.

The same raw lookup is also what keeps referential integrity intact underneath a soft-deleted booking. `GET /bookings/{id}/cargo` and `POST /bookings/{id}/cargo` both resolve their parent through `store.get(id)`, not the filtered `getVisible`, so a cancelled booking's cargo items stay listable through that path even though the booking itself has dropped out of normal single-resource reads. That is exactly what "the row still exists" is supposed to buy: a sub-resource relationship that points at a soft-deleted parent never has to handle a parent that's quietly become unreachable, because soft delete only ever changes what a *default* caller sees, never what actually exists for anything still holding a reference to that id.

Hiding the record from normal traffic is a second, independent piece of machinery, not a side effect of the status flip. `getVisible`/`get_visible` and `listVisible`/`list_visible` both filter on `status != CANCELLED` before returning anything to a default caller: the single-resource read and the collection read enforce the same rule, and that repetition is the detail that keeps the guarantee from quietly breaking. A soft-delete feature that hides a cancelled booking from the list endpoint but still serves it from `GET /bookings/{id}` has quietly broken its own contract: a client that paginated the collection and never saw the booking, then guessed its id and asked for it directly, would get back a resource the collection told it didn't exist. Filtering both read paths from the same underlying predicate (rather than duplicating the condition and risking one of the two copies drifting) closes that gap by construction.

## Still addressable, by design

A soft-deleted booking being invisible to normal traffic is only half of what "soft" means; the other half is that it stays reachable to someone with a legitimate reason to look. `GET /bookings/{id}?includeDeleted=true` is that escape hatch. It routes to the raw `get`/`get_visible`-bypassing lookup instead of the filtered one, so a cancelled booking that `GET /bookings/{id}` 404s on comes back as a normal `200` with a full `Booking` body under the audit query parameter:

{% include codetabs.html langs="Quarkus|Python" %}

```java
Booking booking = includeDeleted ? store.get(id) : store.getVisible(id);
if (booking == null) {
    return notFound(id);
}

Response.ResponseBuilder response = Response.ok(booking);
if (includeDeleted && booking.status() == BookingStatus.CANCELLED) {
    DeletionAudit audit = store.getAudit(id);
    if (audit != null) {
        response.header("X-Audit-Deleted-At", audit.deletedAt());
        response.header("X-Audit-Reason", audit.reason());
    }
}
return response.build();
```

```python
booking = store.get(booking_id) if includeDeleted else store.get_visible(booking_id)
if booking is None:
    return _problem(404, "Booking not found", f"No booking with id {booking_id}")

headers: dict[str, str] | None = None
if includeDeleted and booking.status == BookingStatus.CANCELLED:
    audit = store.get_audit(booking_id)
    if audit is not None:
        headers = {"X-Audit-Deleted-At": audit.deletedAt, "X-Audit-Reason": audit.reason}
return _json(200, booking, headers=headers)
```

Notice where the audit trail rides: in response headers, `X-Audit-Deleted-At` and `X-Audit-Reason`, not as extra fields bolted onto the `Booking` body. That's not an arbitrary style choice: it's forced by a constraint the contract already has. `contracts/schemas/shipping.schema.json` declares `additionalProperties: false` on `Booking`, the same lockdown Chapter 7 relied on to make `PATCH` predictable: any field that shows up in a `Booking` response but isn't in the schema fails validation, for every client, on every request, deleted or not. Adding `deletedAt` and `reason` straight onto the body would mean either loosening that constraint for the one resource that happens to support soft delete (reopening the exact drift risk `additionalProperties: false` exists to close) or giving `Booking` two optional fields that are `null` on every response except the rare audit view, which is schema noise paid by every caller for a feature only the audit path uses. Headers sidestep both: they're a local, documented extension to this one response that the shared `Booking` schema never has to know about, and `validate_body Booking` in `verify.sh` keeps passing against the exact same contract on the exact same response.

This cuts both ways, and naming the cost matters as much as naming the fix. A header isn't as discoverable or as strongly typed as a schema-declared body field: a client has to know to look for `X-Audit-Deleted-At` rather than finding it enumerated in the `Booking` schema the way every other field is, and a generated SDK built straight from the OpenAPI document won't surface it as a typed property at all. A team shipping this pattern against a production system would more likely promote the audit trail to its own sub-resource, `GET /bookings/{id}/audit`, with a schema of its own that a generated client can see. That's a legitimate design this chapter's example sidesteps to keep its surface area to one endpoint; the header approach here is scoped to proving the audit trail is inspectable and gone after purge, not to being the shape every team should copy verbatim into a shipping API. The headers only appear, in both stacks, when the booking is `CANCELLED` and an audit entry exists for it: asking for `includeDeleted=true` on a booking that hasn't been deleted returns the ordinary body with no audit headers, because there's nothing yet to audit.

{% include excalidraw.html file="13-soft-delete-purge" alt="A flow diagram contrasting DELETE /bookings/{id} (soft delete), which moves a booking's status to CANCELLED, records a deletion audit entry, hides it from the default collection and single-item reads while leaving it addressable via GET ?includeDeleted=true with X-Audit-* headers, against DELETE /bookings/{id}/purge (GDPR erasure), which hard-deletes both the booking and its audit entry so that every read path, including the audit view, returns 404 afterward." caption="Figure 13.1: Soft delete keeps the audit trail; purge erases it under GDPR." %}

## Purge: the privileged override

`DELETE /bookings/{id}/purge` is a distinct, named path held apart from the soft-delete endpoint rather than folded into it as a query parameter or a header flag: one URL, one policy, no ambiguity about which rule a given request invokes. `BookingStore.purge` and `store.purge` both remove the booking from the primary map *and* its entry from the audit map, in the same call, with nothing left behind in either:

{% include codetabs.html langs="Quarkus|Python" %}

```java
/**
 * GDPR purge: hard-delete the booking AND its audit trail. Returns
 * {@code true} if a booking existed to purge (so the resource layer can
 * tell a real erasure from a 404).
 */
public boolean purge(String id) {
    boolean existed = bookings.remove(id) != null;
    auditTrail.remove(id);
    return existed;
}
```

```python
def purge(booking_id: str) -> bool:
    """GDPR purge: hard-delete the booking AND its audit trail.

    Returns True if a booking existed to purge, so the route layer can tell
    a real erasure from a 404.
    """
    existed = _bookings.pop(booking_id, None) is not None
    _audit_trail.pop(booking_id, None)
    return existed
```

The handlers wrapping this are almost suspiciously plain (look up whether the booking existed, `204` if it did, `404` if it didn't), and that plainness is itself the design statement. Purge doesn't check `status` the way soft delete's handler implicitly relies on filtered reads; a booking that's still `PENDING`, one that's already `CANCELLED`, and one sitting mid-transit are all equally purgeable, because the right to erasure a data subject invokes doesn't come with an exception for "but the booking is still in progress." It overrides retention outright rather than adding one more condition retention has to satisfy. After a purge, `GET /bookings/{id}?includeDeleted=true` (the same audit escape hatch that worked a moment earlier) now `404`s too, because the lookup it depends on, `store.get(id)`, has nothing left to return. There is no privileged view left that can still see the booking; purge doesn't narrow visibility, it removes the thing visibility was about.

That symmetry with soft delete's idempotency carries over to purge as well, and `verify.sh` checks it directly: calling purge a second time against an id that's already been purged returns `404`, not another `204`, because there is nothing left to erase the second time around. That's a meaningfully different idempotent shape than `DELETE`'s: repeat cancellation stays a `204` no-op because the booking is still there to re-cancel, while repeat purge becomes a `404` because the first call already finished the job completely. Both are idempotent in the sense Chapter 5 cares about (the *n*th call produces the same end state as the first); they just land on different status codes because "the booking is gone" and "the booking never existed" are indistinguishable once purge has run to completion.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>The example's README documents a regression worth triggering by hand: comment out the <code>auditTrail.remove(id)</code> call (or its Python equivalent) so purge removes the booking but leaves the audit entry behind. Every response a client can see still looks correct: the audit view 404s right on schedule, because <code>get</code>/<code>get_visible</code> both key off the booking map, which really is empty now. The leak is invisible from the API surface entirely; only a check against the store itself, not the client-visible response, would catch the orphaned audit record still holding a cancellation reason for a booking that's supposed to be erased. That gap is exactly where GDPR erasure bugs hide in practice: proving "the client can no longer retrieve X" is not the same proof as "X no longer exists anywhere," and a purge feature needs the second proof, not just the first.</p></div>

## Proof

```bash
cd examples/13-soft-delete-purge
./verify.sh
```

The script brings up Quarkus on port `8093` and FastAPI on port `8013`, then drives one booking through the full sequence against each stack independently: create, soft-delete, confirm it's hidden from the default collection and 404s on the default single-item read, confirm the audit view still returns it with both `X-Audit-*` headers present and correct, purge it, confirm the audit view now 404s too, and purge it again to confirm the second call also 404s rather than silently succeeding. Every `Booking` and `Problem` body along the way is schema-validated against `contracts/schemas/shipping.schema.json`, the same shared contract every other chapter's example validates against: soft delete and purge don't get a looser contract just because they're deleting things.

The two drift probes documented in the example's README are worth running once by hand, because each one demonstrates a failure mode that's easy to introduce by accident and easy to miss in review. Removing the `status != CANCELLED` filter from `listVisible`/`list_visible` leaves a cancelled booking schema-valid but visible in a collection it has no business appearing in: `verify.sh` catches it with `soft-deleted booking ... is still visible in the default GET /bookings list`, a check that plain schema validation would never fail, because the leaked booking is a perfectly good `Booking`. Leaving the audit map untouched during purge is the subtler one covered above, invisible to the client-facing assertions `verify.sh` runs, and a reminder that a test suite guarding a purge feature in production needs to assert against the store directly, not only through the API a well-behaved client would use. Both probes point at the same underlying lesson: a schema-valid response and a correctly behaving delete feature are two different claims, and only the second one is what this chapter is actually about.

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to the choice between soft-delete, hard-delete, and purge. Reach for soft delete when the evolution axis matters more than storage cost: when referential integrity, an audit trail, or plain recoverability from an accidental or disputed cancellation outweighs the overhead of a hidden row that lives on indefinitely; that's the default for anything resembling a financial or logistics record, bookings included. Reach for a true hard delete only when a resource has no downstream audience for its history at all: no audit requirement, nothing else references it, and undoing an accidental delete is not a scenario worth building for. Reach for purge specifically when an external constraint (GDPR's right to erasure, a contractual data-retention limit, a support request a compliance team has signed off on) overrides retention outright; model it as its own privileged, clearly named operation rather than a flag on the ordinary delete path, so the two policies, keep it for later, and erase it completely, never get to compete for the same endpoint's behavior. Operational constraints and client diversity both favor the same split: a purge is rare, consequential, and typically gated behind a different authorization check than an ordinary cancellation, which is one more reason it belongs on its own path rather than hidden behind a query parameter a careless client could set by accident.</p></div>

## For deeper coverage

- *Security* (Chapter 12, [Cloud Native Design Patterns](https://github.com/patterncatalyst/cloud-native-design-patterns)): the privacy-by-design and compliance concerns a purge endpoint sits inside.
- [Regulation (EU) 2016/679 (GDPR), Article 17: Right to erasure ('right to be forgotten')](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32016R0679): the legal basis for the purge endpoint this chapter builds.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): the soft-delete pattern this chapter's `DELETE`/purge split is built on.
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): retention- and deletion-adjacent resource patterns.
