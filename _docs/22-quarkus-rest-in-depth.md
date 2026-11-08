---
title: "Quarkus REST in depth"
order: 22
part: "Multi-protocol contracts & framework deep-dives"
description: "Quarkus REST resolves parameter bindings at build time instead of by reflection, and a reactive Multi stream needs its own NDJSON writer to avoid double-encoding."
duration: "27 min"
---

## Learning objectives

By the end of this chapter you can:

- Explain why Quarkus REST resolves `@RestHeader` and `@RestQuery` bindings through build-time generated code instead of runtime reflection, and what that buys in startup, allocation and native-image support.
- Bound an NDJSON export with `@RestQuery` and a clamp such as `EventGenerator.clampLimit`.
- Write a dedicated `MessageBodyWriter` (`NdjsonMessageBodyWriter`) so Jackson doesn't double-encode a pre-serialized `Multi<String>`.
- Decide when a `Multi` is the right return type for a REST response.
- Name where LangChain4j, Camel Quarkus with CXF, and JobRunr extend a Quarkus REST service.

## Why this matters

Quarkus REST (formerly RESTEasy Reactive) decides how a request maps onto a Java method at build time, once, instead of at request time, repeatedly. `curl` can't see the difference: a header or query parameter binds the same way either way. The difference is in startup time, allocation and whether the service compiles to a native image. Two endpoints show the mechanism, and three ecosystem pieces show where a REST service on Quarkus goes next.

{% include excalidraw.html file="22-quarkus-rest-in-depth" alt="Quarkus REST's build-time bytecode generation resolving @RestHeader and @RestQuery bindings ahead of request time, alongside the reactive NDJSON export's tick-driven Multi pipeline delivering one line at a time through a dedicated MessageBodyWriter to the client." caption="Figure 22.1: Build-time parameter binding and tick-driven reactive streaming in Quarkus REST." %}

## Build-time metadata instead of runtime reflection

Classic JAX-RS containers (RESTEasy Classic, Jersey) walk a method's `Parameter` array through `java.lang.reflect` on every request, read each `@HeaderParam` or `@QueryParam`, and coerce the value. They also scan the classpath at startup for `@Path` classes.

Quarkus REST does that work once, during the build. A processor reads `@Path`, `@GET`, `@RestHeader` and `@RestQuery` and generates a class that reads the header directly and calls the target method. At request time there's no `Method.invoke()`, no parameter walk and no annotation lookup.

| Effect | Why |
|---|---|
| Faster startup | No classpath scan for `@Path` classes and no reflective metadata to build before the first request; the dispatch tables already exist |
| Lower allocation | Reflective calls allocate and do bookkeeping the JIT can't fully remove; a generated direct call compiles like a hand-written `getHeader()` |
| Native-image support | GraalVM must know every reflectively reachable class ahead of time; a framework that already resolved its bindings has nothing left to register |

Behavior is unchanged; cost isn't.

## `@RestHeader` and `@RestQuery`

`org.jboss.resteasy.reactive.RestHeader` is the Quarkus REST counterpart of `@HeaderParam`. An absent header binds as `null`:

```java
static final String DEFAULT_TENANT = "public";

@GET
@Path("/tenant")
@Produces(MediaType.APPLICATION_JSON)
public Map<String, Object> tenantInfo(@RestHeader("X-Tenant") String tenant) {
    boolean defaulted = tenant == null;
    Map<String, Object> body = new LinkedHashMap<>();
    body.put("tenant", defaulted ? DEFAULT_TENANT : tenant);
    body.put("defaulted", defaulted);
    return body;
}
```

Send `X-Tenant` and the body echoes it with `defaulted: false`; omit it and the body reports `public` with `defaulted: true`. The fallback is explicit in the method because `@DefaultValue` supplies only a fixed literal; a real tenant default may come from configuration.

`@RestQuery` does the same for query strings, and here the value drives how much work the server does:

```java
@GET
@Path("/bookings/events/export")
@Produces("application/x-ndjson")
public Multi<String> exportEvents(@RestQuery("limit") @DefaultValue("5") int limit) {
    int effectiveLimit = EventGenerator.clampLimit(limit);

    return Multi.createFrom().ticks()
            .startingAfter(Duration.ofMillis(EventGenerator.STREAM_INTERVAL_MILLIS))
            .every(Duration.ofMillis(EventGenerator.STREAM_INTERVAL_MILLIS))
            .onItem().transform(Long::intValue)
            .select().first(effectiveLimit)
            .onItem().transform(i -> toJsonLine(EventGenerator.eventFor(EventGenerator.SAMPLE_BOOKING_ID, i)));
}
```

`@DefaultValue("5")` fits here: five is a fixed default, and the primitive `int` leaves no `null` case. `clampLimit` bounds `limit` to `[1, MAX_LIMIT]` with `MAX_LIMIT = 20`, so `limit=3` streams 3 records and `limit=999` streams 20. The clamp is a denial-of-service guard: the connection stays open for about `limit * 200 ms`, so an unclamped `limit=1000000` would hold it for over fifty hours. A query parameter that sets resource consumption needs an upper bound in code.

## Streaming a response with `Multi`

A response that is large, slow to assemble or open-ended (a bulk export, a file download, an NDJSON or SSE feed) shouldn't be built as one list and serialized at the end. Thread-per-request holds an OS thread for the whole response, and threads cost stack memory and context switches, so a server with many long-lived responses runs out of threads before CPU or bandwidth. Mutiny's `Multi<String>` emits each item when it is ready instead, and the event loop writes it to the socket without a blocked thread or a buffered body; the ceiling on concurrent streams becomes memory and scheduling, not a thread count.

 `exportEvents` ticks every `STREAM_INTERVAL_MILLIS`, caps the count with `.select().first(...)` and turns each tick into one NDJSON line. The event loop that owns the connection flushes each line before the next tick. Backpressure applies: `Multi` emits the next item only when the response's outbound buffer can take it, so a fast producer can't pile up data the socket can't drain.

## The NDJSON double-encoding pitfall

`@Produces("application/x-ndjson")` on a `Multi<String>` doesn't by itself produce raw NDJSON. The Jackson integration (`quarkus-rest-jackson`) registers a writer broad enough to win the lookup for `String`, even on a media type it doesn't know. It then serializes the line as a quoted JSON string and escapes the newline to `\n`. Each record ends up wrapped in an outer string, which breaks newline-delimited JSON.

A `@Provider` scoped to exactly `application/x-ndjson` and `String` wins instead:

```java
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
```

`toJsonLine` already serializes the event and appends the newline, so the writer only has to emit bytes. The same applies to any pre-serialized text on a media type a general writer might also claim.

A buffered response can return the right status, `Content-Type` and body byte for byte while having been produced in one burst. Only the arrival time of each line tells incremental delivery from a buffered body wearing a streaming media type.

## Where Quarkus REST extends

| Extension | Use it for |
|---|---|
| LangChain4j | Token-by-token LLM output. A streaming chat model maps onto a `Multi<String>` over `text/event-stream`, one SSE event per token, with the same backpressure as the NDJSON export |
| Camel Quarkus and CXF | Systems that don't speak REST. Camel routes handle queues, file drops and protocol bridges; CXF exposes or consumes SOAP and WSDL behind a REST facade |
| JobRunr | Slow work behind `202 Accepted` and a status URL. It persists job state in the application's database and handles retries, scheduling and recurring jobs without a separate broker |

## Decision rule

| Choice | Take it when | Skip it when |
|---|---|---|
| Build-time binding | The target is serverless, autoscaled or a native image, so every cold instance pays startup | One long-lived process on a fixed VM, never measured on cold start |
| `Multi` streaming | The response is large, slow to assemble or open-ended | One small, quickly computed JSON object: a synchronous method is simpler |
| Blocking, thread-per-request code | The team knows it and load never approaches the thread ceiling | Many concurrent long-lived responses |

> **🤖 Explore with your agent**
>
> "In `examples/22-quarkus-rest-depth`, add `GET /bookings/events/export/sse` that returns the same `EventGenerator` events as `text/event-stream` using `Multi<String>`, reusing `EventGenerator.clampLimit` for `limit`. Say whether it needs its own `MessageBodyWriter` and why."
>
> Check: `./verify.sh` still passes, and `curl -N` against the new endpoint prints events spread over time.

## Build, run, observe

```bash
cd examples/22-quarkus-rest-depth && ./verify.sh
```

`verify.sh` starts the Quarkus service (port 8102) with `docker compose`. `X-Tenant` is echoed or defaulted, `limit` sets and clamps the record count, every exported record validates against `#/$defs/BookingEvent`, and a timed read shows incremental delivery: with `limit=5` at a 200 ms tick, the first and last lines arrive about 0.8 seconds apart, against a 0.5-second floor. It prints `PASS` when all hold. The full output is in `examples/22-quarkus-rest-depth/README.md`.

- Collect all events and return `Multi.createFrom().item(all.toString())`: status, content type and per-line validity stay correct, the spread drops near zero, and the run fails as buffered.
- Delete `NdjsonMessageBodyWriter`: Jackson writes each line as an escaped JSON string and schema validation fails with `is not of type 'object'`.

## For deeper coverage

- [Quarkus REST guide](https://quarkus.io/guides/rest): build-time parameter binding, `@RestHeader`, `@RestQuery` and reactive return types.
- Jakub Gough, Daniel Bryant & Matthew Auburn, *Mastering API Architecture* (O'Reilly, 2022): framework and runtime trade-offs behind a REST layer.
- Mike Amundsen, *RESTful Web API Patterns and Practices Cookbook* (O'Reilly, 2022): streaming and resource-shaping patterns at the HTTP layer.
- Cloud Native Design Patterns, "Anti-patterns" chapter: the client-controlled limit without a clamp, which `EventGenerator.clampLimit` guards against.
