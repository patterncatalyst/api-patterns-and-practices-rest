package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.DeletionAudit;
import jakarta.enterprise.context.ApplicationScoped;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * In-memory booking store backing every capability this example exercises:
 * plain CRUD (Ch4), ascending-by-id listing for keyset pagination (Ch8), a
 * PENDING-&gt;CONFIRMED transition driven by the async operation worker
 * (Ch10), and soft delete + GDPR purge with a separate audit trail (Ch13).
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

    /** Bookings visible in the default collection view (cancelled hidden), sorted
     * ascending by id — ULIDs are 48-bit-timestamp-prefixed, so sorting by id is
     * equivalent to sorting by creation time; this is the stable sort key keyset
     * pagination is built on. */
    public List<Booking> listVisible() {
        List<Booking> result = new ArrayList<>();
        synchronized (bookings) {
            for (Booking booking : bookings.values()) {
                if (booking.status() != BookingStatus.CANCELLED) {
                    result.add(booking);
                }
            }
        }
        result.sort(Comparator.comparing(Booking::id));
        return result;
    }

    /** Ch10: flips a PENDING booking to CONFIRMED (no-op if already past PENDING). Returns the current booking. */
    public Booking confirm(String id) {
        Booking existing = bookings.get(id);
        if (existing == null || existing.status() != BookingStatus.PENDING) {
            return existing;
        }
        Booking confirmed = new Booking(
                existing.id(), BookingStatus.CONFIRMED, existing.origin(), existing.destination(),
                existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(),
                nowUtc(), null);
        bookings.put(id, confirmed);
        return confirmed;
    }

    /** Soft delete: cancel the booking in place and record why/when. */
    public void softDelete(String id, String reason) {
        Booking existing = bookings.get(id);
        if (existing == null) {
            return;
        }
        String now = nowUtc();
        Booking cancelled = new Booking(
                existing.id(), BookingStatus.CANCELLED, existing.origin(), existing.destination(),
                existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(), now, null);
        bookings.put(id, cancelled);
        auditTrail.put(id, new DeletionAudit(now, reason));
    }

    public DeletionAudit getAudit(String id) {
        return auditTrail.get(id);
    }

    /** GDPR purge: hard-delete the booking AND its audit trail. Returns true if
     * a booking existed to purge. */
    public boolean purge(String id) {
        boolean existed = bookings.remove(id) != null;
        auditTrail.remove(id);
        return existed;
    }

    private static String nowUtc() {
        return Instant.now().truncatedTo(ChronoUnit.SECONDS).toString();
    }
}
