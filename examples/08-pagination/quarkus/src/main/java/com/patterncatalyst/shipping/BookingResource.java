package com.patterncatalyst.shipping;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
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
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.DELETE;
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

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Ch8 filtering, projection &amp; pagination: extends the Ch4 contract-first
 * Booking + Cargo resource model with three pagination strategies (offset,
 * keyset/cursor, seek) and sparse fieldset projection on GET /bookings.
 * Every non-projected response body here is schema-validated by
 * examples/08-pagination's verify.sh against
 * contracts/schemas/shipping.schema.json — this class is the thing that has
 * to stay honest.
 */
@Path("/bookings")
public class BookingResource {

    /** Default page size when `limit` is omitted. */
    private static final int DEFAULT_LIMIT = 20;

    /** DoS guard: `limit` above this is CLAMPED, never honored unbounded
     * (matches `#/$defs/PageMeta.limit`'s `maximum: 100` in the shared
     * schema). An unbounded limit lets a client force the server to
     * materialize and serialize an arbitrarily large response in one shot. */
    private static final int MAX_LIMIT = 100;

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

    /**
     * GET /bookings — four orthogonal query knobs, documented in
     * examples/08-pagination/README.md:
     *
     * <ul>
     *   <li>{@code limit} — page size, clamped to [1, MAX_LIMIT].</li>
     *   <li>{@code offset} — classic offset pagination (drifts under
     *       concurrent inserts; see README). Takes precedence over
     *       after_id/cursor when present.</li>
     *   <li>{@code after_id} — seek pagination: items with id &gt; after_id.
     *       Takes precedence over cursor when present (and offset absent).</li>
     *   <li>{@code cursor} — keyset pagination, the DEFAULT/stable strategy
     *       when offset and after_id are both absent. Opaque (base64 of the
     *       last-seen id); {@code page.nextCursor} is null on the last
     *       page.</li>
     *   <li>{@code fields} — sparse fieldset (e.g. "id,status,origin"); when
     *       present the response is NOT a schema-conforming
     *       {@code BookingCollection} (items are a reduced shape) — built by
     *       hand below instead of through the {@code Booking} record.</li>
     * </ul>
     */
    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response listBookings(
            @QueryParam("limit") Integer limit,
            @QueryParam("offset") Integer offset,
            @QueryParam("after_id") String afterId,
            @QueryParam("cursor") String cursor,
            @QueryParam("fields") String fields) {
        List<Booking> visible = store.listVisible();
        int effectiveLimit = clampLimit(limit);
        PageResult result = computePage(visible, offset, afterId, cursor, effectiveLimit);
        PageMeta page = new PageMeta(effectiveLimit, result.items().size(), result.nextCursor());

        if (fields == null || fields.isBlank()) {
            return Response.ok(new BookingCollection(result.items(), page)).build();
        }
        return Response.ok(projectItems(result.items(), fields, page)).build();
    }

    // ------------------------------------------------------------------
    // Pagination strategies
    // ------------------------------------------------------------------

    private record PageResult(List<Booking> items, String nextCursor) {
    }

    private int clampLimit(Integer requested) {
        int limit = (requested == null) ? DEFAULT_LIMIT : requested;
        if (limit < 1) {
            limit = 1;
        }
        if (limit > MAX_LIMIT) {
            limit = MAX_LIMIT;
        }
        return limit;
    }

    /**
     * Resolves exactly one of three mutually-exclusive strategies, in
     * precedence order: offset > after_id (seek) > cursor (keyset,
     * default). {@code visible} must already be sorted ascending by id
     * (see {@link BookingStore#listVisible()}).
     */
    private PageResult computePage(List<Booking> visible, Integer offset, String afterId, String cursor, int limit) {
        if (offset != null) {
            int off = Math.max(0, offset);
            List<Booking> page = visible.stream().skip(off).limit(limit).toList();
            return new PageResult(page, null);
        }

        if (afterId != null && !afterId.isBlank()) {
            List<Booking> candidates = visible.stream().filter(b -> b.id().compareTo(afterId) > 0).toList();
            List<Booking> page = candidates.stream().limit(limit).toList();
            return new PageResult(page, null);
        }

        // Keyset/cursor — the default/stable strategy. A null/blank cursor
        // means "first page"; following page.nextCursor walks the whole set
        // with no dupes or gaps, because each page's lower bound is the
        // highest id actually returned by the page before it.
        String afterKey = (cursor != null && !cursor.isBlank()) ? decodeCursor(cursor) : null;
        List<Booking> candidates = (afterKey == null)
                ? visible
                : visible.stream().filter(b -> b.id().compareTo(afterKey) > 0).toList();
        List<Booking> page = candidates.stream().limit(limit).toList();
        String nextCursor = (candidates.size() > limit) ? encodeCursor(page.get(page.size() - 1).id()) : null;
        return new PageResult(page, nextCursor);
    }

    /** Opaque cursor = base64url of the last-seen booking id. Callers must
     * treat it as opaque; this encoding is an implementation detail. */
    private static String encodeCursor(String id) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(id.getBytes(StandardCharsets.UTF_8));
    }

    /** A malformed cursor is treated as "start from the beginning" rather
     * than failing the request — a client replaying a stale/corrupted
     * cursor still gets a valid (if restarted) page. */
    private static String decodeCursor(String cursor) {
        try {
            return new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    /**
     * Sparse fieldset projection. {@code id} is always included regardless
     * of whether it was requested. The result is built as a raw
     * {@link ObjectNode} tree, NOT a {@code BookingCollection}/{@code
     * Booking}, because a projected item generally fails the full
     * {@code Booking} schema (missing required properties) — that's
     * expected and documented in README.md, not a bug.
     */
    private ObjectNode projectItems(List<Booking> items, String fields, PageMeta page) {
        Set<String> requested = new LinkedHashSet<>();
        for (String f : fields.split(",")) {
            String trimmed = f.trim();
            if (!trimmed.isEmpty()) {
                requested.add(trimmed);
            }
        }

        ArrayNode itemsNode = mapper.createArrayNode();
        for (Booking booking : items) {
            ObjectNode full = mapper.valueToTree(booking);
            ObjectNode projected = mapper.createObjectNode();
            projected.set("id", full.get("id"));
            for (String field : requested) {
                if (!"id".equals(field) && full.has(field)) {
                    projected.set(field, full.get(field));
                }
            }
            itemsNode.add(projected);
        }

        ObjectNode root = mapper.createObjectNode();
        root.set("items", itemsNode);
        root.set("page", mapper.valueToTree(page));
        return root;
    }

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response getBooking(@PathParam("id") String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        return Response.ok(booking).build();
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
    public Response deleteBooking(@PathParam("id") String id) {
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
