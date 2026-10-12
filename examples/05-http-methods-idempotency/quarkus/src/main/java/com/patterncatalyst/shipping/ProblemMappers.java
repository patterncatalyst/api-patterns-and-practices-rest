package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Problem;
import jakarta.validation.ConstraintViolationException;
import jakarta.ws.rs.NotAcceptableException;
import jakarta.ws.rs.NotSupportedException;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import org.jboss.logging.Logger;

import java.util.stream.Collectors;

/**
 * Makes sure errors the JAX-RS runtime raises itself (not just the ones
 * BookingResource builds by hand) still come back as
 * application/problem+json — e.g. a PATCH sent with the wrong
 * Content-Type never reaches the resource method at all; RESTEasy Reactive
 * rejects it with NotSupportedException before our code runs.
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
                    "PATCH requires Content-Type: application/merge-patch+json");
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

    /**
     * Quarkus Bean Validation: {@code @Valid} on a resource method's
     * request-body parameter (see BookingResource) throws this when a
     * constraint fails — e.g. a missing {@code origin.unLocode} or a
     * {@code dimensions.weightKg <= 0}. Reproduces the same 400
     * {@code application/problem+json} shape the hand-rolled checks it
     * replaced used to return.
     */
    @Provider
    public static class ConstraintViolationExceptionMapper implements ExceptionMapper<ConstraintViolationException> {
        @Override
        public Response toResponse(ConstraintViolationException exception) {
            String detail = exception.getConstraintViolations().stream()
                    .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                    .sorted()
                    .collect(Collectors.joining("; "));
            Problem problem = new Problem(
                    "Invalid request", 400,
                    detail.isEmpty() ? "The request failed validation" : detail);
            return Response.status(400).type("application/problem+json").entity(problem).build();
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
