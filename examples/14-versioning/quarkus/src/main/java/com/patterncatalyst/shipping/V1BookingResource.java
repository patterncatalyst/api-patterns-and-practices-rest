package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Response;

import org.jboss.resteasy.reactive.RestPath;

/**
 * URI versioning, v1 side: {@code GET /v1/bookings/{id}} always returns the
 * FROZEN {@code BookingV1} shape (price + cargoDescription), regardless of
 * any {@code Accept} header — the URL itself is the version pin. There is
 * no POST/PUT/PATCH/DELETE here: v1 is a stub frozen read view for teaching
 * the breaking change, not a maintained write API (see README.md).
 */
@Path("/v1/bookings")
public class V1BookingResource {

    @Inject
    BookingStore store;

    @GET
    @Path("/{id}")
    @Produces(VersionMapper.MEDIA_TYPE_V1)
    public Response getBookingV1(@RestPath String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(VersionMapper.toV1(booking)).build();
    }

    private Response notFound(String id) {
        Problem problem = new Problem("Booking not found", 404, "No booking with id " + id);
        return Response.status(404).type("application/problem+json").entity(problem).build();
    }
}
