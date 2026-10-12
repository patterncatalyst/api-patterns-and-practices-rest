package com.patterncatalyst.shipping;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

/**
 * Ch0 boot skeleton. Proves the toolchain — Quarkus on UBI 10 JVM mode —
 * builds, starts, and answers a request. The real shipping/cargo resource
 * model (bookings, cargo, routes) arrives contract-first in Ch4.
 */
@Path("/")
public class BootResource {

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public BootStatus status() {
        return new BootStatus("shipping-quarkus", "up");
    }

    public record BootStatus(String service, String status) {
    }
}
