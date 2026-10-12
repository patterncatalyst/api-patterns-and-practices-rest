package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingStatus;
import jakarta.enterprise.context.ApplicationScoped;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * In-memory booking store. Deterministic and fast on purpose — this
 * chapter's job is proving request/response shapes against the contract,
 * not persistence (Ch4 is contract-first; Postgres shows up once the
 * example needs it). Ch10 adds {@link #confirm(String)}, the completion
 * side-effect the background confirmation worker (OperationStore) applies
 * once an async confirmation operation succeeds.
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
     * Transitions a PENDING booking to CONFIRMED. Returns false (a no-op)
     * if the booking is missing or no longer PENDING — e.g. a cancelled
     * operation must never resurrect a booking's confirmation after the
     * fact, and this guard is what makes that safe even if it were called
     * twice.
     */
    public boolean confirm(String id) {
        synchronized (bookings) {
            Booking existing = bookings.get(id);
            if (existing == null || existing.status() != BookingStatus.PENDING) {
                return false;
            }
            Booking confirmed = new Booking(
                    existing.id(), BookingStatus.CONFIRMED, existing.origin(), existing.destination(),
                    existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(), nowUtc());
            bookings.put(id, confirmed);
            return true;
        }
    }

    private static String nowUtc() {
        return Instant.now().truncatedTo(ChronoUnit.SECONDS).toString();
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
