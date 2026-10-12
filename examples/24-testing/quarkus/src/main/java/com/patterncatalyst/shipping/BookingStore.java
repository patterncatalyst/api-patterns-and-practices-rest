package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import jakarta.enterprise.context.ApplicationScoped;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * In-memory booking store. This chapter's job is proving the test pyramid
 * around a known-good booking shape, not persistence — see
 * examples/04-contract-first for the same tradeoff.
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
