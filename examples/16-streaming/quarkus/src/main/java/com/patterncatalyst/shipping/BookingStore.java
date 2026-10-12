package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import jakarta.enterprise.context.ApplicationScoped;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory booking store. Ch16 only needs put/get — just enough to mint a
 * booking id for the streaming tests below and to tell a known booking from
 * an unknown one (the SSE endpoint's 404 case). Mirrors
 * ../04-contract-first's BookingStore, trimmed of the
 * listVisible()/soft-delete machinery this chapter doesn't exercise.
 */
@ApplicationScoped
public class BookingStore {

    private final Map<String, Booking> bookings = new ConcurrentHashMap<>();

    public void put(Booking booking) {
        bookings.put(booking.id(), booking);
    }

    public Booking get(String id) {
        return bookings.get(id);
    }
}
