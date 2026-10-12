package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import org.jboss.resteasy.reactive.RestPath;

/**
 * URI versioning, v2 side: {@code GET /v2/bookings/{id}} always returns the
 * CURRENT {@code Booking} shape (quote + cargo[]) from
 * {@code contracts/schemas/shipping.schema.json}, regardless of any
 * {@code Accept} header. The unversioned {@code GET /bookings/{id}} in
 * {@link BookingResource} also serves this shape by default — URI
 * versioning and "no version pin at all" agree on what "current" means.
 */
@Path("/v2/bookings")
public class V2BookingResource {

    @Inject
    BookingStore store;

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response getBookingV2(@RestPath String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(booking).build();
    }

    private Response notFound(String id) {
        Problem problem = new Problem("Booking not found", 404, "No booking with id " + id);
        return Response.status(404).type("application/problem+json").entity(problem).build();
    }
}
