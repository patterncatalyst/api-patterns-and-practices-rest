package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingStatus;
import jakarta.enterprise.context.ApplicationScoped;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * In-memory booking store. Deterministic and fast on purpose — this
 * chapter's job is proving request/response shapes against the contract,
 * not persistence (Ch4 is contract-first; Postgres shows up once the
 * example needs it).
 */
@ApplicationScoped
public class BookingStore {

    private final Map<String, Booking> bookings = Collections.synchronizedMap(new LinkedHashMap<>());

    public void put(Booking booking) {
        bookings.put(booking.id(), booking);
    }

    public Booking get(String id) {
        return bookings.get(id);
    }

    /**
     * A booking that is still "live" from the API consumer's point of view:
     * exists AND has not been (soft-)deleted. This chapter's DELETE is a
     * soft-delete (status -> CANCELLED, record retained for audit) but every
     * single-item read/write treats a cancelled booking as gone — GET, PUT,
     * PATCH, DELETE and the cargo sub-resource all 404 once a booking is
     * cancelled, matching the "second DELETE -> 404" assertion in
     * verify.sh. Only the raw {@link #get} above can still see a cancelled
     * record, which is what a real audit/undo path would use.
     */
    public Booking getActive(String id) {
        Booking booking = bookings.get(id);
        return (booking == null || booking.status() == BookingStatus.CANCELLED) ? null : booking;
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
}
