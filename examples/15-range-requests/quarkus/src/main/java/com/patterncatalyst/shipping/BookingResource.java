package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingRequest;
import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.Cargo;
import com.patterncatalyst.shipping.model.CargoRequest;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.validation.Valid;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import org.jboss.resteasy.reactive.RestPath;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;

/**
 * Ch15's Booking resource is deliberately thin: just the slice of Ch4's
 * contract-first Booking model (POST to create, GET by id) needed to mint a
 * booking id for the manifest tests below. This chapter's actual subject —
 * HEAD/GET /bookings/{bookingId}/manifest with Range support — lives in
 * ManifestResource. No PUT/PATCH/DELETE/cargo-sub-resource here; those stay
 * in Ch4/Ch5/Ch7/Ch13 where they're the point.
 */
@Path("/bookings")
public class BookingResource {

    @Inject
    BookingStore store;

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response createBooking(@Valid BookingRequest request) {
        List<Cargo> cargoItems = toCargoItems(request.cargo());
        Booking booking = new Booking(
                "bkg_" + Ulid.generate(),
                BookingStatus.PENDING,
                request.origin(),
                request.destination(),
                cargoItems,
                null,
                request.requestedPickup(),
                nowUtc(),
                null);
        store.put(booking);

        // A literal header string, NOT Response.created(URI) — see
        // ../04-contract-first/BookingResource.java's createBooking() for
        // why: ResponseBuilder.location(URI) resolves a relative URI into
        // an absolute one, which would make Quarkus's Location header shape
        // diverge from the Python stack's relative `/bookings/{id}`.
        return Response.status(Response.Status.CREATED)
                .header("Location", "/bookings/" + booking.id())
                .entity(booking)
                .build();
    }

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response getBooking(@RestPath String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(booking).build();
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    private List<Cargo> toCargoItems(List<CargoRequest> requests) {
        List<Cargo> items = new ArrayList<>(requests.size());
        for (CargoRequest cr : requests) {
            items.add(new Cargo("crg_" + Ulid.generate(), cr.description(), cr.type(), cr.dimensions(), cr.hazardousOrDefault()));
        }
        return items;
    }

    private static String nowUtc() {
        return Instant.now().truncatedTo(ChronoUnit.SECONDS).toString();
    }

    private Response notFound(String id) {
        return problem(404, "Booking not found", "No booking with id " + id);
    }

    private Response problem(int status, String title, String detail) {
        Problem problem = new Problem(title, status, detail);
        return Response.status(status).type("application/problem+json").entity(problem).build();
    }
}
