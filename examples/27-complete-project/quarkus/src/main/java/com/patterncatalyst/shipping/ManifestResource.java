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
import jakarta.ws.rs.core.Response;

import org.jboss.resteasy.reactive.RestPath;

import java.time.Duration;

/**
 * Ch16-style streaming: `GET /bookings/{id}/manifest/export` delivers that
 * booking's lifecycle manifest as `application/x-ndjson`, one
 * {@link BookingEvent} per line, flushed INCREMENTALLY (one line every
 * {@link ManifestEventGenerator#INTERVAL_MILLIS}) rather than buffered and
 * written in one shot. Built on Mutiny {@link Multi} — the reactive-streams
 * type Quarkus REST streams element-by-element to the client as each item
 * is produced. See {@link NdjsonMessageBodyWriter} for why a dedicated
 * writer is required for this media type.
 */
@Path("/bookings")
public class ManifestResource {

    @Inject
    BookingStore store;

    @Inject
    ObjectMapper objectMapper;

    @GET
    @Path("/{id}/manifest/export")
    @Produces("application/x-ndjson")
    public Multi<String> exportManifest(@RestPath String id) {
        if (store.get(id) == null) {
            throw notFoundException(id);
        }

        return Multi.createFrom().ticks()
                .startingAfter(Duration.ofMillis(ManifestEventGenerator.INTERVAL_MILLIS))
                .every(Duration.ofMillis(ManifestEventGenerator.INTERVAL_MILLIS))
                .onItem().transform(tick -> toJsonLine(ManifestEventGenerator.eventFor(id, tick.intValue())))
                .select().first(ManifestEventGenerator.LINE_COUNT);
    }

    private String toJsonLine(BookingEvent event) {
        try {
            return objectMapper.writeValueAsString(event) + "\n";
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Failed to serialize BookingEvent", e);
        }
    }

    private WebApplicationException notFoundException(String id) {
        Problem problem = new Problem("Booking not found", 404, "No booking with id " + id);
        Response response = Response.status(404).type("application/problem+json").entity(problem).build();
        return new WebApplicationException(response);
    }
}
