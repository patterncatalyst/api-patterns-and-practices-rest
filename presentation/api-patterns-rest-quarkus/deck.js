// deck.js: "API Patterns & Practices: REST · Quarkus Implementation".
// How the 100-level patterns are built in Quarkus REST (RESTEasy Reactive),
// shipping/cargo domain, against one OpenAPI contract. Real code from
// examples/*/quarkus/** and _docs/22-quarkus-rest-in-depth.md.
//
// Build:  export NODE_PATH="$(cd ../_shared/node_modules && pwd)" && node deck.js

"use strict";

const path = require("path");
const SHARED = path.resolve(__dirname, "../_shared");
process.env.DECK_ASSETS = `${SHARED}/assets`;
process.env.DECK_PNG = `${SHARED}/png`;

const H = require(`${SHARED}/deck-helpers.js`);
const {
  COLOR, FONT, W, ASSETS,
  newDeck, addFooter, addContentTitle, addBullets, addTwoColBullets,
  addStatusTable, addCaption, addCodeSlide, addDiagramSlide,
  addSectionDivider, addNotes,
} = H;

const OUT = path.resolve(__dirname, "api-patterns-rest-quarkus-r1.1.pptx");
const REV = "r1.1";

const pres = newDeck();
pres.title = "API Patterns & Practices: REST · Quarkus Implementation";
let pageNum = 0;

function S() { const s = pres.addSlide(); pageNum += 1; addFooter(s, pageNum); return s; }
function divider(code, title, subtitle, notes) {
  const s = pres.addSlide(); pageNum += 1; addSectionDivider(s, code, title, subtitle); addNotes(s, notes);
}

/* ======================= 1 · COVER ======================= */
{
  const s = pres.addSlide();
  pageNum += 1;
  s.background = { color: COLOR.white };
  try { s.addImage({ path: `${ASSETS}/cover-panel.png`, x: 0, y: 0, w: W, h: 7.5 }); } catch (e) {}
  s.addText("API PATTERNS & PRACTICES · REST", { x: 6.00, y: 1.82, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 14, bold: true, color: COLOR.red, charSpacing: 6, align: "left", valign: "middle" });
  s.addText([{ text: "The Quarkus", options: { breakLine: true } }, { text: "implementation." }], {
    x: 5.95, y: 2.28, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("Every REST pattern from the 100-level deck, built in Quarkus REST: build-time binding, Bean Validation, reactive streaming, and CloudEvents over Kafka, in the shipping & cargo domain, against one OpenAPI contract.", {
    x: 6.00, y: 4.30, w: 6.80, h: 1.30, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText([
    { text: "Robert Sedor", options: { bold: true, color: COLOR.ink, breakLine: true } },
    { text: "Principal Chief Architect, Application Development", options: { color: COLOR.caption } },
  ], { x: 6.00, y: 5.75, w: 6.70, h: 0.80, fontFace: FONT.body, fontSize: 15, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 6.40, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "Welcome to the Quarkus implementation deck. This is deck two of three in the API Patterns & Practices: REST series. The 100-level deck established the patterns and the reasoning, stack-agnostic; this deck shows how each of those patterns is actually built in Quarkus REST, the framework formerly called RESTEasy Reactive, against the same single OpenAPI contract and the same shipping and cargo domain. Everything you'll see is real code from the site's runnable examples under examples/*/quarkus, and from the Chapter 22 deep-dive. The through-line is Quarkus's defining choice: resolve as much as possible at build time rather than at request time, and lean on the reactive runtime for streaming and messaging. I'm Robert Sedor. By the end you'll have seen the resource classes, the records-as-DTOs with Bean Validation, the Problem-details exception mappers, keyset pagination, the async operation, HATEOAS link building, media-type versioning, reactive NDJSON streaming with its own message-body writer, and the CloudEvents-over-Kafka publisher, all the way to @QuarkusTest and native images.");
}

/* ======================= 2 · AGENDA ======================= */
{
  const s = S();
  addContentTitle(s, "ROADMAP", "Agenda");
  addTwoColBullets(s,
    [
      "Build-time binding vs runtime reflection",
      "Contract-first & the Booking resource",
      "Records as DTOs + Bean Validation",
      "Problem Details exception mappers",
      "Content negotiation & partial updates",
      "Keyset pagination",
    ],
    [
      "Async operations (202 → poll → 303)",
      "HATEOAS links from the lifecycle FSM",
      "Versioning & soft deletion",
      "Reactive NDJSON streaming + the writer",
      "CloudEvents over Kafka (SmallRye)",
      "Testing, running it · ecosystem · Q&A",
    ],
    { fontSize: 15 });
  addNotes(s, "The arc follows the same pattern order as the 100-level deck, so the two map one to one, but every stop is Quarkus code. We open with the build-time binding model that defines Quarkus REST, then the contract-first resource class and the records-plus-Bean-Validation approach to DTOs, and the exception mappers that turn every failure into RFC 9457 Problem Details. The middle covers HTTP semantics in Quarkus: content negotiation and merge-patch, plus keyset pagination with @RestQuery. Then the harder patterns: the asynchronous operation across two resource classes, HATEOAS links driven by the lifecycle state machine, media-type versioning, and soft deletion. We finish with the reactive story: Multi-based NDJSON streaming and the dedicated message-body writer that keeps it honest, then the CloudEvents-over-Kafka publisher built on SmallRye Reactive Messaging, and then testing with @QuarkusTest, running across the three tiers, and the surrounding ecosystem. A short appendix carries extra code variants. Speaker notes on every slide, appendix included.");
}

/* ======================= 3 · SERIES MAP ======================= */
{
  const s = S();
  addContentTitle(s, "SERIES MAP", "Where this deck sits");
  addBullets(s, [
    "Deck 1 (100-level) is the patterns and the why, stack-agnostic: start there for the reasoning.",
    "This deck is the Quarkus HOW: the same shipping/cargo contract realized in Quarkus REST, with real code.",
    "A sibling deck does the identical arc in Python/FastAPI: both are validated against the one OpenAPI contract in CI.",
    "Code shown here is lifted from examples/*/quarkus/** and the Chapter 22 deep-dive; versions are pinned (Quarkus on JDK 25).",
  ], { fontSize: 17 });
  addCaption(s, "Same patterns, same domain, same contract: this deck is the Quarkus realization of them.");
  addNotes(s, "A quick orientation so the three decks compose rather than repeat. Deck one, the 100-level, is where the patterns and the reasoning live: if a design question comes up today about why a pattern is shaped the way it is, that's the deck that answers it, and it does so without committing to a language. This deck is the Quarkus how: it takes each of those patterns and shows the actual Quarkus code that implements it, against the same shipping and cargo contract and domain. There's a sibling deck that walks the identical arc in Python and FastAPI, and the point of having both is that the two implementations are validated against the one OpenAPI contract in CI, so they stay interchangeable; a client can't tell which stack answered. Everything I show is lifted from the runnable examples under examples slash star slash quarkus and from the Chapter 22 deep-dive, and the versions are pinned, Quarkus on JDK 25, so what you see is what runs.");
}

/* ======================= DIVIDER 01 ======================= */
divider("01", "Build-time Quarkus REST",
  "Why Quarkus resolves parameter bindings at build time, and what that buys you.",
  "Quarkus REST makes one defining choice: figure out how a request maps onto a Java method once, at build time, instead of by reflection on every request. That choice is invisible on the wire but it's why Quarkus starts in milliseconds, runs lean, and compiles to a native binary. This section grounds it in two real endpoints.");

/* --- build-time diagram --- */
{
  const s = S();
  addDiagramSlide(s, "BUILD-TIME", "Build-time binding, not runtime reflection",
    "r22-quarkus-buildtime",
    "A build step generates the parameter-binding bytecode once; the running server does no reflection on the request path.",
    { x: 1.10, y: 1.72, w: 11.13, h: 4.60 });
  addNotes(s, "Classic JAX-RS, RESTEasy Classic, Jersey, most of what 'a REST framework in Java' meant for a decade, resolves a method's parameters the same way on every request: it walks the method's Parameter array via java.lang.reflect, reads the @HeaderParam or @QueryParam annotation, pulls the value, and coerces it, every time, for every annotated method. It also discovers which classes answer which @Path by scanning the classpath at startup. Quarkus REST does the equivalent work once, ahead of time, as part of the build. A build-time extension reads the same annotations you write: @Path, @GET, @RestHeader, @RestQuery, and generates actual bytecode: a concrete class that calls request.getHeader directly and invokes your method with the value already in hand. No Method.invoke at runtime, no annotation lookup on the request path. The payoff shows up in three places you can observe without a benchmark harness: startup time drops because there's no classpath scan and no reflective metadata to build before the first request; memory and allocation improve because reflective dispatch isn't free; and native-image compilation becomes tractable, because GraalVM has to know every reflectively-reachable method ahead of time, and a framework that already resolved its bindings at build time has almost nothing left to reflect on. None of this changes behaviour; all of it changes cost.");
}

/* --- @RestHeader / @RestQuery code --- */
{
  const s = S();
  addCodeSlide(s, "BUILD-TIME", "@RestHeader / @RestQuery / @RestPath", "java · Quarkus",
    [
      "// Quarkus REST's own binding annotations — bound at build time,",
      "// drop-in replacements for classic JAX-RS @HeaderParam/@QueryParam.",
      "@GET @Path(\"/tenant\") @Produces(MediaType.APPLICATION_JSON)",
      "public Map<String,Object> tenantInfo(@RestHeader(\"X-Tenant\") String tenant) {",
      "    boolean defaulted = tenant == null;      // absent header -> null",
      "    return Map.of(\"tenant\", defaulted ? DEFAULT_TENANT : tenant,",
      "                  \"defaulted\", defaulted);",
      "}",
      "",
      "@GET @Path(\"/bookings/{id}\") @Produces(MediaType.APPLICATION_JSON)",
      "public Response getBooking(@RestPath String id) { ... }",
    ],
    "Same contract as @HeaderParam/@PathParam: the binding just disappears into generated code before the first request.",
    { fontSize: 12 });
  addNotes(s, "Here's the smallest demonstration, from the Chapter 22 example. org.jboss.resteasy.reactive.RestHeader is Quarkus REST's own annotation, a drop-in replacement for classic JAX-RS's @HeaderParam: same job, bound at build time instead of resolved by reflection per request. On an absent X-Tenant header it injects null, exactly as @HeaderParam would, which is why the fallback to the default tenant is written explicitly in the method body rather than delegated to @DefaultValue: @DefaultValue can only supply a fixed string literal baked in at the annotation site, which can't express 'fall back to a value computed or looked up elsewhere'. Send the header and the response echoes it with defaulted false; omit it and it reports the server default with defaulted true, a request-scoped observable that makes the binding checkable. @RestPath and @RestQuery are the same idea for path segments and query strings. The HTTP contract is unremarkable: a header read, a default, a JSON body. That's the point: you write one annotation on one parameter, and the framework makes it disappear into generated code before the first request lands.");
}

/* --- payoff + decision --- */
{
  const s = S();
  addContentTitle(s, "BUILD-TIME", "What the build-time model buys, and when");
  addTwoColBullets(s,
    [
      { text: "The payoff", options: { bold: true, bullet: false } },
      "Startup: no classpath scan, no reflective metadata at boot.",
      "Memory: no Method.invoke bookkeeping on the hot path.",
      "Native: little left for GraalVM to reflect on.",
    ],
    [
      { text: "When it matters most", options: { bold: true, bullet: false } },
      "Serverless / scale-from-zero: cold start is paid every time.",
      "Autoscaled pods: start time gates how fast you absorb load.",
      "Native binaries: the build-time model makes them tractable.",
    ],
    { fontSize: 15 });
  addCaption(s, "A long-lived process on a fixed VM amortizes boot cost; there, classic JAX-RS is fine. The win scales with how often you start.");
  addNotes(s, "The build-time model isn't a blanket 'Quarkus is faster' claim: it's a specific win under specific pressure, so it's worth being honest about where it pays off. The payoff, on the left, is the three observable effects: startup drops because there's no scan or reflective metadata to build at boot; memory and allocation improve because reflective dispatch costs bookkeeping the JIT can't fully optimize away; and native-image friendliness is close to existential, because GraalVM needs to know every reflectively-reachable method ahead of time and the build-time model leaves almost nothing to reflect on. On the right is the honest framing from the Chapter 22 Decision callout: these wins scale with how often you start a process. A service that restarts rarely and runs as one long-lived process on a fixed-size VM amortizes its boot cost over a long uptime and gets little practical benefit; a classic JAX-RS container is a perfectly reasonable choice there. The calculus flips the moment the target is serverless, autoscaled, or a native binary: a function scaling from zero, pods scaling with traffic, or anything compiled with GraalVM pays startup cost on every cold instance, and that's exactly what the build-time metadata erases. Match the tool to the pressure.");
}

/* ======================= DIVIDER 02 ======================= */
divider("02", "Contract-first & the resource model",
  "The Booking resource, records as DTOs, Bean Validation, and Problem Details.",
  "With the runtime model understood, the resource layer: one @Path class implements the booking surface from the OpenAPI contract, DTOs are Java records with Bean Validation constraints that mirror the shared schema, and every error, the ones we raise and the ones the runtime raises, comes back as application/problem+json.");

/* --- BookingResource CRUD --- */
{
  const s = S();
  addCodeSlide(s, "RESOURCES", "The Booking resource: contract-first CRUD", "java · Quarkus",
    [
      "@Path(\"/bookings\")",
      "public class BookingResource {",
      "  @Inject BookingStore store;",
      "",
      "  @POST @Consumes(APPLICATION_JSON) @Produces(APPLICATION_JSON)",
      "  public Response createBooking(@Valid BookingRequest request) {",
      "    Booking booking = new Booking(\"bkg_\" + Ulid.generate(),",
      "        BookingStatus.PENDING, request.origin(), request.destination(),",
      "        toCargoItems(request.cargo()), QuoteCalculator.compute(...),",
      "        request.requestedPickup(), nowUtc(), null);",
      "    store.put(booking);",
      "    return Response.status(CREATED)",
      "        .header(\"Location\", \"/bookings/\" + booking.id())  // literal, relative",
      "        .entity(booking).build();",
      "  }",
      "}",
    ],
    "One @Path class maps to the contract's booking operations; the server mints the id and returns 201 + a relative Location.",
    { fontSize: 11 });
  addNotes(s, "This is the contract-first anchor: one @Path class, BookingResource, implementing the booking operations from shipping-api.yaml, backed by an injected store. createBooking takes a @Valid BookingRequest (we'll come back to that @Valid in two slides; it's what triggers Bean Validation), mints the server-assigned id with a bkg_ prefix and a ULID body, sets the initial status to PENDING, computes the quote, persists, and returns. Two details worth calling out. First, the server mints the URI, not the client, which is the REST rule for POST-to-a-collection. Second, look at how the Location header is set: it's a literal string, '/bookings/' plus the id, not Response.created(URI). That's intentional: per the JAX-RS spec, ResponseBuilder.location resolves a relative URI into an absolute one against the request base URI, which would make Quarkus's Location header diverge from the Python stack's relative /bookings/{id}. Setting the header directly keeps the two stacks byte-for-byte identical, which is exactly the kind of thing the shared contract tests check. Every response body in this class is schema-validated against the shared JSON Schema in CI; this class is the thing that has to stay honest.");
}

/* --- records + Bean Validation --- */
{
  const s = S();
  addCodeSlide(s, "RESOURCES", "Records as DTOs + Bean Validation", "java · Quarkus",
    [
      "// DTOs are records; constraints mirror the shared JSON Schema",
      "public record BookingRequest(",
      "    @NotNull @Valid Location origin,",
      "    @NotNull @Valid Location destination,",
      "    @NotEmpty @Valid List<CargoRequest> cargo,   // >= 1 cargo item",
      "    String requestedPickup) {}",
      "",
      "public record Location(",
      "    @NotNull @Pattern(regexp = \"^[A-Z]{2}[A-Z0-9]{3}$\") String unLocode,",
      "    String name, @Pattern(regexp = \"^[A-Z]{2}$\") String country) {}",
      "",
      "public record Dimensions(@Positive double weightKg,",
      "                         @Positive Double volumeM3) {}",
    ],
    "@Valid cascades into nested records; a missing weightKg deserializes to 0, which @Positive rejects, same as the schema.",
    { fontSize: 12 });
  addNotes(s, "DTOs here are Java records, not classes: concise, immutable, and a natural fit for request and response payloads. The constraints are Jakarta Bean Validation annotations, and they're chosen to mirror the shared JSON Schema exactly so both stacks reject the same malformed input. BookingRequest requires origin and destination with @NotNull, requires at least one cargo item with @NotEmpty, and, importantly, carries @Valid on the nested types. @Valid cascades validation into each nested Location and CargoRequest, so a malformed unLocode deep inside the request is caught, not just a missing top-level field. Location's unLocode has a @Pattern matching the UN/LOCODE shape; country has its own pattern. Dimensions uses @Positive on weightKg, and there's a subtle correctness point in the comment: weightKg is a primitive double, so a missing value deserializes to 0, and @Positive rejects 0 the same as an explicit negative, which matches the schema's exclusiveMinimum of zero. The Quarkus and Python constraints are kept parallel; the Python side expresses the same rules with Pydantic Field declarations. The upshot: validation is declarative, lives on the DTO, and when it fails it throws a ConstraintViolationException, which brings us to the mappers.");
}

/* --- Problem mappers --- */
{
  const s = S();
  addCodeSlide(s, "RESOURCES", "Every failure → application/problem+json", "java · Quarkus",
    [
      "// Bean Validation failures -> 400 Problem (RFC 9457)",
      "@Provider",
      "public static class ConstraintViolationExceptionMapper",
      "        implements ExceptionMapper<ConstraintViolationException> {",
      "  public Response toResponse(ConstraintViolationException ex) {",
      "    String detail = ex.getConstraintViolations().stream()",
      "        .map(v -> v.getPropertyPath() + \": \" + v.getMessage())",
      "        .sorted().collect(Collectors.joining(\"; \"));",
      "    return Response.status(400).type(\"application/problem+json\")",
      "        .entity(new Problem(\"Validation failed\", 400, detail)).build();",
      "  }",
      "}",
      "// Also mapped: NotSupportedException -> 415, NotAcceptableException -> 406,",
      "// Throwable -> 500 — so runtime-raised errors are Problem too.",
    ],
    "The runtime rejects a wrong Content-Type before your method runs; mappers make those errors Problem-shaped as well.",
    { fontSize: 11 });
  addNotes(s, "This is what makes the error contract honest. When Bean Validation fails on that @Valid parameter, the runtime throws a ConstraintViolationException before your method body ever runs. This @Provider ExceptionMapper catches it, flattens the violations into a sorted, readable detail string (property path plus message) and returns a 400 with Content-Type application/problem+json and an RFC 9457 Problem body. The sorting matters for determinism: the same bad request produces the same detail string every time, which the contract tests rely on. The reason there's a whole family of these mappers, not just one, is that the JAX-RS runtime raises some errors itself, before your resource method is reached. A PATCH sent with the wrong Content-Type never reaches patchBooking: RESTEasy Reactive rejects it with a NotSupportedException first, so there's a mapper that turns that into a 415 Problem. Likewise NotAcceptableException becomes a 406 Problem, and a last-resort Throwable mapper turns any unexpected bug into a 500 Problem instead of leaking a stack trace. The principle: every error a client can possibly see, whether we raised it ourselves or the framework raised it for us, comes back in the same application/problem+json shape, so a client only has to understand one error format.");
}

/* ======================= DIVIDER 03 ======================= */
divider("03", "HTTP semantics in Quarkus",
  "Content negotiation, merge-patch, and status codes done to the letter.",
  "The patterns from the semantics section, in Quarkus code: a PATCH scoped to the merge-patch media type, status codes chosen precisely, and the Location header shaped to match the contract. Small code, big correctness.");

/* --- content negotiation + merge patch --- */
{
  const s = S();
  addCodeSlide(s, "SEMANTICS", "Merge-patch, scoped by media type", "java · Quarkus",
    [
      "@PATCH @Path(\"/{id}\")",
      "@Consumes(\"application/merge-patch+json\")   // ONLY this media type",
      "@Produces(MediaType.APPLICATION_JSON)",
      "public Response patchBooking(@RestPath String id, JsonNode mergePatchDoc) {",
      "  Booking existing = store.get(id);",
      "  if (existing == null) return notFound(id);",
      "  JsonNode target = mapper.valueToTree(existing);",
      "  JsonNode merged = applyMergePatch(target, mergePatchDoc);  // RFC 7396",
      "  Booking patched = mapper.treeToValue(merged, Booking.class);",
      "  // id/createdAt are server-assigned (readOnly) — never overwritten",
      "  store.put(result); return Response.ok(result).build();",
      "}",
    ],
    "A request with any other Content-Type never reaches this method: the runtime returns 415 (mapped to Problem).",
    { fontSize: 11 });
  addNotes(s, "Partial updates, Quarkus-side. The @Consumes annotation is scoped to exactly application/merge-patch+json, and that scoping is doing real work: a PATCH with any other Content-Type never dispatches to this method at all; RESTEasy Reactive rejects it with the NotSupportedException we just mapped to a 415 Problem. So the media-type contract from the 100-level deck is enforced by the framework, not by a hand-written check. The body comes in as a Jackson JsonNode rather than a typed DTO, because a merge patch is a sparse document, only the fields being changed, so you can't deserialize it straight into a Booking. applyMergePatch implements RFC 7396 recursively: for each field in the patch, a null value means remove, anything else is set or merged. Then the merged tree is read back into a Booking. The critical safety line is the comment: id and createdAt are server-assigned and readOnly in the schema, so after merging we explicitly restore the existing id and createdAt: a client can't overwrite them no matter what it sends in the patch. JSON Patch, RFC 6902, would be a second @Consumes on application/json-patch+json dispatching to a different handler; the site ships merge-patch as the primary and this is the shape.");
}

/* --- status codes --- */
{
  const s = S();
  addContentTitle(s, "SEMANTICS", "Status codes, chosen precisely");
  addStatusTable(s, [
    { code: "201", name: "Response.status(CREATED)", purpose: "createBooking, with a literal relative Location header to the new booking." },
    { code: "202", name: "Response.status(ACCEPTED)", purpose: "requestConfirmation: Location points at the Operation to poll." },
    { code: "204", name: "Response.noContent()", purpose: "deleteBooking (soft-delete) and operation cancel: success, empty body." },
    { code: "303", name: "Response.status(SEE_OTHER)", purpose: "OperationResource: once SUCCEEDED, Location to the confirmed booking." },
    { code: "4xx", name: "Problem mappers", purpose: "404/409/415/406/400 all return application/problem+json via mappers." },
  ], { colW: [0.95, 3.95, 7.19], rowH: 0.62 });
  addCaption(s, "Quarkus's Response builder names each status; the Location header is set literally so both stacks stay byte-identical.");
  addNotes(s, "Quarkus's Response builder lets you name each status code explicitly, and the examples do, because the status code is the first thing every client and proxy reads. createBooking uses Response.status(CREATED) with the literal relative Location header we discussed. requestConfirmation, the async pattern's opening move, uses ACCEPTED (202) with Location pointing at the Operation. deleteBooking and operation cancel use Response.noContent, a 204 with an empty body, which is exactly right for a soft-delete that succeeded. OperationResource returns SEE_OTHER (303) once the operation has SUCCEEDED, with Location pointing at the now-confirmed booking. And the whole 4xx family (404 not found, 409 conflict on an illegal state transition, 415 and 406 from content negotiation, 400 from validation) all flow through the Problem mappers, so they're application/problem+json. The recurring discipline, in the caption: the Location header is always set as a literal relative path rather than through the builder's location method, specifically so the Quarkus and Python responses are byte-for-byte identical and the shared contract tests pass against both.");
}

/* ======================= DIVIDER 04 ======================= */
divider("04", "Collections at scale",
  "Keyset pagination with @RestQuery, capped and cursor-driven.",
  "Reading the booking collection safely, in Quarkus: query parameters bound by @RestQuery, a hard cap on page size, and an opaque keyset cursor as the default strategy, with offset and seek supported for comparison.");

/* --- pagination diagram --- */
{
  const s = S();
  addDiagramSlide(s, "COLLECTIONS", "Pagination strategies",
    "r08-pagination",
    "Quarkus defaults to keyset-with-cursor; offset and seek are supported so the trade-offs are visible side by side.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "Same strategy spectrum as the 100-level deck (offset, keyset, seek) and the Quarkus example implements all three on one listBookings endpoint so you can see the trade-offs in running code rather than on a slide. Offset is simple but drifts and slows at depth; keyset pages on the last-seen sort key, consistent and fast but coupled to the sort; seek adds an opaque cursor that decouples paging from the filter. The example makes keyset-with-cursor the default and stable strategy, which matches the shared contract. The next slide is the actual handler. The one invariant across all three strategies, and the thing to really take away: the page limit is clamped in code, never honoured unbounded, because a client that asks for a million rows is a denial-of-service vector whether it means to be or not.");
}

/* --- keyset pagination code --- */
{
  const s = S();
  addCodeSlide(s, "COLLECTIONS", "Keyset pagination with @RestQuery", "java · Quarkus",
    [
      "@GET @Produces(MediaType.APPLICATION_JSON)",
      "public Response listBookings(",
      "    @RestQuery Integer limit,          // page size, clamped to [1, 100]",
      "    @RestQuery Integer offset,         // offset pagination (comparison)",
      "    @RestQuery(\"after_id\") String afterId,  // seek pagination",
      "    @RestQuery String cursor,          // keyset — the DEFAULT strategy",
      "    @RestQuery String fields) {        // sparse fieldset projection",
      "  int effectiveLimit = clampLimit(limit);        // DoS guard: max 100",
      "  PageResult result = computePage(visible, offset, afterId, cursor, effectiveLimit);",
      "  PageMeta page = new PageMeta(effectiveLimit, result.items().size(),",
      "                               result.nextCursor());  // null on last page",
      "  return Response.ok(new BookingCollection(result.items(), page)).build();",
      "}",
    ],
    "limit is clamped to the schema's maximum (100); the opaque cursor (base64 of the last-seen id) decouples paging from filters.",
    { fontSize: 11 });
  addNotes(s, "Here's the real handler. Five query parameters, all bound by @RestQuery; note after_id uses the explicit name form because the Java identifier can't contain the underscore style the API uses. The parameters let one endpoint demonstrate all three strategies: offset for comparison, after_id for seek, cursor for keyset (which is the default when offset and after_id are absent), and fields for sparse projection. The first thing the method does is clampLimit: the limit is forced into the range 1 to 100, matching the shared schema's maximum. That clamp is the DoS guard: a client sending limit equals one million gets 100, not a million, because an unbounded limit lets a client force the server to materialize and serialize an arbitrarily large response. computePage dispatches to the right strategy and returns the page plus the next cursor, which is an opaque base64 encoding of the last-seen id; it's opaque so the client treats it as a token rather than something to parse, which is what decouples paging from the filter and sort logic. The response is a BookingCollection object carrying items and a PageMeta with the applied limit, the count, and nextCursor, which is null on the last page: the unambiguous end-of-collection signal.");
}

/* ======================= DIVIDER 05 ======================= */
divider("05", "Asynchronous operations",
  "The 202 → poll → 303 protocol across two resource classes.",
  "Confirmation can't finish in one request, so it's modelled as the asynchronous operation pattern: BookingResource accepts the work with 202 and an Operation to poll, and OperationResource serves the poll and the 303 redirect to the result.");

/* --- async diagram --- */
{
  const s = S();
  addDiagramSlide(s, "ASYNC", "202 → poll → 303",
    "r10-async-flow",
    "BookingResource returns 202 + the Operation URI; OperationResource polls and, once SUCCEEDED, 303s to the booking.",
    { x: 1.60, y: 1.70, w: 10.13, h: 4.55 });
  addNotes(s, "The flow from the 100-level deck, now split across the two Quarkus resource classes that implement it. POST to the confirmation sub-resource on BookingResource accepts the work and returns 202 with a Location header pointing at a new Operation resource; it does not block on the routing and capacity checks. The client then polls that Operation on OperationResource; while it's PENDING or RUNNING the poll returns 200 with the Operation body, and once it's SUCCEEDED the same GET returns 303 See Other with Location pointing at the confirmed booking. The Operation is a first-class, durable resource with its own id and status machine, so a client that crashed can come back and ask whether its confirmation finished simply by GETting the Operation URI it saved. The next two slides are the two halves in code.");
}

/* --- 202 half --- */
{
  const s = S();
  addCodeSlide(s, "ASYNC", "The 202 half: accept, hand back an Operation", "java · Quarkus",
    [
      "@POST @Path(\"/{id}/confirmation\") @Produces(MediaType.APPLICATION_JSON)",
      "public Response requestConfirmation(@RestPath String id) {",
      "  Booking booking = store.get(id);",
      "  if (booking == null) return notFound(id);",
      "  if (booking.status() != BookingStatus.PENDING)",
      "    return problem(409, \"Booking not confirmable\",",
      "                   \"Booking \" + id + \" is not PENDING\");   // illegal transition",
      "  String opId = \"op_\" + Ulid.generate();",
      "  operationStore.startConfirmation(opId, id);     // runs off the request thread",
      "  return Response.status(Response.Status.ACCEPTED)",
      "      .header(\"Location\", \"/operations/\" + opId)",
      "      .entity(operationStore.get(opId)).build();",
      "}",
    ],
    "A confirm on a non-PENDING booking is a 409 Conflict: the state machine rejects an illegal transition.",
    { fontSize: 11 });
  addNotes(s, "The accept half, on BookingResource. It guards twice: a missing booking is a 404, and (this is the state-machine check) confirming a booking that isn't PENDING is a 409 Conflict, because that's an illegal transition, not a malformed request. That distinction between 409 and 400 matters to clients. If both guards pass, it mints an Operation id, kicks off the confirmation work through the operation store so it runs off the request thread rather than blocking the response, and returns 202 Accepted with Location pointing at the new Operation and the Operation body as the entity. Same literal-relative Location discipline as everywhere else. The actual confirmation work (the routing and capacity checks) happens asynchronously; in the multi-protocol example that same transition is also what publishes the CloudEvents message we'll see later. The client's job now is to poll the Operation, which is the other resource class.");
}

/* --- poll/303 half --- */
{
  const s = S();
  addCodeSlide(s, "ASYNC", "The poll half: 200 while running, 303 when done", "java · Quarkus",
    [
      "@Path(\"/operations\")",
      "public class OperationResource {",
      "  @GET @Path(\"/{id}\") @Produces(MediaType.APPLICATION_JSON)",
      "  public Response get(@RestPath String id) {",
      "    Operation op = store.get(id);",
      "    if (op == null) return notFound(id);",
      "    if (op.status() == OperationStatus.SUCCEEDED)",
      "      return Response.status(Response.Status.SEE_OTHER)   // 303",
      "          .header(\"Location\", op.resource()).build();    // -> the booking",
      "    return Response.ok(op).build();          // 200 while PENDING/RUNNING/FAILED",
      "  }",
      "  @DELETE @Path(\"/{id}\")   // cancel a still-running operation -> 204",
      "  public Response cancel(@RestPath String id) { store.cancel(id); ... }",
      "}",
    ],
    "The Operation carries status PENDING/RUNNING/SUCCEEDED/FAILED; DELETE cancels and is idempotent (204 either way).",
    { fontSize: 11 });
  addNotes(s, "The poll and cancel half, OperationResource. The GET is the heart of it: if the operation has SUCCEEDED, it returns 303 See Other with Location pointing at op.resource, the confirmed booking, so the client follows the redirect to the result. Any other status (PENDING, RUNNING, or FAILED) returns 200 with the Operation body, so the client reads status and keeps polling, or sees FAILED with its error. That's the whole 202-poll-303 contract in a dozen lines. The DELETE provides the cancel affordance the Operation advertised while running: it cancels a still-running operation and returns 204, and it's idempotent: cancelling an already-terminal operation is a no-op that still returns 204, exactly the way DELETE on a booking treats a repeat cancel. Notice there's no reflection, no magic: it's plain JAX-RS reading a status off a stored resource and choosing a response code, which is the point: the async pattern is a protocol you implement with ordinary HTTP, not a framework feature you switch on.");
}

/* ======================= DIVIDER 06 ======================= */
divider("06", "Lifecycle: HATEOAS, versioning, soft delete",
  "Links driven by the state machine, media-type versioning, and soft deletion.",
  "The evolution patterns in Quarkus: a link builder that emits exactly the transitions legal from a booking's current state, media-type versioning that projects one stored resource into an older representation, and a soft-delete that flips status rather than erasing the row.");

/* --- HATEOAS diagram --- */
{
  const s = S();
  addDiagramSlide(s, "LIFECYCLE", "HATEOAS: links are the state machine",
    "r12-hateoas-fsm",
    "A link builder emits self everywhere, confirm+cancel while PENDING, cancel while CONFIRMED, and nothing more once terminal.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "The booking lifecycle finite-state machine from the 100-level deck. In Quarkus it's implemented by a single small builder that maps a booking's current status to the set of links it should carry, so the response literally is the state machine and the client follows links instead of hard-coding which transitions are legal. The next slide is that builder, and it's refreshingly small: the whole 'hypermedia as the engine of application state' idea comes down to a switch on status.");
}

/* --- HATEOAS code --- */
{
  const s = S();
  addCodeSlide(s, "LIFECYCLE", "Building _links from the lifecycle FSM", "java · Quarkus",
    [
      "static Map<String, Link> forBooking(String id, BookingStatus status) {",
      "  Map<String, Link> links = new LinkedHashMap<>();",
      "  links.put(\"self\", new Link(\"/bookings/\" + id, \"GET\", \"Get this booking\"));",
      "  switch (status) {",
      "    case PENDING -> {",
      "      links.put(\"confirm\", new Link(\"/bookings/\" + id + \"/confirmation\", \"POST\", ...));",
      "      links.put(\"cancel\",  new Link(\"/bookings/\" + id, \"DELETE\", ...));",
      "    }",
      "    case CONFIRMED -> links.put(\"cancel\", new Link(\"/bookings/\" + id, \"DELETE\", ...));",
      "    case IN_TRANSIT, DELIVERED, CANCELLED -> { /* self only — terminal */ }",
      "  }",
      "  return links;",
      "}",
    ],
    "The server owns the rules; a client renders whatever links arrive. Terminal states carry only self.",
    { fontSize: 11 });
  addNotes(s, "This is the entire HATEOAS implementation, and its smallness is the lesson. forBooking takes an id and the current status and returns the link map. Every state gets a self link: the canonical URI, which every resource should carry. A PENDING booking additionally gets confirm, a POST to the confirmation sub-resource, and cancel, a DELETE on the booking; those are its legal moves. A CONFIRMED booking gets only cancel. And the terminal states (IN_TRANSIT, DELIVERED, CANCELLED) get nothing but self, because there's no further client-driven transition from there. Each Link carries href, method, and a human title. The switch is exhaustive over the enum, so the compiler enforces that every state is handled: add a new status and it won't compile until you decide which links it offers, which is a nice safety property. The payoff is the same as in the concept deck: the rule 'you can only cancel while pending or confirmed' lives in exactly this one method, the server emits the links, and a well-built client renders whatever links arrive and stops offering a transition the moment its link disappears, with no client-side copy of the state machine and no redeploy when the rules change. The Python side mirrors this relation-for-relation.");
}

/* --- versioning --- */
{
  const s = S();
  addCodeSlide(s, "LIFECYCLE", "Media-type versioning: one resource, two shapes", "java · Quarkus",
    [
      "public static final String MEDIA_TYPE_V1 = \"application/vnd.shipping.v1+json\";",
      "public static final String MEDIA_TYPE_V2 = \"application/vnd.shipping.v2+json\";",
      "",
      "// The Accept header picks the representation of the ONE stored booking.",
      "public static boolean wantsV1(String acceptHeader) {",
      "  return acceptHeader != null && acceptHeader.contains(\"vnd.shipping.v1+json\");",
      "}",
      "",
      "// v1 is a LOSSY, read-only projection of the current v2 state:",
      "public static BookingV1 toV1(Booking b) {",
      "  String cargoDescription = b.cargo().stream()",
      "      .map(Cargo::description).collect(Collectors.joining(\"; \"));",
      "  return new BookingV1(b.id(), b.status(), b.origin(), b.destination(),",
      "                       cargoDescription, b.quote(), b.createdAt());",
      "}",
    ],
    "No v1 store and no v1 write path: v1 is a view derived from v2. Versioning is about the representation, not the resource.",
    { fontSize: 11 });
  addNotes(s, "Media-type versioning in Quarkus, and it teaches the deepest point about versioning: it's about the representation a client gets back, not about forking the underlying resource. There are two vendor media types, v1 and v2. wantsV1 reads the Accept header: anything that isn't explicitly the v1 vendor type, including a bare application/json, a wildcard, or the v2 type, means 'give me the current representation', so 'no opinion' and 'current version' behave identically. The crucial design choice is in toV1: there is no separate v1 store and no v1 write path. The one booking is always stored in the current v2 shape, and v1 is a read-only projection computed on the way out. And that projection is lossy by design: v1's single cargoDescription string is built by joining the v2 cargo items' descriptions, and v1 has no way to recover the individual items, weights, or hazardous flags from that string. That lossiness is the honest cost of carrying an old representation forward: it can only describe what its shape had room for. On the unversioned endpoint, wantsV1 drives the choice; the response echoes the negotiated vendor type in Content-Type and sets Vary: Accept so a shared cache treats the URL as having more than one representation. That Vary header is the caching subtlety from the concept deck, made real.");
}

/* --- soft delete --- */
{
  const s = S();
  addCodeSlide(s, "LIFECYCLE", "Soft deletion: flip status, don't erase", "java · Quarkus",
    [
      "@DELETE @Path(\"/{id}\")",
      "public Response deleteBooking(@RestPath String id) {",
      "  Booking existing = store.get(id);",
      "  if (existing == null) return notFound(id);",
      "  Booking cancelled = new Booking(existing.id(),",
      "      BookingStatus.CANCELLED,          // soft-delete = status flip",
      "      existing.origin(), existing.destination(), existing.cargo(),",
      "      existing.quote(), existing.requestedPickup(), existing.createdAt(), nowUtc());",
      "  store.put(cancelled);",
      "  return Response.noContent().build();   // 204; idempotent",
      "}",
      "// store.listVisible() excludes CANCELLED — soft-deleted rows stay out",
      "// of default queries; a separate, governed purge does hard-deletion (GDPR).",
    ],
    "DELETE is idempotent: cancelling an already-cancelled booking still returns 204, and the row persists for audit/undelete.",
    { fontSize: 11 });
  addNotes(s, "Soft deletion, the Quarkus way, and it's exactly what the concept deck described. DELETE doesn't remove the row: it constructs a new Booking with status flipped to CANCELLED, preserving everything else and stamping updatedAt, persists it, and returns 204 No Content. Because the data survives, you get recovery from accidental deletes, audit history, and referential integrity for free, and because flipping an already-cancelled booking to cancelled lands the same state, DELETE is idempotent, which the matrix requires. The two comments carry the rest of the pattern. First, the store's listVisible method excludes CANCELLED bookings, so soft-deleted rows stay out of default query results; a cancelled booking must not show up in a normal list, which is both a correctness and a potential compliance issue. Second, soft-delete is not the whole story for GDPR: there's a separate, governed purge path for lawful hard-deletion, distinct from everyday cancel and auditable, because the right to erasure can require that data actually be gone, not merely hidden. Soft-delete is the default; purge is the governed exception.");
}

/* ======================= DIVIDER 07 ======================= */
divider("07", "Reactive streaming & large payloads",
  "Multi-based NDJSON, the message-body writer that keeps it honest, and Range.",
  "Quarkus's reactive runtime is the idiomatic answer to a response that's large, slow, or open-ended. This section is NDJSON streamed from a Multi pipeline, the dedicated writer that stops Jackson from double-encoding it, and Range requests for large binaries.");

/* --- reactive NDJSON diagram --- */
{
  const s = S();
  addDiagramSlide(s, "STREAMING", "Reactive NDJSON: a Multi pipeline",
    "r22-reactive-ndjson",
    "A tick-driven Multi produces one line per tick over the event loop, never buffered, through a dedicated @Provider writer.",
    { x: 1.10, y: 1.72, w: 11.13, h: 4.55 });
  addNotes(s, "Reactive streaming is Quarkus's idiomatic answer to a REST response that's large, slow to assemble, or open-ended: a bulk export, a file download, an NDJSON or SSE feed. The mechanism is Mutiny's Multi, the reactive type for zero-or-more items delivered over time, driven by the event loop already running the HTTP connection. The pipeline on the diagram: a ticking source produces an item on an interval, select-first caps the count, each item is transformed into one NDJSON line, and a dedicated message-body writer flushes each line to the socket as it's produced. No dedicated thread is blocked for the stream's duration and no buffer accumulates the whole response in memory. The contrast is thread-per-request, where one OS thread sits blocked for the whole response and you scale by adding threads until you run out of them; an event loop processing many Multi subscriptions never blocks waiting for the next tick. And backpressure is built in: Multi only produces the next item when the downstream, here the socket's outbound buffer, is ready, so a fast producer can't pile up data the socket can't drain. The next two slides are the pipeline and the writer in code.");
}

/* --- Multi NDJSON code --- */
{
  const s = S();
  addCodeSlide(s, "STREAMING", "Streaming NDJSON from a Multi", "java · Quarkus",
    [
      "@GET @Path(\"/bookings/events/export\")",
      "@Produces(\"application/x-ndjson\")",
      "public Multi<String> exportEvents(@RestQuery(\"limit\") @DefaultValue(\"5\") int limit) {",
      "  int effectiveLimit = EventGenerator.clampLimit(limit);   // [1, 20] DoS guard",
      "  return Multi.createFrom().ticks()",
      "      .startingAfter(Duration.ofMillis(STREAM_INTERVAL_MILLIS))",
      "      .every(Duration.ofMillis(STREAM_INTERVAL_MILLIS))",
      "      .onItem().transform(Long::intValue)",
      "      .select().first(effectiveLimit)                      // cap the count",
      "      .onItem().transform(i -> toJsonLine(EventGenerator.eventFor(id, i)));",
      "}",
    ],
    "Each line is assembled only when its tick fires and flushed before the next, holding a connection ~limit × interval.",
    { fontSize: 11 });
  addNotes(s, "The real export endpoint from Chapter 22. It returns Multi of String, not a List it built up first, and each item is a complete NDJSON line assembled only when its tick fires. The pipeline: createFrom().ticks() is a periodic source firing every STREAM_INTERVAL_MILLIS; select().first(effectiveLimit) caps how many; and each tick is transformed into the next BookingEvent's JSON line. The event loop running the HTTP connection drives it: each tick produces one line, that line flushes to the socket before the next tick is due, nothing buffers. Note the clampLimit again: it enforces 1 to 20, and the comment in the source spells out why this DoS guard matters, not a nicety: an NDJSON export built on a ticking stream holds the connection open for roughly limit times the interval, so at a 200-millisecond tick an unclamped limit of a million would keep the connection alive for over fifty hours. A query parameter that drives resource consumption directly needs an upper bound enforced in code, independent of what the client claims to want. And the example's verify script proves the streaming happens incrementally by timestamping each line as it arrives and asserting the spread, because a buffered implementation could produce byte-identical output all at once; only the timing distinguishes incremental delivery.");
}

/* --- NDJSON writer code --- */
{
  const s = S();
  addCodeSlide(s, "STREAMING", "The writer that stops double-encoding", "java · Quarkus",
    [
      "@Provider",
      "@Produces(\"application/x-ndjson\")",
      "public class NdjsonMessageBodyWriter implements MessageBodyWriter<String> {",
      "  public boolean isWriteable(Class<?> t, Type g, Annotation[] a, MediaType m) {",
      "    return String.class.isAssignableFrom(t);",
      "  }",
      "  public void writeTo(String line, ... OutputStream entityStream) throws IOException {",
      "    entityStream.write(line.getBytes(StandardCharsets.UTF_8));  // raw bytes, untouched",
      "  }",
      "}",
    ],
    "Without this, quarkus-rest-jackson wraps each String as a quoted JSON string, escaping the newline, breaking NDJSON.",
    { fontSize: 12 });
  addNotes(s, "This is the gotcha that generalizes, and it's worth the slide. Declaring @Produces application/x-ndjson on a method returning Multi of String is not, by itself, enough to get raw NDJSON on the wire. Quarkus REST's Jackson integration registers a message-body writer broadly enough that it wins the writer lookup for String even on a media type it has no special knowledge of; when it wins, it does what Jackson always does with a String: serializes it as a quoted JSON string, escaping the line's own embedded newline to a backslash-n. So each NDJSON record, which is supposed to be independently parseable JSON on its own line, ends up wrapped inside an outer JSON string, which breaks newline-delimited JSON and fails schema validation outright. This narrowly-scoped @Provider fixes it: it's registered for exactly application/x-ndjson and String, so it wins that specific lookup, and writeTo does the only thing an NDJSON writer should: write the already-serialized line's bytes to the socket, untouched, because toJsonLine already produced a complete JSON object plus a trailing newline. The lesson generalizes beyond NDJSON: any reactive endpoint producing pre-serialized text on a media type a general-purpose writer might also claim needs a dedicated @Provider scoped to that combination, or the generic writer reinterprets bytes that were already in final form.");
}

/* --- Range diagram --- */
{
  const s = S();
  addDiagramSlide(s, "PAYLOADS", "Large binaries: HEAD, Range, 206",
    "r15-range",
    "HEAD learns size + range support; GET with a Range header returns 206 Partial Content and a Content-Range.",
    { x: 1.60, y: 1.70, w: 10.13, h: 4.55 });
  addNotes(s, "For large binary resources, a cargo manifest PDF of many megabytes, the pattern is the standard HTTP range machinery from the concept deck, and Quarkus serves it with ordinary resource methods. HEAD returns the headers without a body so the client learns Content-Length and Accept-Ranges: bytes before downloading anything. Then a GET with a Range header fetches a slice, and the server answers 206 Partial Content with a Content-Range header stating which bytes and the total size. A range past the end is a 416. There's nothing Quarkus-specific or exotic here: it's HEAD plus Range plus 206, which is exactly why it's robust: every client, cache, and download manager already speaks it. I'm showing it as a diagram rather than code because the implementation is just reading the Range header, slicing the resource, and setting the status and Content-Range; the pattern is the valuable part.");
}

/* ======================= DIVIDER 08 ======================= */
divider("08", "Events & multi-protocol contracts",
  "Publishing CloudEvents to Kafka with SmallRye Reactive Messaging.",
  "The same booking service answers REST synchronously and announces state changes asynchronously. In Quarkus the event side is SmallRye Reactive Messaging: a CloudEvents-enveloped BookingEvent emitted to a Kafka channel, off the request thread, typed by the same shared schema as the REST Booking.");

/* --- multi-protocol diagram --- */
{
  const s = S();
  addDiagramSlide(s, "CONTRACTS", "One service, two protocols, one schema",
    "r21-multiprotocol",
    "OpenAPI (sync) and AsyncAPI (events) both $ref the shared JSON Schema; Quarkus publishes the CloudEvents envelope to Kafka.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "The multi-protocol picture from the 100-level deck, with the Quarkus implementation highlighted. The booking service answers POST /bookings synchronously under the OpenAPI contract, and when a booking confirms it also publishes a CloudEvents-enveloped BookingEvent to a Kafka channel declared by the AsyncAPI contract, and both contracts $ref the same shared JSON Schema, so the Booking a REST client reads and the BookingEvent a Kafka consumer reads can't drift on their shared fields. On the Quarkus side the publish path is SmallRye Reactive Messaging's Kafka connector, which is the idiomatic emit path rather than a hand-rolled KafkaProducer. The next two slides are the configuration and the publisher code.");
}

/* --- Kafka config + publisher --- */
{
  const s = S();
  addCodeSlide(s, "CONTRACTS", "SmallRye Reactive Messaging: the channel", "properties · Quarkus",
    [
      "# application.properties — wire the outgoing 'booking-events' channel to Kafka",
      "kafka.bootstrap.servers=kafka:9092",
      "mp.messaging.outgoing.booking-events.connector=smallrye-kafka",
      "mp.messaging.outgoing.booking-events.topic=shipping.bookings.lifecycle",
      "mp.messaging.outgoing.booking-events.value.serializer=\\",
      "    org.apache.kafka.common.serialization.StringSerializer",
      "",
      "// Inject the channel as an Emitter — no hand-rolled KafkaProducer",
      "@Inject @Channel(\"booking-events\") Emitter<String> emitter;",
    ],
    "Config names the channel; the topic is the exact one the AsyncAPI contract declares (shipping.bookings.lifecycle).",
    { fontSize: 12 });
  addNotes(s, "The event plumbing is configuration plus one injected field. In application.properties, the outgoing channel named booking-events is bound to the smallrye-kafka connector, pointed at the topic shipping.bookings.lifecycle (the exact channel name the AsyncAPI contract declares, so the config and the contract agree) with a String value serializer because we serialize the CloudEvents envelope to a JSON string ourselves. Then in code, you inject an Emitter of String annotated with @Channel booking-events, and that's the whole wiring: no hand-rolled KafkaProducer, no connection management, no manual serialization setup. This is the idiomatic Quarkus messaging path: declare the channel in config, inject the Emitter, call send. It also means the same code runs against a Dev Services Kafka in tests and a real broker in production with only the bootstrap servers changing. The next slide is the publisher that uses this emitter.");
}

/* --- publisher code --- */
{
  const s = S();
  addCodeSlide(s, "CONTRACTS", "The CloudEvents publisher", "java · Quarkus",
    [
      "public void publishConfirmed(Booking confirmed, BookingStatus previousStatus) {",
      "  try {",
      "    Map<String,Object> data = new LinkedHashMap<>();   // = $defs/BookingEvent",
      "    data.put(\"bookingId\", confirmed.id()); data.put(\"status\", ...);",
      "    data.put(\"previousStatus\", ...); data.put(\"origin\", confirmed.origin()); ...",
      "    Map<String,Object> envelope = new LinkedHashMap<>();",
      "    envelope.put(\"specversion\", \"1.0\"); envelope.put(\"id\", \"evt_\" + Ulid.generate());",
      "    envelope.put(\"source\", \"/shipping/bookings\");",
      "    envelope.put(\"type\", \"dev.patterncatalyst.shipping.booking.confirmed\");",
      "    envelope.put(\"subject\", confirmed.id()); envelope.put(\"data\", data); ...",
      "    emitter.send(mapper.writeValueAsString(envelope))",
      "        .toCompletableFuture().get(10, TimeUnit.SECONDS);  // bounded wait for ack",
      "  } catch (Exception e) { LOG.error(\"publish failed\", e); }  // never a 5xx",
      "}",
    ],
    "A failed background publish is logged and swallowed: a Kafka outage degrades the event stream, never the REST response.",
    { fontSize: 10 });
  addNotes(s, "The publisher, and it's where the shared-schema thesis becomes concrete. It builds the CloudEvents envelope by hand: specversion 1.0, a unique evt_ id, the source URI, the reverse-DNS type naming the event, subject set to the booking id, and the data payload, because the point is the shape of the envelope, not an SDK's convenience methods. The data map is the BookingEvent from the shared schema: bookingId, the new status, the previousStatus it transitioned from, origin, and destination; those origin and destination values are the same Location type the REST Booking uses, which is what guarantees the sync and async views can't drift. It serializes the envelope to JSON and sends it through the injected Emitter, then blocks with a bounded ten-second timeout on the returned CompletionStage so a caller running this off the request thread knows the broker actually acked before moving on. The catch block is the production-critical detail: a failed publish is logged and swallowed, never rethrown, because this runs after the synchronous REST response has already gone out: a Kafka outage must degrade the event stream, not turn a successful booking confirmation into a 5xx. The two paths share the booking's data, not a failure domain. The Python side does the identical envelope with confluent-kafka.");
}

/* ======================= DIVIDER 09 ======================= */
divider("09", "Testing & running it",
  "@QuarkusTest with RestAssured, the test pyramid, and the three tiers.",
  "Proving the Quarkus implementation honours the contract: an in-process @QuarkusTest layer with RestAssured, sitting inside the shared test pyramid, and then running the same image from Compose to minikube to OpenShift, including the native build Quarkus makes tractable.");

/* --- test pyramid diagram --- */
{
  const s = S();
  addDiagramSlide(s, "TESTING", "The test pyramid",
    "r24-test-pyramid",
    "@QuarkusTest is the in-process integration layer; contract lint, the shared Newman collection, and load sit around it.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "The shared test pyramid from the concept deck, with the Quarkus-specific layer named. At the base, contract tests lint the OpenAPI and AsyncAPI and validate responses against the shared schema. The integration layer is where @QuarkusTest sits: an in-process test that boots the full application in the same JVM as the test. Above that, the API/end-to-end layer runs a shared Newman collection against the running service, and because the collection is shared, the exact same assertions run against both the Quarkus and the Python deployments. A load pass on top confirms the caps and the async flow hold under concurrency. The key framing is that every layer checks the same one contract from a different angle, which is what lets the two stacks stay interchangeable. The next slide is the @QuarkusTest itself.");
}

/* --- @QuarkusTest code --- */
{
  const s = S();
  addCodeSlide(s, "TESTING", "@QuarkusTest + RestAssured, in-process", "java · Quarkus",
    [
      "@QuarkusTest                       // boots the full app in the test JVM",
      "class BookingResourceTest {",
      "  @Test",
      "  void createBooking_returns201WithLocationAndBody() {",
      "    given().contentType(\"application/json\").body(VALID_BOOKING)",
      "    .when().post(\"/bookings\")",
      "    .then().statusCode(201)",
      "      .header(\"Location\", matchesPattern(\"^/bookings/bkg_[0-9A-HJKMNP-TV-Z]{26}$\"))",
      "      .body(\"status\", equalTo(\"PENDING\"))",
      "      .body(\"quote.amount\", equalTo(\"3001.25\"));",
      "  }",
      "  @Test void getBooking_nonexistent_returns404ProblemBody() {",
      "    given().when().get(\"/bookings/{id}\", \"bkg_0...0\")",
      "    .then().statusCode(404).contentType(\"application/problem+json\"); }",
      "}",
    ],
    "RestAssured's given/when/then asserts the full HTTP contract (status, headers, and body) against the booted app.",
    { fontSize: 10 });
  addNotes(s, "The @QuarkusTest layer in real code. The @QuarkusTest annotation boots the full Quarkus application (CDI, JAX-RS, Jackson) in the same JVM as the test, so this exercises the actual wiring, not mocks, but in-process rather than over a network. The tests use RestAssured's given-when-then fluent style, which reads almost like the HTTP it's asserting: given a JSON body, when you POST to /bookings, then expect 201, a Location header matching the booking-id pattern, a PENDING status, and the computed quote. The second test checks the 404 path returns a Problem body with the right content type. This asserts the full HTTP contract: status code, headers, and body shape, which is exactly what a client sees. One honest operational note from the example's README: this @QuarkusTest isn't run by the CI verify script, because a Maven and JVM boot per CI matrix leg is too heavy and slow for the bounded, deterministic CI path; it's the local and build-time test layer, while the live-container contract checks and the Newman collection are what run in CI. Both are real layers of the pyramid; they just run in different places.");
}

/* --- running it --- */
{
  const s = S();
  addDiagramSlide(s, "RUNNING IT", "One image across three tiers",
    "r25-deployment-tiers",
    "The same Quarkus image: Compose → minikube → OpenShift Local. JVM or native (GraalVM); UBI base images; restricted-v2 on CRC.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "Running the Quarkus service across the three tiers from the concept deck, with the Quarkus specifics. Tier one, Docker or Podman Compose, brings the service up alongside Postgres and Kafka plus the LGTM observability stack, so you get distributed tracing from the first run. Tier two is minikube with standard Kubernetes Deployments, Services, and Ingress; tier three is OpenShift Local with Routes, BuildConfig, and the restricted-v2 security context constraint. The Quarkus-specific angle: the image can be the JVM build or a GraalVM native binary, and this is where the build-time model from the opening section pays off most, because native compilation is tractable precisely because Quarkus resolved its bindings at build time, so there's little left to reflect on. Base images are UBI, Red Hat Universal Base Images, pinned to exact tags. And the whole thing holds the house rule: examples run on plain infrastructure, Docker Engine on a Fedora or RHEL workstation, plain minikube, OpenShift Local, no managed cloud on the primary path. The same artifact promotes up the tiers; only the surrounding manifests change.");
}

/* ======================= DIVIDER 10 ======================= */
divider("10", "Ecosystem & wrap-up",
  "Why teams stay on Quarkus as a service grows, and where to go deeper.",
  "Beyond REST itself, three ecosystem pieces come up often enough to name, then where to go next.");

/* --- ecosystem --- */
{
  const s = S();
  addContentTitle(s, "ECOSYSTEM", "Why teams stay on Quarkus");
  addBullets(s, [
    "LangChain4j for LLM-backed SSE: stream model tokens over the same Multi machinery as the NDJSON export; one reactive type, two uses.",
    "Camel Quarkus & CXF: bridge to systems that don't speak REST (a partner's SOAP endpoint, a message queue, a file drop) as build-time-optimized components.",
    "JobRunr for background jobs: persist job state to the app's own database with retry and scheduling, short of a full broker; the Quarkus answer to Chapter 10's out-of-band work.",
  ], { fontSize: 16 });
  addCaption(s, "These are why a team already building REST on Quarkus tends to stay there as the service's responsibilities grow past plain request/response.");
  addNotes(s, "The build-time model and reactive streaming are Quarkus REST's own contribution; the rest of why Quarkus is a recurring choice lives in the surrounding ecosystem, and three pieces come up enough to name. First, LangChain4j for LLM-backed Server-Sent Events: a service fronting a language model needs to forward tokens as they're generated, not buffer the whole answer, and LangChain4j's streaming chat model maps onto the exact same Multi machinery the NDJSON export already uses: a method returning Multi of String over text/event-stream, one SSE event per token, with the same backpressure and non-blocking guarantees. One reactive type, two uses. Second, Camel Quarkus and CXF for integration: not every system a REST API talks to speaks REST (a partner's legacy SOAP endpoint, a mainframe feed over a queue, a file drop), and Camel brings enterprise integration patterns into the app as build-time-optimized components, while CXF handles putting a REST facade in front of a SOAP backend that isn't going away this quarter. Third, JobRunr for background jobs: a REST endpoint that triggers slow work shouldn't hold the request open, and JobRunr persists job state to the application's own database with retry and scheduling, a proportionate choice short of a full event-streaming platform. None of these needs a worked example here; they're why a team already on Quarkus for REST tends to stay on Quarkus as the service grows.");
}

/* --- wrap --- */
{
  const s = S();
  addContentTitle(s, "WRAP-UP", "Quarkus, pattern by pattern");
  addBullets(s, [
    "Build-time binding: @RestHeader/@RestQuery resolved once, yielding fast start, low memory, native-ready builds.",
    "Records + Bean Validation + Problem mappers: declarative DTOs, every failure application/problem+json.",
    "Reactive Multi + a scoped @Provider writer: honest streaming without double-encoding.",
    "SmallRye Reactive Messaging: CloudEvents to Kafka off the request thread, typed by the shared schema.",
    "Go deeper: examples/*/quarkus/**, Chapter 22, and the Python/FastAPI companion deck for the other stack.",
  ], { fontSize: 16 });
  addNotes(s, "Pulling the Quarkus story together. The defining choice is build-time binding: @RestHeader, @RestQuery, @RestPath resolved once during the build instead of by reflection per request, which is what gives you fast startup, low memory, and tractable native images. The resource layer is records as DTOs with declarative Bean Validation, and a family of exception mappers that guarantee every failure, whether we raised it or the runtime did, comes back as application/problem+json. The reactive story is Mutiny's Multi for streaming, paired with a narrowly-scoped @Provider message-body writer so NDJSON isn't double-encoded by the general-purpose Jackson writer. And the event side is SmallRye Reactive Messaging, publishing a CloudEvents envelope to Kafka off the request thread, with the payload typed by the same shared schema as the REST Booking so the two protocols can't drift. All of it is real code in examples slash star slash quarkus, expanded in Chapter 22. To see the identical patterns in the other stack, the Python and FastAPI companion deck is the next one.");
}

/* --- Q&A --- */
{
  const s = S();
  addContentTitle(s, "THANK YOU", "Q&A");
  addBullets(s, [
    "Questions on any of it: build-time binding, Bean Validation, reactive streaming, the Kafka publisher, @QuarkusTest, native?",
    "Code: examples/*/quarkus/** · deep-dive: _docs/22-quarkus-rest-in-depth.md · github.com/patterncatalyst/api-patterns-and-practices-rest",
  ], { fontSize: 16 });
  addCaption(s, "Red Hat is the world's leading provider of enterprise open source software solutions, trusted by the Fortune 500 for support, training, and consulting.");
  addNotes(s, "Thank you. That's every pattern from the 100-level deck, built in Quarkus: the build-time binding model and what it buys you, the contract-first resource with records and Bean Validation, Problem-details mappers, content negotiation and merge-patch, keyset pagination, the async operation across two resource classes, HATEOAS links from the lifecycle state machine, media-type versioning, soft deletion, reactive NDJSON with its dedicated writer, Range for large binaries, and the CloudEvents-over-Kafka publisher on SmallRye Reactive Messaging, all tested with @QuarkusTest and runnable from a laptop to OpenShift, as a JVM or native image. I'm happy to take questions on any of it. All the code is under examples slash star slash quarkus, the deep-dive is Chapter 22, and the whole project is public on the Pattern Catalyst GitHub organization. And the standard Red Hat close: Red Hat is the world's leading provider of enterprise open source software solutions, trusted by the Fortune 500 for award-winning support, training, and consulting services.");
}

/* ======================= APPENDIX A ======================= */
divider("A", "Appendix: extra Quarkus code",
  "Reference listings kept out of the main flow: PUT idempotency, cargo sub-resource, config.",
  "Appendix material: keep it open in another window rather than reading front to back. These are the code variants that round out the examples but would slow the main narrative.");

/* --- PUT idempotency --- */
{
  const s = S();
  addCodeSlide(s, "APPENDIX A · METHODS", "PUT: full replace, made idempotent", "java · Quarkus",
    [
      "@PUT @Path(\"/{id}\") @Consumes(APPLICATION_JSON) @Produces(APPLICATION_JSON)",
      "public Response replaceBooking(@RestPath String id, @Valid BookingRequest request) {",
      "  Booking existing = store.get(id);",
      "  if (existing == null) return notFound(id);",
      "  // Deterministic cargo ids keyed on (bookingId, index): PUT must be",
      "  // idempotent, so replacing with the SAME body twice yields the SAME ids.",
      "  List<Cargo> cargoItems = toCargoItemsForReplace(id, request.cargo());",
      "  Booking replaced = new Booking(existing.id(), existing.status(),",
      "      request.origin(), request.destination(), cargoItems,",
      "      QuoteCalculator.compute(cargoItems), request.requestedPickup(),",
      "      existing.createdAt(), nowUtc());",
      "  store.put(replaced); return Response.ok(replaced).build();",
      "}",
    ],
    "POST mints random cargo ids; PUT mints deterministic ones so a repeated identical PUT lands byte-identical state.",
    { fontSize: 10 });
  addNotes(s, "An appendix detail that's easy to get wrong: making PUT fully idempotent. PUT is a full replacement and the idempotency matrix requires that replacing a booking with the same body twice lands the same state both times. The subtlety is cargo ids. POST correctly mints a fresh random ULID for each cargo item: a new booking gets new ids. But if PUT did the same, replacing a booking with an identical body twice would produce different cargo ids each time, which violates idempotency; the second response wouldn't byte-match the first. So replaceBooking uses toCargoItemsForReplace, which mints deterministic ids keyed on the booking id and the item's index, so the same body always yields the same ids. It also preserves the existing id, status, and createdAt; only the client-supplied fields and updatedAt change. This is the kind of correctness detail that the shared contract and idempotency tests actually catch, and it's why it's worth showing: 'PUT is idempotent' is a property you have to implement by design, not one you get for free.");
}

/* --- cargo sub-resource --- */
{
  const s = S();
  addCodeSlide(s, "APPENDIX A · RESOURCES", "The cargo sub-resource", "java · Quarkus",
    [
      "@POST @Path(\"/{id}/cargo\") @Consumes(APPLICATION_JSON) @Produces(APPLICATION_JSON)",
      "public Response addCargo(@RestPath String id, @Valid CargoRequest request) {",
      "  Booking booking = store.get(id);",
      "  if (booking == null) return notFound(id);",
      "  Cargo cargo = new Cargo(\"crg_\" + Ulid.generate(), request.description(),",
      "      request.type(), request.dimensions(), request.hazardousOrDefault());",
      "  List<Cargo> newList = new ArrayList<>(booking.cargo()); newList.add(cargo);",
      "  Booking updated = /* booking with newList + recomputed quote + updatedAt */;",
      "  store.put(updated);",
      "  return Response.status(CREATED)",
      "      .header(\"Location\", \"/bookings/\" + id + \"/cargo/\" + cargo.id())",
      "      .entity(cargo).build();",
      "}",
    ],
    "Cargo is nested under its booking (direct ownership); adding one recomputes the quote and 201s with a nested Location.",
    { fontSize: 10 });
  addNotes(s, "The cargo sub-resource, as an appendix reference. This is the 'nest when it reads as ownership' guidance from the concept deck in code: cargo lives at /bookings/{id}/cargo because a cargo item belongs to a booking. addCargo validates the CargoRequest with @Valid, mints a crg_-prefixed id, appends it to the booking's cargo list, recomputes the quote because adding cargo changes the price, persists the updated booking, and returns 201 with a Location pointing at the nested cargo URI. It's one level of nesting, which is the sweet spot; deeper than that and the guidance was to use links instead. Nothing exotic, but it rounds out the resource surface and shows the sub-resource pattern concretely.");
}


/* --- Scan to explore (QR codes) --- */
{
  const s = S();
  addContentTitle(s, "SCAN TO EXPLORE", "Take it with you");

  // Left QR: the site
  s.addImage({ path: `${ASSETS}/qr-rest-site.png`, x: 2.30, y: 1.78, w: 3.10, h: 3.10 });
  s.addText("The site", { x: 1.55, y: 4.98, w: 4.60, h: 0.40,
    fontFace: FONT.title, fontSize: 18, bold: true, color: COLOR.ink, align: "center", valign: "middle" });
  s.addText("Chapters, the OpenAPI / AsyncAPI contracts, and both-stack runnable examples", { x: 1.45, y: 5.40, w: 4.80, h: 0.72,
    fontFace: FONT.body, fontSize: 13, italic: true, color: COLOR.caption, align: "center", valign: "top" });
  s.addText("patterncatalyst.github.io/api-patterns-and-practices-rest", { x: 1.45, y: 6.12, w: 4.80, h: 0.32,
    fontFace: FONT.mono, fontSize: 10, color: COLOR.red, align: "center", valign: "middle" });

  // Right QR: the hub
  s.addImage({ path: `${ASSETS}/qr-hub.png`, x: 7.93, y: 1.78, w: 3.10, h: 3.10 });
  s.addText("Workshops & Tutorials", { x: 7.18, y: 4.98, w: 4.60, h: 0.40,
    fontFace: FONT.title, fontSize: 18, bold: true, color: COLOR.ink, align: "center", valign: "middle" });
  s.addText("The whole series: every workshop, tutorial, and deck in one place", { x: 7.08, y: 5.40, w: 4.80, h: 0.72,
    fontFace: FONT.body, fontSize: 13, italic: true, color: COLOR.caption, align: "center", valign: "top" });
  s.addText("patterncatalyst.github.io/patterncatalyst-workshops-tutorials-list", { x: 7.08, y: 6.12, w: 4.80, h: 0.32,
    fontFace: FONT.mono, fontSize: 9, color: COLOR.red, align: "center", valign: "middle" });

  addNotes(s, "This is the Quarkus implementation deck, so the left code takes you to the runnable Quarkus example and contract, the right to the whole series. On the left, the site: the chapters, the OpenAPI and AsyncAPI contracts, and the runnable both-stack examples, all public. On the right, the Workshops and Tutorials hub: every workshop, tutorial, and deck in the series in one place, including the gRPC, GraphQL, and WebSockets siblings as they land. Scan whichever is useful; both are on the Pattern Catalyst GitHub organization.");
}

pres.writeFile({ fileName: OUT })
  .then((p) => console.log("WROTE", p, "slides:", pageNum))
  .catch((e) => { console.error(e); process.exit(1); });
