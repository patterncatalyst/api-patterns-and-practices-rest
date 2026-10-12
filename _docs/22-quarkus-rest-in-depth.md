---
title: "Quarkus REST in depth"
order: 22
part: "Multi-protocol contracts & framework deep-dives"
description: "Why Quarkus REST resolves parameter bindings at build time instead of by reflection, how that shows up in @RestHeader/@RestQuery, and why reactive Multi streaming needs its own NDJSON writer to avoid double-encoding."
duration: "27 min"
---

Every REST chapter so far has treated "the framework" as a black box that turns an annotated method into a working endpoint, judged only by what crossed the wire — status codes, headers, bodies. This chapter opens the box for one stack. Quarkus REST, the framework this book's Quarkus examples have used since Chapter 1 under the name RESTEasy Reactive, makes a specific, consequential choice about *when* it figures out how a request maps onto a Java method: at build time, once, rather than at request time, repeatedly. That choice is invisible to `curl` (a `GET` with a header or a query parameter looks the same whether the framework resolved it by reflection or by code generated months earlier), but it's the reason Quarkus starts in milliseconds and runs lean in a container. This chapter grounds that claim in two real endpoints from `examples/22-quarkus-rest-depth/`, then widens out to three more pieces of the Quarkus REST ecosystem (SSE from an LLM client, integration routing, background jobs) that round out why a team reaches for this stack for REST work, not just because it happens to run Java.

## Build-time metadata instead of runtime reflection

Classic JAX-RS (RESTEasy Classic, Jersey, most of what "a REST framework in Java" meant for over a decade) resolves a method's parameters the same way every time a request arrives: it looks at the target method, walks its `Parameter` array via `java.lang.reflect`, reads off each parameter's `@HeaderParam`/`@QueryParam`/`@PathParam` annotation, and uses that reflective metadata to pull the right header or query string value out of the incoming request and coerce it to the right Java type. That happens on *every single request*, to *every annotated method* the container might dispatch to. The container also has to discover which methods exist and which `@Path` they answer to in the first place, which classically means a classpath scan at startup (walking every JAR on the classpath looking for `@Path`-annotated classes) before the application can answer its first request.

Quarkus REST does the equivalent work once, ahead of time, as part of the Quarkus build. A build-time extension (a Quarkus processor that runs during `mvn package` or `quarkus:dev`'s initial compile, not during a request) reads the same annotations a developer writes (`@Path`, `@GET`, `@RestHeader`, `@RestQuery`) and, instead of leaving them as metadata for a runtime dispatcher to interpret later, generates actual bytecode: a concrete Java class, compiled alongside the application, that reads `request.getHeader("X-Tenant")` directly and calls the target method with that value already in hand. There is no `Method.invoke()` at runtime, no walking an array of `Parameter` objects, no annotation lookup on the request path at all — just a generated class doing exactly what a developer would have hand-written to wire up that one binding, except the compiler wrote it instead of a person.

This is the same build-time-versus-runtime trade this book already made once, for a different concern: Chapter 4's `mp.openapi.scan.disable=true` sidesteps `smallrye-openapi`'s annotation scanner for a hand-authored document precisely because that scanner is itself a form of reflection-driven discovery, done at build or boot time rather than per request. Quarkus's bytecode-generation strategy for parameter binding is the more aggressive version of the same instinct applied to the request path itself: anything that can be figured out once, from source that doesn't change between requests, should be figured out once.

The payoff shows up in three places a reader can observe without benchmarking equipment. Startup time drops because there's no classpath scan hunting for `@Path` classes at boot and no reflective metadata to build before the first request can be served — Quarkus's build step already produced the dispatch tables the running process needs, so boot is mostly "load the generated classes and start listening," which is why a Quarkus app commonly reaches "ready" in well under a second where a classically-reflective container takes several. Memory and allocation profile improve because reflection isn't free at runtime either: every `Method.invoke()` call and every lookup into a `Parameter` array allocates and does bookkeeping the JVM can't fully optimize away, especially before the JIT warms that path up, whereas a generated direct call compiles to the same machine code a hand-written `getHeader()` call would produce. And native-image friendliness is close to existential: GraalVM's native-image compiler has to know, ahead of time, every class and method reachable through reflection, because it can't observe what a running JVM would discover dynamically — a framework built on heavy runtime reflection needs hand-maintained reflection configuration to compile to a native binary at all, while a framework that already resolved its bindings at build time has nothing left to reflect on. None of this changes behavior; all of it changes cost.

## `@RestHeader`: the same contract, resolved differently

`RestDepthResource.java`'s `tenantInfo` endpoint is the smallest possible demonstration of a header binding:

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

`org.jboss.resteasy.reactive.RestHeader` is Quarkus REST's own annotation, a drop-in replacement for classic JAX-RS's `@HeaderParam` — same job, bound at build time instead of resolved by reflection per request. On an absent `X-Tenant` header it injects `null` for the `String` parameter, exactly as `@HeaderParam` would, which is why the fallback to `"public"` is written out explicitly in the method body rather than delegated to `@DefaultValue`: `@DefaultValue` only ever supplies a fixed string literal baked in at the annotation site, which is fine for a query parameter with one obvious default but can't express "fall back to a value computed or looked up elsewhere," the way a real multi-tenant default might come from configuration rather than a hardcoded constant. Send the header and the response echoes it back with `defaulted: false`; omit it and the response reports the server's own default with `defaulted: true` — a request-scoped observable that makes the binding's behavior checkable without touching any internals.

The endpoint's HTTP contract here is unremarkable by design: a header read, a default applied, a JSON body returned. That unremarkable contract is exactly what the build-time machinery is for — a developer writes one annotation on one parameter, and the framework makes that annotation disappear into generated code before the first request ever lands, so `@RestHeader("X-Tenant") String tenant` is both the entire specification of the binding and, once built, nothing the running server has to figure out dynamically.

## `@RestQuery` driving the response, not just decorating it

The export endpoint goes a step further: the query parameter it binds doesn't just get echoed back, it determines how much work the server does and how long the response stays open.

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

`@RestQuery("limit")` is `@RestHeader`'s counterpart for query strings — classic JAX-RS's `@QueryParam`, resolved the same way. `@DefaultValue("5")` works fine here: `5` is the fixed value a caller gets by omitting `limit`, and the parameter's primitive `int` type leaves no `null` case to special-case. What matters is what happens once `limit` is in hand: `EventGenerator.clampLimit` enforces `[1, MAX_LIMIT]` with `MAX_LIMIT = 20`, so `limit=3` streams 3 records, `limit=8` streams 8, and `limit=999` comes back clamped to 20 rather than honored literally. That clamp is a deliberate DoS guard: an NDJSON export built on a ticking stream holds a connection open for roughly `limit * STREAM_INTERVAL_MILLIS` — at the 200ms tick this example uses, an unclamped `limit=1000000` would keep the connection alive for over fifty hours. A query parameter that drives resource consumption directly needs an upper bound enforced in code, independent of what a client claims to want.

## Reactive streaming as the idiomatic answer to "this response is big or slow to produce"

`exportEvents` doesn't build a list of records and serialize all of it before returning — it returns `Multi<String>`, Mutiny's reactive type for "zero or more items, delivered over time," and each item is a complete NDJSON line assembled only when the tick that produces it fires. `Multi.createFrom().ticks()` is a periodic source (one event every `STREAM_INTERVAL_MILLIS`) chained through `.select().first(effectiveLimit)` to cap the count, with each tick transformed into the next `BookingEvent`'s JSON line. The event loop already running the HTTP connection drives this: each tick fires, produces one line, and that line is flushed to the socket before the next tick is due, with no dedicated thread blocked for the stream's duration and no buffer accumulating the whole response in memory first.

That's the structural reason reactive streaming is Quarkus's idiomatic answer for a REST response that's large, slow to assemble, or open-ended — a big JSON export, a file download, an NDJSON or SSE feed. The alternative, a thread-per-request model where one OS thread sits blocked for the entire length of the response, scales by adding threads, and threads are expensive enough (stack memory, context-switch overhead, a hard ceiling on how many a JVM comfortably runs at once) that a server handling many concurrent long-lived responses this way runs out of threads before it runs out of CPU or bandwidth. An event loop processing many `Multi` subscriptions concurrently never blocks a thread waiting on the next tick; it reacts to each tick as it fires and moves on, so the practical ceiling on concurrent streaming responses is memory and scheduling overhead for the streams themselves, not a thread count. Backpressure is the other half of the story: `Multi`'s machinery only produces the next item when a downstream subscriber (here, the HTTP response's outbound buffer) is ready to accept it, which is what prevents a fast producer from piling up data the socket can't drain fast enough, something a naive "write everything to an `OutputStream` as fast as possible" loop has no defense against.

`verify.sh`'s timing proof makes the incremental claim checkable rather than assumed: it reads the export's lines through `curl -N` piped into a loop that timestamps each line as it arrives, and with `limit=5` at a 200ms tick, asserts the spread between first and last timestamp is at least 0.5 seconds — close to the ideal 800ms, far above the near-zero spread a buffered implementation would produce. A response with the right status code, `Content-Type`, and even byte-for-byte the right body can still have been generated all at once and written in a single burst right before the connection closed; only a timing assertion on when each piece left the server distinguishes real incremental delivery from a buffered one wearing a streaming `Content-Type`.

### The NDJSON double-encoding pitfall

Declaring `@Produces("application/x-ndjson")` on a method returning `Multi<String>` is not, on its own, enough to get raw NDJSON on the wire. Quarkus REST's Jackson integration (`quarkus-rest-jackson`) registers a `MessageBodyWriter` broadly enough that it wins the writer lookup for `String` even on a media type it has no special knowledge of, and when it wins, it does what Jackson always does with a `String`: serializes it as a *quoted JSON string*, escaping the line's own embedded newline to `\n`. Each NDJSON record (meant to be independently parseable JSON, one object per line) ends up wrapped inside an outer JSON string, which breaks the premise of newline-delimited JSON and fails schema validation outright.

`NdjsonMessageBodyWriter.java` fixes this with a narrowly-scoped `@Provider`:

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

Because this writer is registered for exactly `application/x-ndjson` and `String`, it wins that lookup, and `writeTo` does the only thing an NDJSON writer should do with an already-serialized line: write its bytes to the wire, untouched. `exportEvents`'s `toJsonLine` helper already calls `objectMapper.writeValueAsString(event)` and appends the trailing `\n` itself, so by the time a `String` reaches this writer it's a complete JSON object plus a newline — raw bytes are exactly right. The gotcha generalizes beyond NDJSON: any reactive endpoint producing pre-serialized text on a media type a general-purpose writer might also claim needs a dedicated `@Provider` scoped to that combination, or the generic writer reinterprets bytes already in final form.

## Three more reasons Quarkus shows up in REST services

The build-time model and reactive streaming are Quarkus REST's own contribution to a service's REST layer; the rest of what makes Quarkus a recurring choice for REST work lives in the surrounding ecosystem, and three pieces come up often enough to be worth naming even without a worked example in this chapter.

**LangChain4j for LLM-backed SSE.** A REST service that fronts a large language model (a chat endpoint, a streaming completion, a RAG query that narrates its own retrieval steps) needs to forward token-by-token output as it's generated, not buffer the whole answer into one JSON blob once the model finishes. LangChain4j, the Java LLM-orchestration library with a first-class Quarkus extension, exposes a streaming chat model API that emits tokens as they arrive from the underlying provider, and that maps naturally onto the same `Multi`-based machinery this chapter's NDJSON endpoint already uses — a resource method returning `Multi<String>` over `text/event-stream` instead of `application/x-ndjson`, one SSE event per emitted token instead of one NDJSON line. A team adding an LLM-backed feature to an otherwise ordinary Quarkus REST service reaches for this combination because the reactive type that already streams NDJSON exports also streams model tokens, with the same backpressure and non-blocking guarantees, rather than bolting on a second streaming mechanism just for AI features.

**Camel Quarkus and CXF for integration and SOAP bridging.** Not every system a REST API talks to speaks REST, JSON, or HTTP natively — a partner's legacy SOAP endpoint, a mainframe feed over a message queue, a file drop that has to be picked up, transformed, and forwarded. Camel Quarkus brings Apache Camel's enterprise integration patterns (routes, transformations, protocol bridges) into a Quarkus application as build-time-optimized components, letting a REST resource kick off a Camel route that handles that plumbing without hand-rolling it inline. CXF Quarkus answers the SOAP case directly: when "modernize this API" means "put a REST facade in front of a SOAP backend that isn't going away this quarter," CXF's Quarkus support exposes or consumes SOAP/WSDL contracts from inside the same deployable serving the team's real REST surface.

**JobRunr for background jobs.** A REST endpoint that triggers slow work (a report generation, a batch export, a notification fan-out) shouldn't hold a request open for the duration of that work; the idiomatic answer, going back to Chapter 10's async long-running operations, is to accept the request, return `202 Accepted` with a status URL, and do the work out of band. JobRunr is a lightweight background-job library with a Quarkus extension that persists job state to the application's own database and handles retry, scheduling, and recurring jobs without a separate broker — a proportionate choice for "do this later, reliably" short of a full event-streaming platform.

None of these three needs a worked example here: they're why a team already building REST on Quarkus tends to stay on Quarkus as a service's responsibilities grow past plain request/response, rather than reaching for a second framework per shape of work.

{% include excalidraw.html file="22-quarkus-rest-in-depth" alt="Quarkus REST's build-time bytecode-generation path resolving @RestHeader and @RestQuery bindings ahead of request time, alongside the reactive NDJSON export's tick-driven Multi pipeline delivering one line at a time through a dedicated MessageBodyWriter to the client." caption="Figure 22.1 — Build-time parameter binding and tick-driven reactive streaming in Quarkus REST." %}

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Apply the Chapter 2 axes to whether Quarkus's build-time model and reactive streaming are worth reaching for over a simpler, more conventional framework. Evolution pressure and deployment footprint drive the build-time half: a service that restarts rarely, runs as one long-lived process on a fixed-size VM, and is never measured on cold-start time gets little practical benefit from eliminating reflective dispatch, since that cost is paid once at boot and amortized over a long uptime — a classic JAX-RS container is a reasonable choice there. The calculus flips once the deployment target is serverless, autoscaled, or a native-image binary: a function scaling from zero, pods scaling with traffic, or anything compiled with GraalVM pays startup cost on every cold instance, which is exactly what Quarkus's build-time metadata erases. Reactive streaming is worth reaching for when a response is large, slow to assemble, or open-ended (a bulk export, a file download, a token stream), because that's where thread-per-request's scaling ceiling and a buffered response's memory footprint bite; for endpoints returning one small, quickly-computed JSON object, `Multi` adds pipeline complexity with no corresponding win, and a synchronous method is the better fit. Skip the reactive model when the real constraint is familiarity with blocking code and load never nears the concurrency where thread-per-request runs out of threads — these strengths show up under specific pressures, not as a blanket argument for Quarkus over every alternative.</p></div>
