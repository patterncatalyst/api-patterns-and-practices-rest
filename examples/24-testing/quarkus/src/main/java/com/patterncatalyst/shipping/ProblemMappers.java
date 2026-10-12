package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Problem;
import jakarta.ws.rs.NotAcceptableException;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import org.jboss.logging.Logger;

/**
 * Makes sure errors the JAX-RS runtime raises itself (not just the ones
 * BookingResource builds by hand) still come back as
 * application/problem+json, and that an unexpected bug never leaks a bare
 * stack trace to a test client — see examples/04-contract-first's
 * ProblemMappers.java for the fuller version (this chapter has no PATCH
 * endpoint, so NotSupportedException isn't needed here).
 */
public final class ProblemMappers {

    private ProblemMappers() {
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
            return Response.status(500).type("application/problem+json").entity(problem).build();
        }
    }
}
