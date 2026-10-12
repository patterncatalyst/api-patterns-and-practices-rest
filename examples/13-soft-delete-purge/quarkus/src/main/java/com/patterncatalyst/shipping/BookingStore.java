package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.DeletionAudit;
import jakarta.enterprise.context.ApplicationScoped;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * In-memory booking store. Deterministic and fast on purpose — this
 * chapter's job is proving request/response shapes against the contract,
 * not persistence (Ch13 extends the Ch4 anchor; Postgres shows up once an
 * example needs it).
 *
 * Soft delete (`DELETE /bookings/{id}`) flips `status` to `CANCELLED` and
 * records a {@link DeletionAudit} entry — the booking and its audit trail
 * both stay in {@code bookings}/{@code auditTrail}, just hidden from the
 * default read paths. Purge (`DELETE /bookings/{id}/purge`) is the GDPR
 * "right to erasure" escape hatch: it removes BOTH maps' entries for that
 * id, so even the audit view has nothing left to find.
 */
@ApplicationScoped
public class BookingStore {

    private final Map<String, Booking> bookings = Collections.synchronizedMap(new LinkedHashMap<>());
    private final Map<String, DeletionAudit> auditTrail = Collections.synchronizedMap(new LinkedHashMap<>());

    public void put(Booking booking) {
        bookings.put(booking.id(), booking);
    }

    /** Raw lookup — returns a cancelled (soft-deleted) booking too. Internal/audit use only. */
    public Booking get(String id) {
        return bookings.get(id);
    }

    /** Lookup for normal client traffic: a cancelled booking is "gone". */
    public Booking getVisible(String id) {
        Booking booking = bookings.get(id);
        if (booking == null || booking.status() == BookingStatus.CANCELLED) {
            return null;
        }
        return booking;
    }

    /** Bookings visible in the default collection view (cancelled hidden). */
    public List<Booking> listVisible() {
        List<Booking> result = new ArrayList<>();
        synchronized (bookings) {
            for (Booking booking : bookings.values()) {
                if (booking.status() != BookingStatus.CANCELLED) {
                    result.add(booking);
                }
            }
        }
        return result;
    }

    /** Soft delete: cancel the booking in place and record why/when. */
    public void softDelete(String id, Booking cancelled, String reason, String deletedAt) {
        bookings.put(id, cancelled);
        auditTrail.put(id, new DeletionAudit(deletedAt, reason));
    }

    public DeletionAudit getAudit(String id) {
        return auditTrail.get(id);
    }

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
}
