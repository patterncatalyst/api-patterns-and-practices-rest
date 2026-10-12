package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Problem;
import jakarta.validation.ConstraintViolationException;
import jakarta.ws.rs.WebApplicationException;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import org.jboss.logging.Logger;

import java.util.stream.Collectors;

/**
 * Last-resort safety net so an unexpected bug never leaks a bare stack
 * trace to the client — every Ch16 error path this chapter actually
 * exercises (404 on an unknown booking) is built by hand in
 * BookingResource/StreamingResource already. Mirrors
 * ../04-contract-first/ProblemMappers.java, trimmed to just the mappers this
 * chapter's resources don't already cover (no PATCH/Accept negotiation
 * here, but POST /bookings does rely on Bean Validation — see
 * ConstraintViolationExceptionMapper below).
 */
public final class ProblemMappers {

    private ProblemMappers() {
    }

    /**
     * Quarkus Bean Validation: {@code @Valid} on {@code createBooking}'s
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
