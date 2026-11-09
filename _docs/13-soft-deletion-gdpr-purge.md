---
title: "Soft deletion & GDPR purge"
order: 13
part: "Evolution & lifecycle"
description: "Delete without losing the audit trail, then erase for good under compliance: soft delete hides a booking from normal reads while keeping it addressable for audit, and a purge honors the GDPR right to erasure."
duration: "28 min"
---

## Learning objectives

By the end of this chapter you can:

- Implement soft delete (`DELETE /bookings/{id}`) that flips `status` to `CANCELLED`, records a `DeletionAudit`, and leaves the row in place.
- Filter single-resource and collection reads (`getVisible`/`get_visible`, `listVisible`/`list_visible`) from one shared predicate, so a cancelled booking can't leak through one path while hidden on another.
- Expose an audit escape hatch (`GET /bookings/{id}?includeDeleted=true`) through response headers (`X-Audit-Deleted-At`, `X-Audit-Reason`) instead of loosening the `Booking` schema.
- Implement `DELETE /bookings/{id}/purge` as a separate, unconditional erasure path that removes both the booking and its audit entry.
- Explain why a repeat soft delete returns `204` and a repeat purge returns `404`.

## Why this matters

`DELETE` is idempotent, returns `204` and is safe to retry. That says nothing about what happens to the resource underneath. If the record vanishes the instant a client calls `DELETE`, the system loses evidence: what was agreed, who cancelled and why, the cargo manifest a billing dispute needs three months later. It can also leave dangling references, such as a shipment event, an invoice line or a support ticket that point at an id which no longer resolves.

Soft delete flips a status flag instead of removing the row. The record stays for audit, for referential integrity, and for the support agent who needs to undo an accidental cancellation.

Regulation pulls the other way. Under the GDPR right to erasure a data subject can demand that data be erased, not masked by a status check, and "we kept it for audit" is no defense once the demand is made. One `DELETE` endpoint can't keep everything and erase everything. Retention and erasure are opposing policies, not two settings on one dial, so they get two endpoints: `DELETE /bookings/{id}` cancels and retains, and `DELETE /bookings/{id}/purge` erases.

## Pattern: Soft delete

### The problem

A hard delete destroys the audit trail and breaks references. A soft delete that hides the row from the list endpoint but still serves it from `GET /bookings/{id}` breaks its own contract: a client that paged the collection and never saw the booking guesses its id and gets back a resource the collection said didn't exist.

### The solution

**Mark the record deleted instead of removing it, hide it from default reads through one shared predicate, and keep it reachable for callers with a reason to look.**

### How Quarkus and FastAPI model it

`DELETE /bookings/{id}` flips the booking to `CANCELLED`, records when and why in a separate audit map, and removes nothing:

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

The handler finds the booking with the raw lookup, which returns it whatever its status. A `DELETE` on an already-cancelled booking therefore re-cancels, re-records the audit entry and returns `204`. Only an id that never existed, or one that was purged, returns `404`.

Child resources use the raw lookup too. `GET` and `POST` on `/bookings/{id}/cargo` resolve their parent with it, so a cancelled booking's cargo stays listable. Soft delete changes what a default caller sees, never what exists for anything still holding the id.

Hiding is separate machinery from the status flip. Both `getVisible`/`get_visible` and `listVisible`/`list_visible` filter on `status != CANCELLED` before returning anything to a default caller. The single-resource read and the collection read must enforce the same rule from one predicate, so one copy can't drift from the other.

### Still addressable, by design

`GET /bookings/{id}?includeDeleted=true` takes the raw lookup instead of the filtered one. A cancelled booking that the plain `GET` answers with `404` comes back as `200` with a full `Booking` body:

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

The audit trail rides in headers because `Booking` declares `additionalProperties: false`. Adding `deletedAt` and `reason` to the body would mean either loosening that constraint for one resource or giving every caller two optional fields that are `null` except in the rare audit view. Headers extend this one response and leave the shared schema alone. The audit headers appear only when the booking is `CANCELLED` and an audit entry exists.

| Option | Trade-off |
|---|---|
| Response headers | No schema change, but not typed or discoverable, and a generated SDK won't surface them |
| `GET /bookings/{id}/audit` sub-resource | Own schema a generated client can see, one more endpoint |

A production API would likely promote the audit trail to its own sub-resource. Headers avoid the extra endpoint.

{% include excalidraw.html file="13-soft-delete-purge" alt="A flow diagram contrasting DELETE /bookings/{id} (soft delete), which moves a booking's status to CANCELLED, records a deletion audit entry, hides it from the default collection and single-item reads while leaving it addressable via GET ?includeDeleted=true with X-Audit-* headers, against DELETE /bookings/{id}/purge (GDPR erasure), which hard-deletes both the booking and its audit entry so that every read path, including the audit view, returns 404 afterward." caption="Figure 13.1: Soft delete keeps the audit trail; purge erases it under GDPR." %}

## Purge: the privileged override

A data subject invokes the right to erasure, and "the booking is hidden" doesn't satisfy it. The audit entry, which holds a cancellation reason, has to go as well. Erasure gets its own named, privileged endpoint that removes the record and its audit trail, whatever the record's status.

`DELETE /bookings/{id}/purge` is a separate URL, not a query parameter or header flag on soft delete: one URL, one policy. Both stacks remove the booking and its audit entry in one call:

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

The handler returns `204` if the booking existed and `404` if not. It checks no status: a `PENDING`, a `CANCELLED` and an in-transit booking are all purgeable, because the right to erasure has no exception for work in progress. After a purge, `GET /bookings/{id}?includeDeleted=true` returns `404` too. No privileged view remains, because the thing visibility was about is gone.

A repeat purge returns `404`, where a repeat soft delete returns `204`. Both are idempotent, since the *n*th call leaves the same end state as the first. A repeat soft delete finds a booking to re-cancel. A repeat purge finds nothing, because the first call finished the job, and "gone" and "never existed" look the same.

<div class="callout callout--warn"><p class="callout__title">Gotcha</p><p>If purge removes the booking but leaves the audit entry, every client-visible response still looks right: the audit view returns <code>404</code> because the booking map is empty. The leak is invisible from the API, with a cancellation reason sitting in the store for a booking that was supposed to be erased. Proving the client can't retrieve the data is not proving the data no longer exists.</p></div>

## When not to use it

| Situation | Choice |
|---|---|
| Financial or logistics record, audit or recovery matters | Soft delete (the default for bookings) |
| No audience for the history, nothing references it, no undo needed | Hard delete |
| GDPR erasure, contractual retention limit, signed-off compliance request | Purge, as its own endpoint |

A purge is rare, consequential and usually gated behind a different authorization check than a cancellation. That is one more reason it gets its own path, where a careless client can't switch it on with a query parameter.

> **🤖 Explore with your agent**
>
> "In examples/13-soft-delete-purge, review `DELETE /bookings/{id}`, `GET /bookings/{id}?includeDeleted=true` and `DELETE /bookings/{id}/purge` on both stacks. Find any read path that returns a `CANCELLED` booking by default, or any purge path that leaves an entry in the audit map. Then add `GET /bookings/{id}/audit`, return the `DeletionAudit` there, and make it `404` after a purge."
>
> Check: soft-delete a booking, then `GET /bookings` must not list it and `GET /bookings/{id}/audit` must return the reason; after `DELETE /bookings/{id}/purge`, the audit endpoint must return `404`.

## Build, run, observe

```bash
cd examples/13-soft-delete-purge && ./verify.sh
```

The script starts Quarkus on port 8093 and FastAPI on port 8013 and, on each stack, creates a booking, soft-deletes it, purges it and purges it again. It prints `PASS` when the cancelled booking is hidden from the default list and single read, the audit view returns it with both `X-Audit-*` headers, and the audit view and a second purge both return `404`.

- Remove the `status != CANCELLED` filter from `listVisible`/`list_visible`. The leaked booking is still a valid `Booking`, and the run fails: `soft-deleted booking ... is still visible in the default GET /bookings list`.
- Delete the `auditTrail.remove(id)` line (or its Python equivalent). The API still looks correct, so only a check against the store catches the orphaned audit entry.

## For deeper coverage

- *Security* ([Cloud Native Design Patterns](https://github.com/patterncatalyst/cloud-native-design-patterns)): the privacy-by-design and compliance concerns a purge endpoint sits inside.
- [Regulation (EU) 2016/679 (GDPR), Article 17: Right to erasure ('right to be forgotten')](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex%3A32016R0679): the legal basis for the purge endpoint.
- J. J. Geewax, *API Design Patterns* (Manning, 2021): the soft-delete pattern behind the `DELETE`/purge split.
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): retention- and deletion-adjacent resource patterns.
