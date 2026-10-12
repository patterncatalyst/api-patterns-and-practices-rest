package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Problem;
import jakarta.ws.rs.WebApplicationException;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import org.jboss.logging.Logger;

/**
 * Last-resort safety net so an unexpected bug never leaks a bare stack
 * trace to the client — every Ch16 error path this chapter actually
 * exercises (404 on an unknown booking) is built by hand in
 * BookingResource/StreamingResource already. Mirrors
 * ../04-contract-first/ProblemMappers.java, trimmed to just the mapper this
 * chapter's resources don't already cover (no PATCH/Accept negotiation
 * here).
 */
public final class ProblemMappers {

    private ProblemMappers() {
    }

    @Provider
    public static class ThrowableExceptionMapper implements ExceptionMapper<Throwable> {
        private static final Logger LOG = Logger.getLogger(ThrowableExceptionMapper.class);

        @Override
        public Response toResponse(Throwable exception) {
            if (exception instanceof WebApplicationException wae) {
                return wae.getResponse();
            }
            LOG.error("Unhandled exception", exception);
            Problem problem = new Problem("Internal Server Error", 500, "An unexpected error occurred");
            return Response.status(500).type(MediaType.APPLICATION_JSON).entity(problem).build();
        }
    }
}
