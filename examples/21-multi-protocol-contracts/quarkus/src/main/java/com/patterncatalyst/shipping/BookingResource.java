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
import java.util.concurrent.CompletableFuture;

/**
 * Ch21 multi-protocol-contracts anchor: ONE service exposing a synchronous
 * REST path (`POST /bookings` -> `#/$defs/Booking`, per
 * `contracts/openapi/shipping-api.yaml`) that also drives a background
 * event-streaming path (a CloudEvents-enveloped `BookingEvent` published to
 * Kafka, per `contracts/asyncapi/shipping-events.yaml`). The Booking
 * shape/quote logic is the same as examples/04-contract-first — this
 * chapter's addition is BookingEventPublisher, fired off the request thread
 * so the synchronous response never waits on the broker.
 */
@Path("/bookings")
public class BookingResource {

    @Inject
    BookingStore store;

    @Inject
    BookingEventPublisher eventPublisher;

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response createBooking(@Valid BookingRequest request) {
        List<Cargo> cargoItems = toCargoItems(request.cargo());
        String now = nowUtc();
        Booking booking = new Booking(
                "bkg_" + Ulid.generate(),
                BookingStatus.PENDING,
                request.origin(),
                request.destination(),
                cargoItems,
                QuoteCalculator.compute(cargoItems),
                request.requestedPickup(),
                now,
                null);
        store.put(booking);

        // Background action: confirm the booking and publish its CloudEvent
        // off the request thread. The synchronous REST response below
        // returns immediately with the PENDING booking it just created —
        // the confirmation + event emission is the async side effect this
        // chapter is about, not something the caller blocks on.
        CompletableFuture.runAsync(() -> confirmAndPublish(booking));

        // A literal header string, NOT Response.created(URI) — keeps the
        // Location header shape identical to the Python stack's relative
        // `/bookings/{id}` (same reasoning as examples/04-contract-first).
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
    // Background: PENDING -> CONFIRMED + CloudEvents publish
    // ------------------------------------------------------------------

    private void confirmAndPublish(Booking created) {
        Booking confirmed = new Booking(
                created.id(), BookingStatus.CONFIRMED, created.origin(), created.destination(),
                created.cargo(), created.quote(), created.requestedPickup(), created.createdAt(), nowUtc());
        store.put(confirmed);
        eventPublisher.publishConfirmed(confirmed, BookingStatus.PENDING);
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
