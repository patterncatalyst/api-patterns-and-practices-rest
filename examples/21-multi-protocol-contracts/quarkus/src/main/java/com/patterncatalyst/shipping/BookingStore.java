package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import jakarta.enterprise.context.ApplicationScoped;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * In-memory booking store — same role as examples/04-contract-first's
 * BookingStore. Ch21's point is the sync-REST + background-event pairing,
 * not persistence.
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
}
