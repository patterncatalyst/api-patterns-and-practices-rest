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
import com.patterncatalyst.shipping.model.DeletionAudit;
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
 * Ch13 soft-delete &amp; GDPR purge — extends the Ch4 contract-first anchor's
 * Booking + Cargo resource model with:
 *
 * <ul>
 *   <li>{@code DELETE /bookings/{id}} — soft delete: status → {@code CANCELLED},
 *       an audit entry recorded, and the booking hidden from
 *       {@code GET /bookings} and {@code GET /bookings/{id}} by default.</li>
 *   <li>{@code GET /bookings/{id}?includeDeleted=true} — the audit/compliance
 *       view: still returns the cancelled {@code Booking} (schema-conforming
 *       body) plus {@code X-Audit-Deleted-At}/{@code X-Audit-Reason} headers,
 *       because the record still exists in the store (referential
 *       integrity).</li>
 *   <li>{@code DELETE /bookings/{id}/purge} — the GDPR "right to erasure":
 *       hard-deletes the booking AND its audit trail. After this, even the
 *       audit view 404s.</li>
 * </ul>
 *
 * Every response body here is schema-validated by this example's verify.sh
 * against contracts/schemas/shipping.schema.json — this class is the thing
 * that has to stay honest.
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
    public Response listBookings(@QueryParam("limit") @DefaultValue("20") int limit) {
        List<Booking> visible = store.listVisible();
        PageMeta page = new PageMeta(limit, visible.size(), null);
        return Response.ok(new BookingCollection(visible, page)).build();
    }

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response getBooking(@PathParam("id") String id,
            @QueryParam("includeDeleted") @DefaultValue("false") boolean includeDeleted) {
        // Default clients never see a soft-deleted booking: it's "gone" to
        // them, even though the record is still in the store. The
        // audit/compliance view opts back in with includeDeleted=true.
        Booking booking = includeDeleted ? store.get(id) : store.getVisible(id);
        if (booking == null) {
            return notFound(id);
        }

        Response.ResponseBuilder response = Response.ok(booking);
        if (includeDeleted && booking.status() == BookingStatus.CANCELLED) {
            DeletionAudit audit = store.getAudit(id);
            if (audit != null) {
                response.header("X-Audit-Deleted-At", audit.deletedAt());
                response.header("X-Audit-Reason", audit.reason());
            }
        }
        return response.build();
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
                nowUtc());
        store.put(replaced);
        return Response.ok(replaced).build();
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
                    nowUtc());
            store.put(result);
            return Response.ok(result).build();
        } catch (Exception e) {
            return problem(400, "Invalid merge patch", e.getMessage());
        }
    }

    @DELETE
    @Path("/{id}")
    public Response deleteBooking(@PathParam("id") String id,
            @QueryParam("reason") @DefaultValue("user-requested cancellation") String reason) {
        // Soft delete only ever looks at store.get() (not getVisible()) —
        // deleting an already-cancelled booking again is still a legal
        // no-op-ish cancel, not a 404; only a *missing* booking 404s.
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
        }
        String now = nowUtc();
        Booking cancelled = new Booking(
                existing.id(), BookingStatus.CANCELLED, existing.origin(), existing.destination(),
                existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(), now);
        store.softDelete(id, cancelled, reason, now);
        return Response.noContent().build();
    }

    /**
     * GDPR "right to erasure": hard-deletes the booking AND its audit
     * trail. This overrides the soft-delete retention above — a booking
     * (cancelled or not) that still exists in the store is purgeable; once
     * purged, even {@code GET /bookings/{id}?includeDeleted=true} 404s,
     * because nothing is left to find.
     */
    @DELETE
    @Path("/{id}/purge")
    public Response purgeBooking(@PathParam("id") String id) {
        boolean existed = store.purge(id);
        if (!existed) {
            return notFound(id);
        }
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
