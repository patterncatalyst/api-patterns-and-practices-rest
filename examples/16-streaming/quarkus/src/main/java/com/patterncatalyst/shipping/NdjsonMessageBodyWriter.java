package com.patterncatalyst.shipping;

import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.MultivaluedMap;
import jakarta.ws.rs.ext.MessageBodyWriter;
import jakarta.ws.rs.ext.Provider;

import java.io.IOException;
import java.io.OutputStream;
import java.lang.annotation.Annotation;
import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;

/**
 * Writes each streamed `application/x-ndjson` line as RAW bytes, not as a
 * JSON-quoted string. Without a dedicated writer registered for this exact
 * media type, Quarkus REST's Jackson provider — which quarkus-rest-jackson
 * registers broadly enough to catch media types it doesn't recognize —
 * wins the writer lookup for `Multi<String>` and serializes each line as a
 * JSON STRING VALUE (wrapped in quotes, its embedded newline escaped to
 * `\n`) instead of writing the line's bytes as-is. That defeats the entire
 * point of newline-delimited JSON: each line stops being independently
 * parseable JSON and becomes one escaped string inside an invisible
 * larger structure. This writer wins the lookup for exactly
 * `application/x-ndjson` + `String`, so StreamingResource#exportEvents's
 * pre-serialized JSON lines (already built with ObjectMapper, `\n`
 * appended) go to the wire untouched.
 */
@Provider
@Produces("application/x-ndjson")
public class NdjsonMessageBodyWriter implements MessageBodyWriter<String> {

    @Override
    public boolean isWriteable(Class<?> type, Type genericType, Annotation[] annotations, MediaType mediaType) {
        return String.class.isAssignableFrom(type);
    }

    @Override
    public void writeTo(String line, Class<?> type, Type genericType, Annotation[] annotations,
            MediaType mediaType, MultivaluedMap<String, Object> httpHeaders, OutputStream entityStream)
            throws IOException {
        entityStream.write(line.getBytes(StandardCharsets.UTF_8));
    }
}
