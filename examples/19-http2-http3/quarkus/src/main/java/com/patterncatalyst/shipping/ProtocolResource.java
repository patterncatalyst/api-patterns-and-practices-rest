package com.patterncatalyst.shipping;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Context;
import jakarta.ws.rs.core.MediaType;

import io.vertx.core.http.HttpServerRequest;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Ch19's whole point: the response body barely matters — what matters is
 * the wire protocol that carried it. This single endpoint reports back the
 * negotiated HTTP version Vert.x saw on the connection, so a human (or
 * verify.sh) can confirm from the response itself, not just from curl's own
 * {@code %{http_version}}, which protocol was actually used.
 *
 * <p>Quarkus/Vert.x negotiates HTTP/2 two ways: ALPN over TLS (the usual
 * path for browsers/h2), or cleartext "h2c" via prior knowledge — the
 * client sends the HTTP/2 connection preface immediately with no upgrade
 * handshake. This compose stack has no TLS configured, so h2c prior
 * knowledge is the only way to reach this app over HTTP/2; see README.md
 * for the exact curl invocation.</p>
 */
@Path("/")
public class ProtocolResource {

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public Map<String, Object> root(@Context HttpServerRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("service", "shipping-quarkus-ch19");
        body.put("httpVersion", request.version().name());
        return body;
    }
}
