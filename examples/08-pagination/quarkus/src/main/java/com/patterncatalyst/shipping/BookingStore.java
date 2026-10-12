package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingStatus;
import jakarta.enterprise.context.ApplicationScoped;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * In-memory booking store. Deterministic and fast on purpose — this
 * chapter's job is proving pagination/projection shapes against the
 * contract, not persistence (Postgres shows up once a later chapter needs
 * it).
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
     * Bookings visible in the default collection view (cancelled hidden),
     * sorted ascending by id. ULIDs are 48-bit-timestamp-prefixed, so
     * sorting by id is equivalent to sorting by creation time — this is
     * the single stable sort key every pagination strategy is built on.
     */
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
}
