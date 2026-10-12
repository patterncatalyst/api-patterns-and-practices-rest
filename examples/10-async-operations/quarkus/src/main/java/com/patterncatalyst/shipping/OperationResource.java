package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Operation;
import com.patterncatalyst.shipping.model.OperationStatus;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.ws.rs.DELETE;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

/**
 * The poll/cancel half of Ch10's long-running operation protocol
 * (BookingResource.requestConfirmation is the 202 Accepted half):
 *
 * <ul>
 *   <li>{@code GET /operations/{id}} — 200 + Operation while
 *       PENDING/RUNNING/FAILED; 303 + Location once SUCCEEDED.</li>
 *   <li>{@code DELETE /operations/{id}} — 204; cancels a still-running
 *       operation (operation -&gt; FAILED, booking stays PENDING).</li>
 * </ul>
 */
@Path("/operations")
public class OperationResource {

    @Inject
    OperationStore store;

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response get(@PathParam("id") String id) {
        Operation operation = store.get(id);
        if (operation == null) {
            return notFound(id);
        }
        if (operation.status() == OperationStatus.SUCCEEDED) {
            return Response.status(Response.Status.SEE_OTHER)
                    .header("Location", operation.resource())
                    .build();
        }
        return Response.ok(operation).build();
    }

    @DELETE
    @Path("/{id}")
    public Response cancel(@PathParam("id") String id) {
        if (store.get(id) == null) {
            return notFound(id);
        }
        // Idempotent either way: a no-op against an already-terminal
        // operation still reports 204, the same way DELETE /bookings/{id}
        // treats a repeat cancel.
        store.cancel(id);
        return Response.noContent().build();
    }

    private Response notFound(String id) {
        Problem problem = new Problem("Operation not found", 404, "No operation with id " + id);
        return Response.status(404).type("application/problem+json").entity(problem).build();
    }
}
