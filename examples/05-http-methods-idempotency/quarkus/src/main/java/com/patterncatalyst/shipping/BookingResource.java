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
import com.patterncatalyst.shipping.model.Money;
import com.patterncatalyst.shipping.model.PageMeta;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.validation.Valid;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.DELETE;
import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.PATCH;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.PUT;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import org.jboss.resteasy.reactive.RestPath;
import org.jboss.resteasy.reactive.RestQuery;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Ch5 HTTP methods &amp; idempotency: extends the Ch4 contract-first anchor's
 * Booking + Cargo resource model from contracts/openapi/shipping-api.yaml
 * with the full method matrix — GET/POST on the collection, GET/PUT/PATCH/
 * DELETE/HEAD on an item, explicit 405s for methods the resource doesn't
 * support, and the idempotency semantics that distinguish them (PUT
 * replaces the same resource state on every call; POST mints a new resource
 * every call; DELETE is idempotent in end-state even though its status code
 * is not: 204 then 404). Every response body here is schema-validated by
 * this example's verify.sh against contracts/schemas/shipping.schema.json.
 */
@Path("/bookings")
public class BookingResource {

    /** Methods the collection resource (/bookings) supports. */
    private static final String ALLOW_COLLECTION = "GET, POST";

    /** Methods the item resource (/bookings/{id}) supports (HEAD piggybacks on GET). */
    private static final String ALLOW_ITEM = "GET, PUT, PATCH, DELETE, HEAD";

    @Inject
    BookingStore store;

    @Inject
    ObjectMapper mapper;

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

        // A literal header string, NOT Response.created(URI) — per the
        // JAX-RS spec, ResponseBuilder.location(URI) resolves a relative
        // URI into an absolute one against the base URI, which would make
        // Quarkus's Location header shape diverge from the Python stack's
        // relative `/bookings/{id}`. Setting the header directly keeps the
        // two stacks byte-for-byte identical.
        return Response.status(Response.Status.CREATED)
                .header("Location", "/bookings/" + booking.id())
                .entity(booking)
                .build();
    }

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response listBookings(@RestQuery @DefaultValue("20") int limit) {
        List<Booking> visible = store.listVisible();
        PageMeta page = new PageMeta(limit, visible.size(), null);
        return Response.ok(new BookingCollection(visible, page)).build();
    }

    /**
     * The collection resource doesn't support PUT (there's no single
     * "whole collection" state to replace) — 405 with an {@code Allow}
     * header naming what it DOES support, and a {@code Problem} body
     * instead of an empty one, so a caller script doesn't have to special-
     * case this resource's error shape.
     */
    @PUT
    public Response replaceCollectionNotAllowed() {
        return methodNotAllowed(ALLOW_COLLECTION, "PUT is not supported on the /bookings collection; "
                + "PUT a specific item at /bookings/{id} instead");
    }

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response getBooking(@RestPath String id) {
        // HEAD /bookings/{id} is not a separate method: per the JAX-RS
        // method-matching algorithm, a HEAD request falls back to the
        // matching @GET method and the runtime discards the entity body
        // while keeping the headers — exactly the HEAD semantics the
        // method matrix calls for, with no extra code.
        Booking booking = store.getActive(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(booking).build();
    }

    /**
     * An item resource doesn't support POST (POST-to-create belongs on the
     * collection, at /bookings) — 405 + Allow + Problem, same shape as the
     * collection's PUT rejection above.
     */
    @POST
    @Path("/{id}")
    public Response createOnItemNotAllowed(@RestPath String id) {
        return methodNotAllowed(ALLOW_ITEM, "POST is not supported on an individual booking; "
                + "POST a new booking to /bookings instead");
    }

    @PUT
    @Path("/{id}")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response replaceBooking(@RestPath String id, @Valid BookingRequest request) {
        Booking existing = store.getActive(id);
        if (existing == null) {
            return notFound(id);
        }

        // Deterministic (not random) cargo ids: PUT must be idempotent, so
        // replacing a booking with the SAME body twice has to produce the
        // SAME Cargo.id for each item both times — toCargoItems() below
        // mints a fresh random id every call, which POST correctly wants
        // but PUT must not.
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
                nowUtc());
        store.put(replaced);
        return Response.ok(replaced).build();
    }

    @PATCH
    @Path("/{id}")
    @Consumes("application/merge-patch+json")
    @Produces(MediaType.APPLICATION_JSON)
    public Response patchBooking(@RestPath String id, JsonNode mergePatchDoc) {
        Booking existing = store.getActive(id);
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
                    nowUtc());
            store.put(result);
            return Response.ok(result).build();
        } catch (Exception e) {
            return problem(400, "Invalid merge patch", e.getMessage());
        }
    }

    @DELETE
    @Path("/{id}")
    public Response deleteBooking(@RestPath String id) {
        // Idempotent in END STATE, not in status code: the first DELETE of
        // a live booking soft-deletes it and returns 204; every DELETE
        // after that (the id never existed, or it's already cancelled)
        // returns 404 — "already gone" — because getActive() treats a
        // cancelled booking the same as a missing one. The resource ends
        // up cancelled either way, which is what idempotency actually
        // promises.
        Booking existing = store.getActive(id);
        if (existing == null) {
            return notFound(id);
        }
        Booking cancelled = new Booking(
                existing.id(), BookingStatus.CANCELLED, existing.origin(), existing.destination(),
                existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(), nowUtc());
        store.put(cancelled);
        return Response.noContent().build();
    }

    @GET
    @Path("/{id}/cargo")
    @Produces(MediaType.APPLICATION_JSON)
    public Response listCargo(@RestPath String id) {
        Booking booking = store.getActive(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(booking.cargo()).build();
    }

    @POST
    @Path("/{id}/cargo")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response addCargo(@RestPath String id, @Valid CargoRequest request) {
        Booking booking = store.getActive(id);
        if (booking == null) {
            return notFound(id);
        }

        Cargo cargo = new Cargo("crg_" + Ulid.generate(), request.description(), request.type(),
                request.dimensions(), request.hazardousOrDefault());
        List<Cargo> newCargoList = new ArrayList<>(booking.cargo());
        newCargoList.add(cargo);
        Money quote = QuoteCalculator.compute(newCargoList);

        Booking updated = new Booking(
                booking.id(), booking.status(), booking.origin(), booking.destination(),
                newCargoList, quote, booking.requestedPickup(), booking.createdAt(), nowUtc());
        store.put(updated);

        return Response.status(Response.Status.CREATED)
                .header("Location", "/bookings/" + id + "/cargo/" + cargo.id())
                .entity(cargo)
                .build();
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

    private Response methodNotAllowed(String allow, String detail) {
        Problem problem = new Problem("Method Not Allowed", 405, detail);
        return Response.status(405)
                .header("Allow", allow)
                .type("application/problem+json")
                .entity(problem)
                .build();
    }
}
