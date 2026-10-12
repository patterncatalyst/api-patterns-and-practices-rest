package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Problem;
import jakarta.validation.ConstraintViolationException;
import jakarta.ws.rs.NotAcceptableException;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import org.jboss.logging.Logger;

import java.util.stream.Collectors;

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
                    "Validation failed", 400,
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
            return Response.status(500).type("application/problem+json").entity(problem).build();
        }
    }
}
