package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Problem;
import jakarta.ws.rs.NotAcceptableException;
import jakarta.ws.rs.NotSupportedException;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import org.jboss.logging.Logger;

/**
 * Makes sure errors the JAX-RS runtime raises itself (not just the ones
 * BookingResource builds by hand) still come back as
 * application/problem+json.
 */
public final class ProblemMappers {

    private ProblemMappers() {
    }

    @Provider
    public static class NotSupportedExceptionMapper implements ExceptionMapper<NotSupportedException> {
        @Override
        public Response toResponse(NotSupportedException exception) {
            Problem problem = new Problem("Unsupported Media Type", 415, exception.getMessage());
            return Response.status(415).type("application/problem+json").entity(problem).build();
        }
    }

    @Provider
    public static class NotAcceptableExceptionMapper implements ExceptionMapper<NotAcceptableException> {
        @Override
        public Response toResponse(NotAcceptableException exception) {
            Problem problem = new Problem("Not Acceptable", 406, exception.getMessage());
            return Response.status(406).type("application/problem+json").entity(problem).build();
        }
    }

    /** Last-resort safety net so an unexpected bug never leaks a bare stack trace. */
    @Provider
    public static class ThrowableExceptionMapper implements ExceptionMapper<Throwable> {
        private static final Logger LOG = Logger.getLogger(ThrowableExceptionMapper.class);

        @Override
        public Response toResponse(Throwable exception) {
            if (exception instanceof jakarta.ws.rs.WebApplicationException wae) {
                return wae.getResponse();
            }
            LOG.error("Unhandled exception", exception);
            Problem problem = new Problem("Internal Server Error", 500, "An unexpected error occurred");
            return Response.status(500).type(MediaType.APPLICATION_JSON).entity(problem).build();
        }
    }
}
