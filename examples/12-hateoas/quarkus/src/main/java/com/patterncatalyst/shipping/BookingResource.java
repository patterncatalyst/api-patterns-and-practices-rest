package com.patterncatalyst.shipping;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingCollection;
import com.patterncatalyst.shipping.model.BookingRequest;
import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.Cargo;
import com.patterncatalyst.shipping.model.CargoRequest;
import com.patterncatalyst.shipping.model.Link;
import com.patterncatalyst.shipping.model.Money;
import com.patterncatalyst.shipping.model.PageMeta;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.DELETE;
import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.PATCH;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.PUT;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Ch12 HATEOAS: the Ch4 contract-first Booking + Cargo resource model, now
 * with state-dependent `_links` on every Booking response. The stored
 * Booking never carries `_links` itself (always `null`) — {@link #withLinks}
 * computes the relations valid from the CURRENT status fresh at response
 * time, via HateoasLinks, so a stale link never survives a transition.
 * Every response body here is schema-validated by this chapter's verify.sh
 * against contracts/schemas/shipping.schema.json.
 */
@Path("/bookings")
public class BookingResource {

    @Inject
    BookingStore store;

    @Inject
    ObjectMapper mapper;

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response createBooking(BookingRequest request) {
        Response invalid = validateBookingRequest(request);
        if (invalid != null) {
            return invalid;
        }

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
                null,
                null);
        store.put(booking);

        // A literal header string, NOT Response.created(URI) — per the
        // JAX-RS spec, ResponseBuilder.location(URI) resolves a relative
        // URI into an absolute one against the base URI, which would make
        // Quarkus's Location header shape diverge from the Python stack's
        // relative `/bookings/{id}`. Setting the header directly keeps the
        // two stacks byte-for-byte identical.
        return Response.status(Response.Status.CREATED)
                .header("Location", "/bookings/" + booking.id())
                .entity(withLinks(booking))
                .build();
    }

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response listBookings(@QueryParam("limit") @DefaultValue("20") int limit) {
        List<Booking> visible = store.listVisible().stream().map(this::withLinks).toList();
        PageMeta page = new PageMeta(limit, visible.size(), null);
        return Response.ok(new BookingCollection(visible, page)).build();
    }

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response getBooking(@PathParam("id") String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(withLinks(booking)).build();
    }

    @PUT
    @Path("/{id}")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response replaceBooking(@PathParam("id") String id, BookingRequest request) {
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
        }
        Response invalid = validateBookingRequest(request);
        if (invalid != null) {
            return invalid;
        }

        // Deterministic (not random) cargo ids: PUT must be idempotent, so
        // replacing a booking with the SAME body twice has to produce the
        // SAME Cargo.id for each item both times — toCargoItems() mints a
        // fresh random id every call, which POST correctly wants but PUT
        // must not.
        List<Cargo> cargoItems = toCargoItemsForReplace(id, request.cargo());
        Booking replaced = new Booking(
                existing.id(),
                existing.status(),
                request.origin(),
                request.destination(),
                cargoItems,
                QuoteCalculator.compute(cargoItems),
                request.requestedPickup(),
                existing.createdAt(),
                nowUtc(),
                null);
        store.put(replaced);
        return Response.ok(withLinks(replaced)).build();
    }

    @PATCH
    @Path("/{id}")
    @Consumes("application/merge-patch+json")
    @Produces(MediaType.APPLICATION_JSON)
    public Response patchBooking(@PathParam("id") String id, JsonNode mergePatchDoc) {
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
        }
        try {
            JsonNode target = mapper.valueToTree(existing);
            JsonNode merged = applyMergePatch(target, mergePatchDoc);
            Booking patched = mapper.treeToValue(merged, Booking.class);
            // id/createdAt are server-assigned (readOnly in the schema); a
            // merge patch can never overwrite them, regardless of what the
            // client sent.
            Booking result = new Booking(
                    existing.id(),
                    patched.status(),
                    patched.origin(),
                    patched.destination(),
                    patched.cargo(),
                    patched.quote(),
                    patched.requestedPickup(),
                    existing.createdAt(),
                    nowUtc(),
                    null);
            store.put(result);
            return Response.ok(withLinks(result)).build();
        } catch (Exception e) {
            return problem(400, "Invalid merge patch", e.getMessage());
        }
    }

    @DELETE
    @Path("/{id}")
    public Response deleteBooking(@PathParam("id") String id) {
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
        }
        Booking cancelled = new Booking(
                existing.id(), BookingStatus.CANCELLED, existing.origin(), existing.destination(),
                existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(), nowUtc(), null);
        store.put(cancelled);
        return Response.noContent().build();
    }

    @GET
    @Path("/{id}/cargo")
    @Produces(MediaType.APPLICATION_JSON)
    public Response listCargo(@PathParam("id") String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(booking.cargo()).build();
    }

    @POST
    @Path("/{id}/cargo")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response addCargo(@PathParam("id") String id, CargoRequest request) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        if (request == null || isBlank(request.description()) || request.type() == null
                || request.dimensions() == null || request.dimensions().weightKg() <= 0) {
            return problem(400, "Invalid cargo request", "description, type and dimensions.weightKg > 0 are required");
        }

        Cargo cargo = new Cargo("crg_" + Ulid.generate(), request.description(), request.type(),
                request.dimensions(), request.hazardousOrDefault());
        List<Cargo> newCargoList = new ArrayList<>(booking.cargo());
        newCargoList.add(cargo);
        Money quote = QuoteCalculator.compute(newCargoList);

        Booking updated = new Booking(
                booking.id(), booking.status(), booking.origin(), booking.destination(),
                newCargoList, quote, booking.requestedPickup(), booking.createdAt(), nowUtc(), null);
        store.put(updated);

        return Response.status(Response.Status.CREATED)
                .header("Location", "/bookings/" + id + "/cargo/" + cargo.id())
                .entity(cargo)
                .build();
    }

    // ------------------------------------------------------------------
    // State transitions — these drive the booking lifecycle FSM so
    // verify.sh can observe a DIFFERENT `_links` set at each state. Not
    // part of the shared OpenAPI contract (ch10's async 202/poll/303
    // `/confirmation` protocol is the contract-level version of
    // `confirm`); this chapter keeps each transition a single synchronous
    // 200 on purpose, to isolate the HATEOAS behavior from the async
    // protocol taught in Ch10.
    // ------------------------------------------------------------------

    @POST
    @Path("/{id}/confirmation")
    @Produces(MediaType.APPLICATION_JSON)
    public Response confirmBooking(@PathParam("id") String id) {
        return transition(id, BookingStatus.PENDING, BookingStatus.CONFIRMED, "confirmed");
    }

    @POST
    @Path("/{id}/transit")
    @Produces(MediaType.APPLICATION_JSON)
    public Response startTransit(@PathParam("id") String id) {
        return transition(id, BookingStatus.CONFIRMED, BookingStatus.IN_TRANSIT, "moved to IN_TRANSIT");
    }

    @POST
    @Path("/{id}/delivery")
    @Produces(MediaType.APPLICATION_JSON)
    public Response deliverBooking(@PathParam("id") String id) {
        return transition(id, BookingStatus.IN_TRANSIT, BookingStatus.DELIVERED, "delivered");
    }

    private Response transition(String id, BookingStatus requiredCurrent, BookingStatus next, String verbPhrase) {
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
        }
        if (existing.status() != requiredCurrent) {
            return problem(409, "Invalid state transition",
                    "Booking " + id + " is " + existing.status() + "; only a " + requiredCurrent
                            + " booking can be " + verbPhrase);
        }
        Booking updated = new Booking(
                existing.id(), next, existing.origin(), existing.destination(), existing.cargo(),
                existing.quote(), existing.requestedPickup(), existing.createdAt(), nowUtc(), null);
        store.put(updated);
        return Response.ok(withLinks(updated)).build();
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    /**
     * Computes `_links` fresh from `booking`'s CURRENT status (HateoasLinks)
     * and returns a copy carrying them. Every response-building call site
     * routes through here rather than storing links on the Booking kept in
     * BookingStore, so a transition can never leave a stale link behind.
     */
    private Booking withLinks(Booking booking) {
        Map<String, Link> links = HateoasLinks.forBooking(booking.id(), booking.status());
        return new Booking(
                booking.id(), booking.status(), booking.origin(), booking.destination(), booking.cargo(),
                booking.quote(), booking.requestedPickup(), booking.createdAt(), booking.updatedAt(), links);
    }

    private Response validateBookingRequest(BookingRequest request) {
        if (request == null || request.origin() == null || isBlank(request.origin().unLocode())
                || request.destination() == null || isBlank(request.destination().unLocode())
                || request.cargo() == null || request.cargo().isEmpty()) {
            return problem(400, "Invalid booking request",
                    "origin.unLocode, destination.unLocode and at least one cargo item are required");
        }
        for (CargoRequest c : request.cargo()) {
            if (isBlank(c.description()) || c.type() == null || c.dimensions() == null
                    || c.dimensions().weightKg() <= 0) {
                return problem(400, "Invalid cargo item",
                        "each cargo item needs description, type and dimensions.weightKg > 0");
            }
        }
        return null;
    }

    private List<Cargo> toCargoItems(List<CargoRequest> requests) {
        List<Cargo> items = new ArrayList<>(requests.size());
        for (CargoRequest cr : requests) {
            items.add(new Cargo("crg_" + Ulid.generate(), cr.description(), cr.type(), cr.dimensions(), cr.hazardousOrDefault()));
        }
        return items;
    }

    /** Like {@link #toCargoItems}, but with deterministic ids keyed on
     * (bookingId, index) so a PUT replace is idempotent — see the comment
     * at the {@code replaceBooking} call site. */
    private List<Cargo> toCargoItemsForReplace(String bookingId, List<CargoRequest> requests) {
        List<Cargo> items = new ArrayList<>(requests.size());
        for (int i = 0; i < requests.size(); i++) {
            CargoRequest cr = requests.get(i);
            String id = "crg_" + Ulid.deterministic(bookingId + ":" + i);
            items.add(new Cargo(id, cr.description(), cr.type(), cr.dimensions(), cr.hazardousOrDefault()));
        }
        return items;
    }

    private JsonNode applyMergePatch(JsonNode target, JsonNode patch) {
        if (patch == null || !patch.isObject()) {
            return patch;
        }
        ObjectNode result = (target != null && target.isObject()) ? target.deepCopy() : mapper.createObjectNode();
        Iterator<Map.Entry<String, JsonNode>> fields = patch.fields();
        while (fields.hasNext()) {
            Map.Entry<String, JsonNode> entry = fields.next();
            JsonNode value = entry.getValue();
            if (value.isNull()) {
                result.remove(entry.getKey());
            } else {
                JsonNode existingValue = result.get(entry.getKey());
                JsonNode mergedValue = applyMergePatch(existingValue, value);
                result.set(entry.getKey(), mergedValue);
            }
        }
        return result;
    }

    private static boolean isBlank(String s) {
        return s == null || s.isBlank();
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
