package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Booking;
import com.patterncatalyst.shipping.model.BookingCollection;
import com.patterncatalyst.shipping.model.BookingRequest;
import com.patterncatalyst.shipping.model.BookingStatus;
import com.patterncatalyst.shipping.model.BookingV1;
import com.patterncatalyst.shipping.model.Cargo;
import com.patterncatalyst.shipping.model.CargoRequest;
import com.patterncatalyst.shipping.model.DeletionAudit;
import com.patterncatalyst.shipping.model.Link;
import com.patterncatalyst.shipping.model.Operation;
import com.patterncatalyst.shipping.model.PageMeta;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.DELETE;
import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.HeaderParam;
import jakarta.ws.rs.POST;
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
import java.util.List;
import java.util.Map;

/**
 * Ch27 complete-project anchor: the booking service that exercises the
 * whole book's flow end to end over a single cohesive resource model —
 * contract-first create/read (Ch4), keyset pagination (Ch8), async
 * confirmation (Ch10, see {@link OperationResource}), HATEOAS `_links`
 * (Ch12), soft delete + GDPR purge (Ch13), and media-type versioning
 * (Ch14). The NDJSON manifest export (Ch16) lives in
 * {@link ManifestResource}; the background CloudEvents publish (Ch21) is
 * driven from {@link OperationStore} once a confirmation completes.
 */
@Path("/bookings")
public class BookingResource {

    private static final int DEFAULT_LIMIT = 20;
    /** DoS guard: `limit` above this is CLAMPED, never honored unbounded. */
    private static final int MAX_LIMIT = 100;

    @Inject
    BookingStore store;

    @Inject
    OperationStore operationStore;

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

        // A literal header string, NOT Response.created(URI) — keeps the
        // Location header shape identical to the Python stack's relative
        // `/bookings/{id}`.
        return Response.status(Response.Status.CREATED)
                .header("Location", "/bookings/" + booking.id())
                .entity(withLinks(booking))
                .build();
    }

    /** Ch8 keyset pagination + Ch12 collection-level HATEOAS links. */
    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Response listBookings(
            @QueryParam("limit") Integer limit,
            @QueryParam("cursor") String cursor) {
        List<Booking> visible = store.listVisible();
        int effectiveLimit = clampLimit(limit);

        String afterKey = (cursor != null && !cursor.isBlank()) ? decodeCursor(cursor) : null;
        List<Booking> candidates = (afterKey == null)
                ? visible
                : visible.stream().filter(b -> b.id().compareTo(afterKey) > 0).toList();
        List<Booking> page = candidates.stream().limit(effectiveLimit).toList();
        String nextCursor = (candidates.size() > effectiveLimit) ? encodeCursor(page.get(page.size() - 1).id()) : null;

        List<Booking> withLinks = page.stream().map(this::withLinks).toList();
        PageMeta pageMeta = new PageMeta(effectiveLimit, withLinks.size(), nextCursor);
        Map<String, Link> collectionLinks = HateoasLinks.forCollection(effectiveLimit, nextCursor);
        return Response.ok(new BookingCollection(withLinks, pageMeta, collectionLinks)).build();
    }

    /**
     * Ch14 media-type versioning (Accept negotiates v1 vs v2) + Ch13 soft
     * delete (a cancelled booking 404s by default; `includeDeleted=true`
     * is the audit/compliance view).
     */
    @GET
    @Path("/{id}")
    @Produces({MediaType.APPLICATION_JSON, VersionMapper.MEDIA_TYPE_V1, VersionMapper.MEDIA_TYPE_V2})
    public Response getBooking(
            @PathParam("id") String id,
            @HeaderParam("Accept") String accept,
            @QueryParam("includeDeleted") @DefaultValue("false") boolean includeDeleted) {
        Booking booking = includeDeleted ? store.get(id) : store.getVisible(id);
        if (booking == null) {
            return notFound(id);
        }

        if (VersionMapper.wantsV1(accept)) {
            BookingV1 v1 = VersionMapper.toV1(booking);
            return Response.ok(v1).type(VersionMapper.MEDIA_TYPE_V1).header("Vary", "Accept").build();
        }

        Response.ResponseBuilder response = Response.ok(withLinks(booking))
                .type(VersionMapper.MEDIA_TYPE_V2)
                .header("Vary", "Accept");
        if (includeDeleted && booking.status() == BookingStatus.CANCELLED) {
            DeletionAudit audit = store.getAudit(id);
            if (audit != null) {
                response.header("X-Audit-Deleted-At", audit.deletedAt());
                response.header("X-Audit-Reason", audit.reason());
            }
        }
        return response.build();
    }

    /** Ch10: 202 Accepted -> poll /operations/{id} -> 303 (see OperationResource). */
    @POST
    @Path("/{id}/confirmation")
    @Produces(MediaType.APPLICATION_JSON)
    public Response requestConfirmation(@PathParam("id") String id) {
        Booking booking = store.get(id);
        if (booking == null) {
            return notFound(id);
        }
        if (booking.status() != BookingStatus.PENDING) {
            return problem(409, "Booking not confirmable",
                    "Booking " + id + " is not PENDING (status=" + booking.status() + ")");
        }

        String opId = "op_" + Ulid.generate();
        Operation operation = operationStore.startConfirmation(opId, id, store);
        return Response.status(Response.Status.ACCEPTED)
                .header("Location", "/operations/" + opId)
                .entity(operation)
                .build();
    }

    /** Ch13: soft delete — status -> CANCELLED, audit recorded, hidden by default. */
    @DELETE
    @Path("/{id}")
    public Response deleteBooking(
            @PathParam("id") String id,
            @QueryParam("reason") @DefaultValue("user-requested cancellation") String reason) {
        Booking existing = store.get(id);
        if (existing == null) {
            return notFound(id);
        }
        store.softDelete(id, reason);
        return Response.noContent().build();
    }

    /** Ch13: GDPR "right to erasure" — hard-deletes the booking AND its audit trail. */
    @DELETE
    @Path("/{id}/purge")
    public Response purgeBooking(@PathParam("id") String id) {
        boolean existed = store.purge(id);
        if (!existed) {
            return notFound(id);
        }
        return Response.noContent().build();
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    private Booking withLinks(Booking booking) {
        Map<String, Link> links = HateoasLinks.forBooking(booking.id(), booking.status());
        return new Booking(
                booking.id(), booking.status(), booking.origin(), booking.destination(), booking.cargo(),
                booking.quote(), booking.requestedPickup(), booking.createdAt(), booking.updatedAt(), links);
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

    private static String encodeCursor(String id) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(id.getBytes(StandardCharsets.UTF_8));
    }

    private static String decodeCursor(String cursor) {
        try {
            return new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            return null;
        }
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
