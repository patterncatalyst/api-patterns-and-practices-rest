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
 * Makes sure content-negotiation errors the JAX-RS runtime raises ITSELF
 * (not just the ones BookingResource builds by hand) still come back as
 * {@code application/problem+json} with a schema-conforming {@code Problem}
 * body, exactly like every other error in this chapter.
 *
 * <p>Two cases never reach a BookingResource method at all — RESTEasy
 * Reactive rejects the request before any resource code runs:
 * <ul>
 *   <li>A request body arrives with a {@code Content-Type} the matched
 *       resource method's {@code @Consumes} doesn't declare — e.g.
 *       {@code Content-Type: text/plain} on {@code POST /bookings}, or
 *       the wrong type on {@code PATCH}'s
 *       {@code application/merge-patch+json} — raising
 *       {@link NotSupportedException} (415).</li>
 *   <li>The client's {@code Accept} header can't be satisfied by any
 *       media type the matched resource method's {@code @Produces}
 *       declares — e.g. {@code Accept: application/xml} against an
 *       endpoint that only produces {@code application/json} /
 *       {@code application/problem+json} — raising
 *       {@link NotAcceptableException} (406).</li>
 * </ul>
 */
public final class ProblemMappers {

    private ProblemMappers() {
    }

    @Provider
    public static class NotSupportedExceptionMapper implements ExceptionMapper<NotSupportedException> {
        @Override
        public Response toResponse(NotSupportedException exception) {
            Problem problem = new Problem(
                    "Unsupported Media Type", 415,
                    "The request's Content-Type is not one this endpoint accepts.");
            return Response.status(415).type("application/problem+json").entity(problem).build();
        }
    }

    @Provider
    public static class NotAcceptableExceptionMapper implements ExceptionMapper<NotAcceptableException> {
        @Override
        public Response toResponse(NotAcceptableException exception) {
            Problem problem = new Problem(
                    "Not Acceptable", 406,
                    "The Accept header does not match a media type this endpoint can produce "
                            + "(application/json, application/problem+json).");
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
