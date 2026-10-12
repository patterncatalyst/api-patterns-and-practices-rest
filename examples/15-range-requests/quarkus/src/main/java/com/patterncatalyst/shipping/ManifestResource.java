package com.patterncatalyst.shipping;

import com.patterncatalyst.shipping.model.Problem;

import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.HEAD;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.core.Response;

import org.jboss.resteasy.reactive.RestHeader;
import org.jboss.resteasy.reactive.RestPath;

import java.util.Arrays;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * `/bookings/{bookingId}/manifest` — a large binary resource of a KNOWN,
 * fixed size, with HTTP Range support (RFC 9110 §14). This is Ch15's whole
 * point: a client can ask for the full manifest, or a byte slice of it
 * (`Range: bytes=START-END` / an open `bytes=START-`), and get back a 206
 * Partial Content with an exact Content-Range — or a 416 if the requested
 * start is past the end of the resource.
 */
@Path("/bookings/{bookingId}/manifest")
public class ManifestResource {

    // bytes=START-END, bytes=START- (open), or bytes=-SUFFIXLEN (suffix).
    private static final Pattern RANGE_PATTERN = Pattern.compile("^bytes=(\\d*)-(\\d*)$");

    @Inject
    BookingStore store;

    @HEAD
    public Response head(@RestPath String bookingId) {
        if (store.get(bookingId) == null) {
            return notFound(bookingId);
        }
        byte[] manifest = ManifestGenerator.forBooking(bookingId);
        return Response.ok()
                .header("Accept-Ranges", "bytes")
                .header("Content-Length", manifest.length)
                .build();
    }

    @GET
    public Response get(@RestPath String bookingId, @RestHeader("Range") String rangeHeader) {
        if (store.get(bookingId) == null) {
            return notFound(bookingId);
        }

        byte[] manifest = ManifestGenerator.forBooking(bookingId);
        int total = manifest.length;

        if (rangeHeader == null || rangeHeader.isBlank()) {
            return fullResponse(manifest, total);
        }

        Matcher matcher = RANGE_PATTERN.matcher(rangeHeader.trim());
        if (!matcher.matches()) {
            // A malformed Range header is ignored per RFC 9110 §14.2 — the
            // server falls back to serving the full representation rather
            // than rejecting the request outright.
            return fullResponse(manifest, total);
        }

        String startGroup = matcher.group(1);
        String endGroup = matcher.group(2);
        long start;
        long end;

        if (startGroup.isEmpty()) {
            if (endGroup.isEmpty()) {
                // "bytes=-" with neither bound: not a satisfiable range.
                return unsatisfiable(total);
            }
            // Suffix range: bytes=-N -> the last N bytes of the resource.
            long suffixLength = Long.parseLong(endGroup);
            start = Math.max(0, total - suffixLength);
            end = total - 1;
        } else {
            start = Long.parseLong(startGroup);
            end = endGroup.isEmpty() ? total - 1 : Long.parseLong(endGroup);
        }

        if (start >= total || start > end) {
            return unsatisfiable(total);
        }
        end = Math.min(end, total - 1);

        int length = (int) (end - start + 1);
        byte[] slice = Arrays.copyOfRange(manifest, (int) start, (int) start + length);

        return Response.status(206)
                .entity(slice)
                .type("application/pdf")
                .header("Accept-Ranges", "bytes")
                .header("Content-Range", "bytes " + start + "-" + end + "/" + total)
                .header("Content-Length", length)
                .build();
    }

    private Response fullResponse(byte[] manifest, int total) {
        return Response.ok(manifest)
                .type("application/pdf")
                .header("Accept-Ranges", "bytes")
                .header("Content-Length", total)
                .build();
    }

    private Response unsatisfiable(int total) {
        return Response.status(416)
                .header("Content-Range", "bytes */" + total)
                .build();
    }

    private Response notFound(String bookingId) {
        Problem problem = new Problem("Booking not found", 404, "No booking with id " + bookingId);
        return Response.status(404).type("application/problem+json").entity(problem).build();
    }
}
