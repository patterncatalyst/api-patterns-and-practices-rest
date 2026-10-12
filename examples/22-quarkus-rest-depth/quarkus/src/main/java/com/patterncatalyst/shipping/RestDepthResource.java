package com.patterncatalyst.shipping;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.patterncatalyst.shipping.model.BookingEvent;

import io.smallrye.mutiny.Multi;

import jakarta.inject.Inject;
import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

import org.jboss.resteasy.reactive.RestHeader;
import org.jboss.resteasy.reactive.RestQuery;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Ch22's whole point: Quarkus REST (née RESTEasy Reactive) resolves
 * {@code @RestHeader}/{@code @RestQuery}/{@code @RestPath}/{@code @RestForm}
 * parameter bindings at BUILD TIME via Quarkus's bytecode-generating
 * processor — no {@code java.lang.reflect.Method}/{@code Parameter}
 * introspection happens per request, unlike classic JAX-RS
 * (RESTEasy Classic's {@code @HeaderParam}/{@code @QueryParam}), which both
 * resolve via reflection on every call. The two endpoints below produce
 * HTTP-observable behavior identical to their classic-JAX-RS counterparts
 * — same status codes, same header/query semantics — that's the point:
 * the zero-reflection win is in HOW the binding executes (ahead of time,
 * once, at build), not a change in what a client sees on the wire. See
 * README.md for the full explainer.
 */
@Path("/")
public class RestDepthResource {

    @Inject
    ObjectMapper objectMapper;

    // -----------------------------------------------------------------
    // 1. @RestHeader — zero-reflection header binding.
    // -----------------------------------------------------------------

    /**
     * Fallback tenant when the caller sends no {@code X-Tenant} header at
     * all. `@RestHeader` injects {@code null} for an absent header on a
     * reference type (String) — identical behavior to classic
     * {@code @HeaderParam} — so the default is applied explicitly in code
     * rather than via {@code @DefaultValue} (which only ever supplies a
     * STRING literal, not a derived default).
     */
    static final String DEFAULT_TENANT = "public";

    @GET
    @Path("/tenant")
    @Produces(MediaType.APPLICATION_JSON)
    public Map<String, Object> tenantInfo(@RestHeader("X-Tenant") String tenant) {
        boolean defaulted = tenant == null;
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("tenant", defaulted ? DEFAULT_TENANT : tenant);
        body.put("defaulted", defaulted);
        return body;
    }

    // -----------------------------------------------------------------
    // 2. @RestQuery + reactive NDJSON — zero-reflection query binding
    //    that DRIVES the response, streamed INCREMENTALLY (not buffered).
    // -----------------------------------------------------------------

    /**
     * {@code limit} controls exactly how many {@link BookingEvent} records
     * come back (clamped to {@code [1, EventGenerator.MAX_LIMIT]} as a DoS
     * guard — an unbounded limit would let a client force an arbitrarily
     * long-lived stream). Built on Mutiny {@link Multi#createFrom()}
     * {@code ticks()} — the same incremental-delivery technique Ch16's SSE
     * endpoint uses — so each line is flushed to the socket as its own tick
     * fires, roughly {@code EventGenerator.STREAM_INTERVAL_MILLIS} apart,
     * rather than generated internally and written in one buffered burst
     * right before the connection closes.
     */
    @GET
    @Path("/bookings/events/export")
    @Produces("application/x-ndjson")
    public Multi<String> exportEvents(@RestQuery("limit") @DefaultValue("5") int limit) {
        int effectiveLimit = EventGenerator.clampLimit(limit);

        return Multi.createFrom().ticks()
                .startingAfter(Duration.ofMillis(EventGenerator.STREAM_INTERVAL_MILLIS))
                .every(Duration.ofMillis(EventGenerator.STREAM_INTERVAL_MILLIS))
                .onItem().transform(Long::intValue)
                .select().first(effectiveLimit)
                .onItem().transform(i -> toJsonLine(EventGenerator.eventFor(EventGenerator.SAMPLE_BOOKING_ID, i)));
    }

    // -----------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------

    private String toJsonLine(BookingEvent event) {
        try {
            return objectMapper.writeValueAsString(event) + "\n";
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Failed to serialize BookingEvent", e);
        }
    }
}
