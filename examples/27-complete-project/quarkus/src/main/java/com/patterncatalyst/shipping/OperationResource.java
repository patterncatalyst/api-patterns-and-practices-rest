package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Operation;
import com.patterncatalyst.shipping.model.OperationStatus;
import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import org.jboss.resteasy.reactive.RestPath;

/**
 * Ch10's poll half of the long-running operation protocol
 * (BookingResource.requestConfirmation is the 202 Accepted half):
 * `GET /operations/{id}` returns 200 + Operation while PENDING/RUNNING,
 * and 303 See Other + Location once SUCCEEDED.
 */
@Path("/operations")
public class OperationResource {

    @Inject
    OperationStore store;

    @GET
    @Path("/{id}")
    @Produces(MediaType.APPLICATION_JSON)
    public Response get(@RestPath String id) {
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

    private Response notFound(String id) {
        Problem problem = new Problem("Operation not found", 404, "No operation with id " + id);
        return Response.status(404).type("application/problem+json").entity(problem).build();
    }
}
