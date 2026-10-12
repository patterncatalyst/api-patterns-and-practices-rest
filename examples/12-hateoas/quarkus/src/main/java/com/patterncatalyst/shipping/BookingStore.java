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
 * chapter's job is proving state-dependent `_links` against the booking
 * lifecycle, not persistence (Postgres shows up once a later example
 * needs it). Stored bookings never carry `_links` themselves — HateoasLinks
 * computes them fresh from the CURRENT status at response time, in
 * BookingResource.
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
