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
 * Ch6 content negotiation &amp; status codes: extends the Ch4 contract-first
 * anchor's Booking + Cargo resource model from
 * contracts/openapi/shipping-api.yaml with explicit Accept/Content-Type
 * negotiation and a full status-code discipline pass.
 *
 * <p>Content negotiation is mostly "free" here: every resource method's
 * {@code @Produces} lists exactly {@code application/json} and
 * {@code application/problem+json} (never a wildcard), so when a client's
 * {@code Accept} header can't be satisfied by either — e.g.
 * {@code Accept: application/xml} — RESTEasy Reactive itself raises
 * {@link jakarta.ws.rs.NotAcceptableException} per the JAX-RS content-
 * negotiation algorithm (JAX-RS 2.1 §3.8), before this class's code ever
 * runs. Likewise, every write method's {@code @Consumes} is exactly
 * {@code application/json} (or {@code application/merge-patch+json} for
 * PATCH), so a request with the wrong {@code Content-Type} — e.g.
 * {@code Content-Type: text/plain} on a POST — triggers
 * {@link jakarta.ws.rs.NotSupportedException} the same way. Both are turned
 * into a {@code Problem} body by {@link ProblemMappers}, so the 406/415
 * paths need no new code in the resource methods themselves — only the
 * right {@code @Produces}/{@code @Consumes} declarations.
 *
 * <p>Every response body here is schema-validated by this example's
 * verify.sh against contracts/schemas/shipping.schema.json.
 */
@Path("/bookings")
public class BookingResource {

    static final String PROBLEM_JSON = "application/problem+json";

    @Inject
    BookingStore store;

    @Inject
    ObjectMapper mapper;

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
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
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
    public Response listBookings(@RestQuery @DefaultValue("20") int limit) {
        List<Booking> visible = store.listVisible();
        PageMeta page = new PageMeta(limit, visible.size(), null);
        return Response.ok(new BookingCollection(visible, page)).build();
    }

    @GET
    @Path("/{id}")
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
    public Response getBooking(@RestPath String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(booking).build();
    }

    @PUT
    @Path("/{id}")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
    public Response replaceBooking(@RestPath String id, @Valid BookingRequest request) {
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
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
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
    public Response patchBooking(@RestPath String id, JsonNode mergePatchDoc) {
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
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
    public Response deleteBooking(@RestPath String id) {
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
        }
        Booking cancelled = new Booking(
                existing.id(), BookingStatus.CANCELLED, existing.origin(), existing.destination(),
                existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(), nowUtc());
        store.put(cancelled);
        return Response.noContent().build();
    }

    /**
     * 409 Conflict path: confirming a booking is only valid from
     * {@code PENDING} — confirming it twice, or confirming one that's
     * already cancelled/in transit/delivered, is a state conflict, not a
     * validation error (the request is well-formed; the resource just
     * isn't in a state that allows it). This rounds out the status-code
     * table: 200 on success, 404 if the booking doesn't exist, 409 if it
     * exists but is in the wrong state.
     */
    @POST
    @Path("/{id}/confirm")
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
    public Response confirmBooking(@RestPath String id) {
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
        }
        if (existing.status() != BookingStatus.PENDING) {
            return problem(409, "Conflict",
                    "Booking " + id + " cannot be confirmed from status " + existing.status()
                            + "; only a PENDING booking can be confirmed");
        }
        Booking confirmed = new Booking(
                existing.id(), BookingStatus.CONFIRMED, existing.origin(), existing.destination(),
                existing.cargo(), existing.quote(), existing.requestedPickup(), existing.createdAt(), nowUtc());
        store.put(confirmed);
        return Response.ok(confirmed).build();
    }

    @GET
    @Path("/{id}/cargo")
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
    public Response listCargo(@RestPath String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(booking.cargo()).build();
    }

    @POST
    @Path("/{id}/cargo")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces({MediaType.APPLICATION_JSON, PROBLEM_JSON})
    public Response addCargo(@RestPath String id, @Valid CargoRequest request) {
        Booking booking = store.get(id);
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
        return Response.status(status).type(PROBLEM_JSON).entity(problem).build();
    }
}
