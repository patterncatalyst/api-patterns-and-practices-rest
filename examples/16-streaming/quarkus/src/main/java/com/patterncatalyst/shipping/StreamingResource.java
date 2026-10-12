package com.patterncatalyst.shipping;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.patterncatalyst.shipping.model.BookingEvent;
import com.patterncatalyst.shipping.model.Problem;

import io.smallrye.mutiny.Multi;

import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.WebApplicationException;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import org.jboss.resteasy.reactive.RestPath;
import org.jboss.resteasy.reactive.RestStreamElementType;

import java.time.Duration;
import java.util.stream.IntStream;

/**
 * `/bookings/.../events*` — Ch16's whole point: three ways to deliver a
 * sequence of {@link BookingEvent} payloads to a client INCREMENTALLY
 * rather than as one buffered blob.
 *
 * <ul>
 *   <li>{@link #bookingEvents} — Server-Sent Events: a bounded, timed
 *       sequence of frames over a long-lived connection (live updates).</li>
 *   <li>{@link #exportEvents} — NDJSON: one JSON object per line, for a
 *       bulk/batch consumer that wants to process records as they arrive
 *       rather than wait for the whole response.</li>
 *   <li>{@link #exportChunked} — a dedicated endpoint proving HTTP chunked
 *       transfer (no {@code Content-Length}, {@code Transfer-Encoding:
 *       chunked}) over a payload too large/slow to buffer up front. SSE and
 *       NDJSON above are ALSO chunked under the hood (Quarkus never knows
 *       their total length in advance either); this endpoint exists so
 *       verify.sh can assert the chunked-transfer mechanics in isolation,
 *       independent of SSE/NDJSON framing.</li>
 * </ul>
 *
 * All three are built on Mutiny {@link Multi} — the reactive-streams type
 * Quarkus REST streams element-by-element to the client as each item is
 * produced, instead of collecting everything into memory first.
 */
@Path("/bookings")
public class StreamingResource {

    @Inject
    BookingStore store;

    @Inject
    ObjectMapper objectMapper;

    // -----------------------------------------------------------------
    // 1. Server-Sent Events — live cargo-status updates for one booking.
    // -----------------------------------------------------------------

    @GET
    @Path("/{bookingId}/events")
    @Produces(MediaType.SERVER_SENT_EVENTS)
    @RestStreamElementType(MediaType.APPLICATION_JSON)
    public Multi<BookingEvent> bookingEvents(@RestPath String bookingId) {
        if (store.get(bookingId) == null) {
            throw notFoundException(bookingId);
        }

        // ticks() emits 0, 1, 2, ... at a fixed cadence; starting AFTER the
        // interval (not at t=0) means the client sees the connection open
        // immediately but the first `data:` frame only arrives one interval
        // later — genuinely spaced out, not all buffered and flushed at
        // once. select().first(N) completes (closes) the stream after the
        // Nth tick instead of ticking forever.
        return Multi.createFrom().ticks()
                .startingAfter(Duration.ofMillis(EventGenerator.SSE_INTERVAL_MILLIS))
                .every(Duration.ofMillis(EventGenerator.SSE_INTERVAL_MILLIS))
                .onItem().transform(tick -> EventGenerator.eventFor(bookingId, tick.intValue()))
                .select().first(EventGenerator.SSE_EVENT_COUNT);
    }

    // -----------------------------------------------------------------
    // 2. NDJSON export — one JSON object per line, flushed incrementally.
    // -----------------------------------------------------------------

    @GET
    @Path("/events/export")
    @Produces("application/x-ndjson")
    public Multi<String> exportEvents() {
        return Multi.createFrom().items(IntStream.range(0, EventGenerator.EXPORT_EVENT_COUNT).boxed())
                .onItem().transform(i -> toJsonLine(EventGenerator.eventFor(EventGenerator.EXPORT_SAMPLE_BOOKING_ID, i)));
    }

    // -----------------------------------------------------------------
    // 3. Dedicated chunked-transfer demo — a larger generated payload with
    //    no Content-Length, proving Transfer-Encoding: chunked.
    // -----------------------------------------------------------------

    @GET
    @Path("/events/export/chunked")
    @Produces(MediaType.TEXT_PLAIN)
    public Multi<String> exportChunked() {
        return Multi.createFrom().items(IntStream.range(0, EventGenerator.CHUNKED_LINE_COUNT).boxed())
                .onItem().transform(StreamingResource::chunkedLine);
    }

    // -----------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------

    private static String chunkedLine(int index) {
        return "line-" + index + ": " + "x".repeat(200) + "\n";
    }

    private String toJsonLine(BookingEvent event) {
        try {
            return objectMapper.writeValueAsString(event) + "\n";
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Failed to serialize BookingEvent", e);
        }
    }

    private WebApplicationException notFoundException(String bookingId) {
        Problem problem = new Problem("Booking not found", 404, "No booking with id " + bookingId);
        Response response = Response.status(404).type("application/problem+json").entity(problem).build();
        return new WebApplicationException(response);
    }
}
