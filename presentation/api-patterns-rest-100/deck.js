// deck.js — "API Patterns & Practices: REST — 100 (Concepts)".
// Stack-agnostic: the WHAT and WHY of REST, shipping/cargo domain. Snippets are
// plain HTTP / JSON / OpenAPI — never Java or Python. The Quarkus and Python
// companion decks (../api-patterns-rest-quarkus, ../api-patterns-rest-python)
// carry the implementations.
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

const OUT = path.resolve(__dirname, "api-patterns-rest-100-r1.0.pptx");
const REV = "r1.0";

const pres = newDeck();
pres.title = "API Patterns & Practices: REST — 100 (Concepts)";
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
  s.addText("API PATTERNS & PRACTICES · REST · 100", { x: 6.00, y: 1.82, w: 6.90, h: 0.34,
    fontFace: FONT.title, fontSize: 14, bold: true, color: COLOR.red, charSpacing: 6, align: "left", valign: "middle" });
  s.addText([{ text: "REST: the patterns,", options: { breakLine: true } }, { text: "and the why." }], {
    x: 5.95, y: 2.28, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("The design patterns behind a production REST API — resources, methods, async, HATEOAS, versioning — in the shipping & cargo domain. Stack-agnostic: the Quarkus and Python/FastAPI decks show the implementations.", {
    x: 6.00, y: 4.30, w: 6.80, h: 1.20, fontFace: FONT.body, fontSize: 17, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText([
    { text: "Robert Sedor", options: { bold: true, color: COLOR.ink, breakLine: true } },
    { text: "Principal Chief Architect, Application Development", options: { color: COLOR.caption } },
  ], { x: 6.00, y: 5.70, w: 6.70, h: 0.80, fontFace: FONT.body, fontSize: 15, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 6.40, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "Welcome. This is the 100-level deck in the API Patterns & Practices: REST series, and it is deliberately the what and the why — the patterns themselves, not any one framework's implementation of them. The domain is shipping and cargo booking throughout: bookings, cargo, locations by UN/LOCODE, manifests. The premise for the whole series is one contract, two runtimes — every pattern we discuss ships in both Quarkus and Python/FastAPI on the site, validated against a single OpenAPI contract so the two can't drift. But in THIS deck the snippets are plain HTTP, JSON, and OpenAPI — the wire contract — because the goal is to make each design decision defensible independent of language. When you want to see how a pattern is actually built, the two companion decks take over: one for Quarkus, one for Python/FastAPI. I'm Robert Sedor, Principal Chief Architect in Application Development. By the end you should be able to explain when to use which method, how to page a large collection, how to model long-running work, how to let a resource advertise its own next steps, and how to version without breaking callers.");
}

/* ======================= 2 · AGENDA ======================= */
{
  const s = S();
  addContentTitle(s, "ROADMAP", "Agenda");
  addTwoColBullets(s,
    [
      "APIs & patterns, and a decision framework",
      "Designing around resources",
      "Contract-first with OpenAPI",
      "HTTP methods & the idempotency matrix",
      "HTTP semantics: negotiation & status codes",
      "Partial updates: JSON Patch vs Merge Patch",
      "Filtering, projection & pagination",
      "Sub-resources",
    ],
    [
      "Async & long-running operations · jobs",
      "HATEOAS",
      "Soft deletion & GDPR purge",
      "Versioning",
      "Large binary resources & streaming",
      "Multi-protocol contracts",
      "Testing concepts · running it",
      "The complete project · Q&A",
    ],
    { fontSize: 15 });
  addNotes(s, "Here's the arc. We start with the landscape — what an API even is, where REST sits among the alternatives, and a decision framework so that every later choice is deliberate rather than reflexive. Then the core design work: shaping resources, pinning them to a contract, and getting the HTTP method semantics right, including the safe/idempotent matrix that governs retries. The middle is HTTP done properly — content negotiation, status codes, partial updates, and reading large collections through filtering and pagination. From there the patterns that separate a toy API from a production one: asynchronous operations, HATEOAS, soft deletion with a GDPR purge path, and versioning. We finish with the topics the site adds beyond a classic REST talk — streaming, multi-protocol contracts, the testing pyramid, and the three deployment tiers — then the complete project that ties it together. Everything here is conceptual and stack-agnostic; cross-references are by topic, not slide number, so you can follow the same thread into the site chapters and the implementation decks afterward.");
}

/* ======================= 3 · SERIES MAP ======================= */
{
  const s = S();
  addContentTitle(s, "SERIES MAP", "How this series fits together");
  addBullets(s, [
    "This 100-level deck is the patterns: what each REST pattern is and why you reach for it — stack-agnostic.",
    "Every pattern here ships in BOTH Quarkus and Python/FastAPI on the site, built against one OpenAPI contract and validated in CI.",
    "The implementation detail lives in two companion decks: “REST — Quarkus Implementation” and “REST — Python/FastAPI Implementation”.",
    "Snippets in this deck are plain HTTP, JSON, and OpenAPI — the wire contract — never Java or Python.",
  ], { fontSize: 17 });
  addCaption(s, "100 = the patterns. The Quarkus and Python decks = the implementations of those same patterns, in the same domain.");
  addNotes(s, "One slide to set expectations, because the series is three decks and it helps to know which one you're in. This 100-level deck answers what and why: what each REST pattern is, and why you'd reach for it — and it does that without tying you to a language, so the reasoning transfers to any stack. The site behind it ships every one of these patterns twice, in Quarkus and in Python/FastAPI, built against a single OpenAPI contract and validated in continuous integration so the two implementations stay interchangeable. The how lives in two companion decks: one walks through the Quarkus implementation with real Java, the other the Python/FastAPI implementation with real Python. That's why every snippet you'll see here is plain HTTP, JSON, or OpenAPI YAML — the contract on the wire — rather than framework code. If a pattern raises an implementation question today, the short answer is: the concept is here, the code is in the matching implementation deck. Keep that split in mind and the three decks compose into one story rather than repeating each other.");
}

/* ======================= DIVIDER 01 ======================= */
divider("01", "Foundations & the decision lens",
  "What REST is, where it fits, and a framework for choosing it on purpose.",
  "Before any design work, two foundations. First, a precise statement of what REST is — not 'JSON over HTTP', but a set of architectural constraints and a resource-oriented model. Second, a decision framework, because 'just use REST' and 'just use gRPC' are wrong for the same reason: neither names the property of the interaction that makes it true. This section gives you the vocabulary the rest of the session reuses.");

/* --- APIs & patterns --- */
{
  const s = S();
  addContentTitle(s, "FOUNDATIONS", "APIs & patterns");
  addBullets(s, [
    "RPC-oriented APIs are designed around interfaces and methods — you call a procedure.",
    "Web APIs are reachable over HTTP; the family spans XML-RPC, JSON-RPC, SOAP, and REST.",
    "REST is an architectural style over HTTP with five constraints: client-server, statelessness, cacheability, layered system, and a uniform interface.",
    "An API design pattern is a template: agreed conventions and the behaviour that follows from them, for both internal and external APIs.",
    "Resource-oriented APIs model the domain as a hierarchy of resources and collections — the nouns, not the procedures.",
  ], { fontSize: 16 });
  addNotes(s, "Start with the distinction that frames everything. An RPC-oriented API is designed in terms of interfaces and methods — the unit of thought is a procedure you invoke, like confirmBooking(id). A Web API is simply one reachable over HTTP, and that family is broad: XML-RPC, JSON-RPC, SOAP, and REST all ride HTTP but make very different promises. REST is specifically an architectural style, and it's defined by five constraints, not by a serialization format: client-server separation, statelessness (each request carries everything the server needs), cacheability (responses declare whether they can be stored), a layered system (a client can't tell whether it's talking to the origin or an intermediary), and a uniform interface (the same small set of operations across all resources). An API design pattern sits on top of that: a template of conventions and the behaviour they imply, so a consumer can predict how an endpoint behaves before reading its docs. And the mental model we'll use throughout is resource-oriented: the domain is a hierarchy of resources and collections — the nouns — manipulated through a uniform set of methods. Everything after this slide is a consequence of taking those two ideas seriously.");
}

/* --- Resource-oriented architecture --- */
{
  const s = S();
  addContentTitle(s, "FOUNDATIONS", "Resource-oriented architecture");
  addTwoColBullets(s,
    [
      { text: "Four building blocks", options: { bold: true, bullet: false } },
      "Resources — the business entities (a Booking, a Cargo item).",
      "Names — stable URIs that address them (/bookings/{id}).",
      "Representations — JSON today; the shape on the wire.",
      "Links — how resources connect (the basis for HATEOAS).",
    ],
    [
      { text: "Four properties", options: { bold: true, bullet: false } },
      "Addressability — every resource has a URI.",
      "Statelessness — no server-side session between calls.",
      "Connectedness — resources link to related resources.",
      "A uniform interface — the same methods everywhere.",
    ],
    { fontSize: 15 });
  addCaption(s, "A resource-oriented API is not a database: creating a booking can trigger routing, quoting, and notifications behind one resource.");
  addNotes(s, "Resource-oriented architecture has four building blocks and four properties, and they map onto each other. The building blocks: resources are the business entities — in our domain, a Booking is the aggregate root and a Cargo item sits under it. Names are the URIs that address them, and they should be stable; a URI is a promise. Representations are what actually travels on the wire — JSON here, but a resource is not its representation. And links are how resources reference each other, which is the raw material for HATEOAS later. The four properties fall out of the REST constraints: addressability (everything worth talking about has a URI), statelessness (the server keeps no session between your calls — each request stands alone), connectedness (resources point at related resources rather than making the client guess URLs), and a uniform interface (GET, POST, PUT, PATCH, DELETE mean the same thing on every resource). The caption carries the warning that catches teams out: a resource-oriented API is not a view of your database. Creating a booking is a POST to a collection, but behind that one resource the server may run a routing engine, compute a quote, and emit notifications. Model the business entity and the operations on it — never expose the table.");
}

/* --- decision framework diagram --- */
{
  const s = S();
  addDiagramSlide(s, "FOUNDATIONS", "The API decision framework",
    "r02-decision-axes",
    "Seven axes you read off an interaction before choosing a style — and REST is the answer on most, not all, of them.",
    { x: 1.30, y: 1.75, w: 10.73, h: 4.60 });
  addNotes(s, "This is the lens every later topic reuses. The mistake isn't choosing REST; it's choosing any style by habit and forcing every interaction through it. The fix is to read the interaction off seven axes first. Interaction shape: is it request/response, a stream of values over time, or a fire-and-forget event? That one eliminates whole categories. Payload size and shape: a few hundred bytes of booking JSON versus a tens-of-megabytes manifest, or a client that wants to choose its own projection. Latency and real-time need: does correctness depend on a response arriving inside a bound the caller can name? Cacheability: is this a named, addressable, read-heavy resource a CDN or browser can store? That's where REST's model pays for itself. Client diversity: browsers, mobile, third parties — or just services the same team owns? Evolution and versioning: does this contract have to outlive many independent consumers? Operational constraints: what does the proxy, firewall, and CDN between client and service allow? When the path includes infrastructure you don't control, it votes, and it usually votes REST. Run all seven and you get a defensible choice — and sometimes that choice is gRPC, GraphQL, WebSockets, or an event stream. Habit is not an axis.");
}

/* --- worked decision --- */
{
  const s = S();
  addContentTitle(s, "FOUNDATIONS", "A worked decision: confirming a booking");
  addBullets(s, [
    "Interaction shape rules out a blocking call: routing + capacity checks take seconds to minutes.",
    "Latency is asymmetric — the caller tolerates waiting, as long as it isn't blocked on one connection.",
    "Client diversity is decisive: browsers, mobile apps, and partner servers all already hold a REST session.",
    "The axes land on REST — but the asynchronous kind: 202 Accepted → poll an Operation → 303 to the result.",
    "A second interaction hides inside the first: notifying downstream systems is a fire-and-forget event, not a call.",
  ], { fontSize: 16 });
  addNotes(s, "Make the framework concrete. When a customer submits a booking, confirming it runs the routing engine and a capacity check — work that can take anywhere from a second to half a minute. Run the axes. Interaction shape immediately rules out a synchronous POST that blocks until a 200: the shape of the work doesn't match one request/response round trip. Payload and cacheability add little; the bodies are small and a confirmation isn't worth caching. Latency is sensitive but asymmetrically — the caller can tolerate minutes of total wait as long as it isn't blocked on one socket the whole time, which points at decoupling acceptance from completion. Client diversity is the decisive axis: whatever asks for confirmation is a browser, a mobile app, or a partner's server, and all of them already speak REST to this API. So the answer is REST — but the asynchronous operation pattern: POST the confirmation, get 202 Accepted with a Location header pointing at an Operation resource, poll that, and follow a 303 See Other to the confirmed booking when it's done. We'll build exactly that flow later. Now the twist: once the booking is confirmed, how do the warehouse, the customs broker, and the carrier's tracking feed find out? None of them asked, there may be an unknown number of them, and none is polling. Re-run interaction shape and the answer changes — that's a fire-and-forget event on a stream, not a REST call. One state transition, two correct answers, because two interactions were hiding inside one requirement.");
}

/* ======================= DIVIDER 02 ======================= */
divider("02", "Designing resources with a contract",
  "Nouns not verbs, pinned to one OpenAPI contract, with method semantics that make retries safe.",
  "With the lens in place, the core design work: shape the resources as nouns, pin them to a single contract both stacks are generated and validated against, and get the HTTP method semantics right — especially which methods are safe to retry. This is where most of the day-to-day decisions live.");

/* --- design around resources (diagram) --- */
{
  const s = S();
  addDiagramSlide(s, "RESOURCES", "Design around resources",
    "r03-resource-model",
    "Collections and items, nested where it reads as ownership — model entities, never mirror the database schema.",
    { x: 1.30, y: 1.75, w: 10.73, h: 4.60 });
  addNotes(s, "The first design rule: URIs are nouns, and the HTTP method is the verb. A booking collection is /bookings; a single booking is /bookings/{id}; its cargo is /bookings/{id}/cargo. You never see /createBooking or /getBooking — the method already says create or get. Collections and items are different resources: a GET on /bookings returns a page of bookings; a GET on /bookings/{id} returns one. Nest a sub-resource only when it genuinely reads as ownership — cargo belongs to a booking — and prefer links over deep nesting past a level or two, because long nested URLs get brittle and redundant. The anti-patterns on the right are the ones that bite in production. Mirroring your table columns couples the API to a schema you'll want to change. A chatty API — forcing clients to make many tiny GETs to assemble one view — and its cousin, extraneous fetching (pulling back far more than the client needs), are both performance traps you design yourself into. The cure is the same on both sides: model the business entity and the operations on it, expose nouns plus the uniform method set, and use links to connect resources rather than deep structural nesting.");
}

/* --- good/bad URLs code --- */
{
  const s = S();
  addCodeSlide(s, "RESOURCES", "Nouns, not verbs — in the shipping domain", "url shapes",
    [
      "// Not good — verbs in the path, the DB leaking out",
      "POST /create-booking",
      "GET  /booking-row?table=bookings&pk=42",
      "",
      "// Good — nouns addressed by the uniform method set",
      "POST /bookings                     # create a booking",
      "GET  /bookings/{bookingId}         # one booking",
      "GET  /bookings/{bookingId}/cargo   # cargo under it",
      "PATCH /bookings/{bookingId}        # partial update",
      "DELETE /bookings/{bookingId}       # soft-delete (cancel)",
      "",
      "// Identifiers carry meaning, but stay opaque to clients",
      "bookingId  = bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4   # ULID-shaped",
      "location   = USNYC -> NLRTM                    # UN/LOCODE",
    ],
    "The path names the resource; the method names the action. IDs are opaque strings, locations are UN/LOCODE.");
  addNotes(s, "Here it is in our domain. The 'not good' block shows the two failure modes together: a verb in the path (/create-booking, which duplicates what POST already means) and the database leaking through the API (a row addressed by table and primary key). The 'good' block is the whole CRUD surface of a booking expressed as nouns plus methods: POST to the collection creates, GET on an item reads, GET on the sub-resource lists cargo, PATCH partially updates, DELETE cancels. Notice what the identifiers look like. A booking id is an opaque, ULID-shaped string with a bkg_ prefix — the prefix is a human affordance, but the client should treat the whole thing as opaque and never parse it. Locations are UN/LOCODE, the five-character port codes — USNYC for New York, NLRTM for Rotterdam — because reusing a well-known standard identifier beats inventing your own. These exact shapes come straight from the contract we'll look at next, and they stay consistent across every example in both stacks.");
}

/* --- contract-first OpenAPI --- */
{
  const s = S();
  addCodeSlide(s, "CONTRACT", "Contract-first with OpenAPI", "yaml · OpenAPI 3.1",
    [
      "# One contract: contracts/openapi/shipping-api.yaml (OpenAPI 3.1)",
      "paths:",
      "  /bookings:",
      "    post:",
      "      operationId: createBooking",
      "      requestBody:",
      "        content:",
      "          application/json:",
      "            schema:",
      "              # types defined ONCE in the shared JSON Schema",
      "              $ref: '../schemas/shipping.schema.json#/$defs/BookingRequest'",
      "      responses:",
      "        '201': { description: Booking created }   # + Location header",
    ],
    "Both stacks are generated/validated against this one document; CI fails the build on drift. (How: the impl decks.)");
  addNotes(s, "Contract-first is the spine of the whole series, so it's worth being precise about what it buys you. There is exactly one OpenAPI 3.1 document, shipping-api.yaml, and it is the source of truth for the synchronous surface. Payload types are not written inline here — they're defined once in a shared JSON Schema file and referenced with $ref, so Booking, BookingRequest, Money, Location, and Problem each exist in exactly one place. That matters because the same JSON Schema backs the event contracts later, which is how the synchronous and asynchronous views of a booking are guaranteed to agree. The operational payoff: both implementations are validated against this document in CI, and the build fails on drift. If someone changes a response shape in code without changing the contract, or changes the contract without updating a stack, the pipeline goes red. That turns 'the docs match the code' from a hope into a checked invariant. Contract-first also front-loads the design conversation: you argue about the shape of createBooking before anyone writes a handler, which is far cheaper than arguing after two services already disagree. How each framework generates from and validates against this contract is exactly what the Quarkus and Python decks cover.");
}

/* --- HTTP methods table --- */
{
  const s = S();
  addContentTitle(s, "METHODS", "HTTP methods on /bookings");
  addStatusTable(s, [
    { code: "GET", name: "retrieve", purpose: "Safe, cacheable read of a booking or a page of the collection." },
    { code: "POST", name: "create", purpose: "Create a booking; 201 Created + Location. Not idempotent." },
    { code: "PUT", name: "replace", purpose: "Full replacement of a booking with a complete representation. Idempotent." },
    { code: "PATCH", name: "partial update", purpose: "Apply a change document (JSON Patch / Merge Patch). Not inherently idempotent." },
    { code: "DELETE", name: "remove", purpose: "Soft-delete (cancel) the booking; hidden from default queries. Idempotent." },
  ], { colW: [1.70, 2.70, 7.69], rowH: 0.62 });
  addCaption(s, "POST applies to collections; PUT/PATCH/DELETE apply to items. The server, not the client, mints a new booking's URI.");
  addNotes(s, "The uniform interface, applied to bookings. GET retrieves — on the collection it returns a page, on an item the booking — and it's safe (no state change) and cacheable. POST creates: it's applied to the collection /bookings, the server assigns the new resource's URI and returns it in the Location header with a 201, and it is not idempotent — fire it twice and you get two bookings. PUT replaces: the client sends a complete representation of an item, and because the same request always lands the same state, it's idempotent. PATCH partially updates by sending a change document rather than the whole resource; it is not inherently idempotent — you have to design it to be if you want that. DELETE in our domain is a soft-delete: it cancels the booking and hides it from default queries rather than erasing the row, and repeating it is a no-op, so it's idempotent. The caption captures the structural rule: POST targets collections, the item methods target items, and crucially the server mints the new URI — a client shouldn't invent /bookings/42 and PUT to it hoping the server creates it, unless you've explicitly decided to support client-assigned IDs. Which methods are safe and which are idempotent isn't trivia — it's the contract your retry logic depends on, which is the next slide.");
}

/* --- idempotency matrix diagram --- */
{
  const s = S();
  addDiagramSlide(s, "METHODS", "The safe / idempotent matrix",
    "r05-idempotency-matrix",
    "Safe = no state change. Idempotent = repeating lands the same state. This grid is what your retry and caching logic rests on.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "This matrix is one of the most useful things to internalize, because it decides what your clients and proxies are allowed to do automatically. Two independent properties. Safe means the method doesn't change server state — only GET (and HEAD) are safe, which is why a cache or a crawler can issue them freely. Idempotent means issuing the request N times lands the same state as issuing it once. GET is both. PUT and DELETE are idempotent by the HTTP contract: replacing a booking with the same representation twice is the same as once, and cancelling an already-cancelled booking is a no-op. POST is neither — two POSTs make two bookings. PATCH is not inherently idempotent; whether it is depends on the change you express. The practical consequence is retries. Networks drop responses, so clients and gateways retry — and they're only safe to auto-retry idempotent methods. For the unsafe-but-must-retry case, POST a create, you make it safe to retry with an Idempotency-Key: the client sends a unique key, the server records it, and a replay returns the original result instead of creating a duplicate. Idempotency-Key is still an IETF draft, not a finished RFC, but it's widely implemented — it's how payment APIs avoid double-charging. Design to this grid and your failure handling stops being guesswork.");
}

/* ======================= DIVIDER 03 ======================= */
divider("03", "HTTP semantics done right",
  "Content negotiation, the status codes that carry meaning, and partial updates.",
  "The difference between an API that merely works and one that composes with the whole HTTP ecosystem — caches, proxies, generated clients — is whether it honours HTTP semantics. This section covers content negotiation, the status codes that actually carry meaning, machine-readable errors, and the two standard ways to express a partial update.");

/* --- content negotiation --- */
{
  const s = S();
  addCodeSlide(s, "SEMANTICS", "Content negotiation", "http",
    [
      "# Client states what it sends and what it will accept",
      "POST /bookings HTTP/1.1",
      "Content-Type: application/json",
      "Accept: application/json",
      "",
      "# Server can't read the request body's media type",
      "HTTP/1.1 415 Unsupported Media Type",
      "",
      "# Server can't produce anything the client will accept",
      "GET /bookings/{id} HTTP/1.1",
      "Accept: application/xml",
      "HTTP/1.1 406 Not Acceptable",
    ],
    "Content-Type describes the body you send; Accept lists what you'll take back. 415 and 406 are the two failure halves.");
  addNotes(s, "Content negotiation is two headers doing two different jobs, and conflating them is a common bug. Content-Type describes the representation in THIS message's body — when the client POSTs a booking, Content-Type: application/json says 'the bytes I'm sending are JSON'. Accept is the client's wish list for the response — 'send me back any of these media types'. Each has its own failure code, and using the right one matters because generated clients branch on them. If the server can't understand the request body's media type — say the client sent application/xml and the server only parses JSON — the correct answer is 415 Unsupported Media Type; the problem is with what was sent. If the server understands the request fine but can't produce anything on the client's Accept list — the client demanded application/xml but the server only emits JSON — that's 406 Not Acceptable; the problem is with what was asked for in return. 415 is about the body you sent; 406 is about the body you wanted. Our contract declares both on the relevant operations, so a client knows before runtime that these are the failure modes, and the content negotiation story connects directly to media-type versioning later, where the Accept header also carries the version.");
}

/* --- status codes + problem details --- */
{
  const s = S();
  addContentTitle(s, "SEMANTICS", "Status codes that carry meaning");
  addStatusTable(s, [
    { code: "201", name: "Created", purpose: "A booking was created; set Location to its URI, return the representation." },
    { code: "202", name: "Accepted", purpose: "Work started but not finished; Location points at an Operation to poll." },
    { code: "204", name: "No Content", purpose: "Success with nothing to return — e.g. after a soft-delete." },
    { code: "303", name: "See Other", purpose: "Async work finished; follow Location to the resulting resource." },
    { code: "409", name: "Conflict", purpose: "The request fights the resource's current state (illegal transition)." },
    { code: "415", name: "Unsupported Media Type", purpose: "Server can't read the request body's Content-Type." },
    { code: "422", name: "Unprocessable", purpose: "Syntactically valid but semantically wrong; pair with a Problem body." },
  ], { colW: [0.95, 3.05, 8.09], rowH: 0.55 });
  addCaption(s, "Errors return application/problem+json (RFC 9457): type, title, status, detail, instance — machine-readable, not a prose blob.");
  addNotes(s, "A status code is the first thing every client, cache, and proxy reads, so spend them deliberately. 201 Created is the create success — and it's incomplete without a Location header pointing at the new resource. 202 Accepted means 'I took the request but haven't finished' — the async pattern's opening move, with Location pointing at an Operation to poll. 204 No Content is success with an empty body, which is exactly right after a soft-delete. 303 See Other is how async work completes: it redirects the poller to the finished resource. 409 Conflict is the state-machine code — you asked to confirm a booking that's already cancelled, an illegal transition — and it's distinct from 400, which is a malformed request. 415 we just covered. 422 Unprocessable is for a request that parses fine but is semantically wrong, like cargo weight of zero. The caption is the part teams skip and regret: errors should not be a prose string or an ad-hoc JSON blob. Use RFC 9457 Problem Details — application/problem+json with type, title, status, detail, and instance. It's a finished standard, it's machine-readable, and it means every error across your API has the same shape a client can program against. Our contract returns Problem on every error response.");
}

/* --- partial updates --- */
{
  const s = S();
  addCodeSlide(s, "SEMANTICS", "Partial updates: JSON Patch vs Merge Patch", "json",
    [
      "// JSON Patch — RFC 6902 · application/json-patch+json",
      "// An ordered list of operations; precise, can test/move/remove.",
      "[",
      "  { \"op\": \"replace\", \"path\": \"/requestedPickup\", \"value\": \"2026-11-02\" },",
      "  { \"op\": \"add\", \"path\": \"/cargo/-\", \"value\": { \"description\": \"pallets\", \"type\": \"GENERAL\" } }",
      "]",
      "",
      "// JSON Merge Patch — RFC 7396 · application/merge-patch+json",
      "// Looks like the resource; null means delete. Simpler, less precise.",
      "{ \"requestedPickup\": \"2026-11-02\", \"quote\": null }",
    ],
    "Patch targets an item (PATCH /bookings/{id}); the media type tells the server which document format you sent.");
  addNotes(s, "There are two standard ways to express 'change part of this resource', and the media type is how the server tells them apart. JSON Patch — RFC 6902, media type application/json-patch+json — is an ordered array of operations: replace this path, add to that array, remove, copy, move, and test (which asserts a value so you can do optimistic concurrency). It's precise and powerful; the trade-off is that it doesn't look anything like your resource, so it's wordier to produce and read. JSON Merge Patch — RFC 7396, media type application/merge-patch+json — takes the opposite approach: the patch document looks like the resource, you include only the fields you want to change, and setting a field to null means delete it. It's much simpler to write, which is why it's popular, but it has a sharp edge: because null means 'remove', merge patch can't distinguish 'set this to null' from 'delete this', so it's unsuitable when your resource legitimately holds null values. Both are PATCH on the item URI — PATCH /bookings/{id} — and our contract declares both request media types on that operation, so the client picks the format by setting Content-Type and the server dispatches accordingly. Rule of thumb: reach for Merge Patch for simple field edits, JSON Patch when you need ordered operations or test-based concurrency.");
}

/* ======================= DIVIDER 04 ======================= */
divider("04", "Collections at scale",
  "Reading large collections safely: filtering, projection, pagination — and sub-resources.",
  "A collection that returns everything is a denial-of-service waiting to happen. This section is about reading large collections without hurting the server or the client: filtering on the server, projecting to just the fields you need, and the three pagination strategies with their trade-offs — then when to nest a sub-resource and when not to.");

/* --- pagination diagram --- */
{
  const s = S();
  addDiagramSlide(s, "COLLECTIONS", "Filtering, projection & pagination",
    "r08-pagination",
    "Offset is simple but drifts; keyset is consistent but couples to the sort; seek decouples with an opaque cursor.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "Never expose an unbounded collection. Three things keep reads safe: filtering (return a subset — by status, by origin), projection (return fewer fields via a fields= parameter — sparse fieldsets), and pagination (return one page at a time). The pagination choice is the interesting one, and there are three strategies on a spectrum. Offset pagination — limit and offset — is the SQL-native one everybody reaches for first. It's dead simple, but it has two real problems: it gets slow at depth because the database still scans and discards the skipped rows, and it suffers page drift — if rows are inserted while a user pages, items shift and they see duplicates or gaps. Keyset pagination fixes both by paging on the value of the last row's sort key — 'give me the next 20 created before this timestamp' — so it's consistent under inserts and stays fast at any depth, but it couples the client to the sort key and filters. Seek pagination extends keyset with an opaque cursor the server hands back: the client doesn't know or care what's inside it, which decouples paging from the filter and sort logic entirely — at the cost of more backend work to encode and validate the cursor. Our contract uses keyset-with-cursor. Whatever you choose, always do the three things in the side panel: cap the limit as a DoS guard, ship page metadata (count, nextCursor), and give every parameter a sane default.");
}

/* --- filtering/projection code --- */
{
  const s = S();
  addCodeSlide(s, "COLLECTIONS", "Filtering, projection & the page shape", "http · json",
    [
      "# Filter on the server, project to fewer fields, cap the page",
      "GET /bookings?status=PENDING&origin=USNYC&limit=20&fields=id,status,origin",
      "",
      "# The response carries the items AND the paging metadata",
      "{",
      "  \"items\": [ { \"id\": \"bkg_01H...\", \"status\": \"PENDING\", ... } ],",
      "  \"page\":  { \"limit\": 20, \"count\": 20, \"nextCursor\": \"eyJrIjoi...\" },",
      "  \"_links\": { \"next\": { \"href\": \"/bookings?cursor=eyJrIjoi...\" } }",
      "}",
    ],
    "limit is capped (max 100, default 20) as a DoS guard; nextCursor is null on the last page.");
  addNotes(s, "Here's the collection contract in practice. The request combines all three techniques: status and origin filter server-side so the client isn't shipped rows it will throw away; limit caps the page; and fields= asks for a sparse projection — just id, status, and origin — which cuts payload size when a client only needs a summary view. The response shape is the part worth copying. It's an object, not a bare array, with three parts: items is the page of bookings; page is the metadata — the limit that was applied, the count actually returned, and nextCursor, the opaque keyset cursor for the following page, which is null when you've reached the end; and _links carries a ready-made next link so a client can follow pagination without constructing URLs itself, which is HATEOAS applied to collections. Two guard rails from the contract: limit has a maximum of 100 and a default of 20, so a client can't ask for a million rows and a client that forgets to ask still gets a sane page — that cap is a genuine denial-of-service defence, not a nicety. And nextCursor being null is the unambiguous end-of-collection signal, so clients don't have to guess whether an empty page means 'done' or 'try again'.");
}

/* --- sub-resources --- */
{
  const s = S();
  addContentTitle(s, "COLLECTIONS", "Sub-resources: nest with intent");
  addTwoColBullets(s,
    [
      { text: "Nest when…", options: { bold: true, bullet: false } },
      "The URL expresses genuine ownership (/bookings/{id}/cargo).",
      "The child has no identity outside its parent.",
      "Relative context matters (a cargo item within its booking).",
    ],
    [
      { text: "Don't nest when…", options: { bold: true, bullet: false } },
      "It creates obtuse, deeply nested URLs.",
      "It makes redundant endpoints that return the same thing.",
      "Multiple paths to one representation break caching.",
    ],
    { fontSize: 15 });
  addCaption(s, "A nested URL conveys hierarchy — but the data model need not be hierarchical. Past a level or two, prefer links over nesting.");
  addNotes(s, "Sub-resources — nesting one resource under another — are useful and overused in equal measure, so nest with intent. The case for nesting: the URL conveys ownership, like /bookings/{id}/cargo, where a cargo item genuinely belongs to a booking and has little meaning outside it; the relative context is part of the identity, the way a house number only means something with its street. But note the appearance-versus-reality point — a nested URL suggests hierarchy, but your underlying data model doesn't have to be hierarchical; GitHub nests repositories under users in the URL even though the data model is a flat graph. The case against: nesting past a level or two produces obtuse URLs nobody wants to construct; it tempts you into redundant endpoints where the same cargo item is reachable at two different paths; and multiple URIs for one representation is actively harmful to caching, because a cache can't tell they're the same thing and you fragment your hit rate — and it quietly violates the uniform-interface principle. The guidance: nest one level where it reads as ownership, and past that, use links — have the booking carry a link to its cargo collection rather than forcing a deep path. That keeps each resource reachable by exactly one canonical URI, which is what caches and clients both want.");
}

/* ======================= DIVIDER 05 ======================= */
divider("05", "Asynchronous work & jobs",
  "When the work outlasts the request: 202 → poll → 303, and rerunnable jobs.",
  "Some work can't finish inside one request/response cycle — confirmation runs routing and capacity checks that take seconds to minutes. This section is the asynchronous operation pattern end to end, and its cousin, the rerunnable job, where the server owns a repeatable unit of work rather than the client re-specifying it each time.");

/* --- async diagram --- */
{
  const s = S();
  addDiagramSlide(s, "ASYNC", "Asynchronous & long-running operations",
    "r10-async-flow",
    "Accept the request with 202, hand back an Operation to poll, then 303 to the result when it's done.",
    { x: 1.60, y: 1.70, w: 10.13, h: 4.55 });
  addNotes(s, "This is the pattern the decision framework pointed us at, drawn out in full. The client POSTs to the confirmation sub-resource. The server doesn't block — it accepts the work and immediately returns 202 Accepted with a Location header pointing at an Operation resource. That Operation is a first-class resource with its own URI and lifecycle: the client polls it with GET, and while it's running the server returns 200 with a status of RUNNING — and, usefully, the Operation can carry a cancel link while it's in flight, so the client has a way to abort. When the work finishes, the poll returns 303 See Other with a Location header pointing at the result — the now-confirmed booking. The client follows that redirect with a final GET and sees status CONFIRMED. Why this shape rather than, say, a WebSocket or long-poll? Because it stays entirely within REST and the existing HTTP infrastructure — every proxy, every client library already handles 202, polling, and 303 — and because the Operation resource gives you somewhere to hang status, progress, errors, and a cancel affordance. The one thing to get right operationally is the poll interval: respect Retry-After if the server sends it, and back off, so a thousand clients polling don't become the load you were trying to avoid.");
}

/* --- async contract code --- */
{
  const s = S();
  addCodeSlide(s, "ASYNC", "The 202 → poll → 303 contract", "http",
    [
      "# 1 · Start the work — accepted, not finished",
      "POST /bookings/bkg_01H.../confirmation",
      "HTTP/1.1 202 Accepted",
      "Location: /operations/op_01H...",
      "",
      "# 2 · Poll the Operation resource",
      "GET /operations/op_01H...",
      "HTTP/1.1 200 OK   { \"status\": \"RUNNING\" }",
      "",
      "# 3 · Done — redirect to the result",
      "HTTP/1.1 303 See Other",
      "Location: /bookings/bkg_01H...",
    ],
    "The Operation is a real resource with status PENDING/RUNNING/SUCCEEDED/FAILED — and an error (Problem) on failure.");
  addNotes(s, "The same flow as the wire exchange, because this is what you actually implement. Step one: POST to the confirmation sub-resource returns 202 Accepted with Location pointing at /operations/op_... — note the Operation gets its own opaque id, same discipline as bookings. Step two: the client GETs that Operation and gets 200 with a status field; the Operation's status is a small state machine of its own — PENDING, RUNNING, SUCCEEDED, FAILED — so the client can distinguish 'still working' from 'failed' without ambiguity. Step three: on success the Operation responds 303 See Other with Location pointing at the resulting booking, and the client follows it. Two details that make this production-grade. First, failure: when the Operation fails, it doesn't just flip to FAILED — it carries an error field containing a Problem document, the same RFC 9457 shape we use everywhere, so the client learns why. Second, the Operation resource is durable; it outlives the request that created it, which is what lets a client that crashed and restarted come back and ask 'did my confirmation finish?' simply by GETting the Operation URI it saved. That durability is the whole point — the state lives on the server in a resource, not in a connection that can drop. How each stack runs the work off the request thread is in the implementation decks.");
}

/* --- rerunnable jobs --- */
{
  const s = S();
  addContentTitle(s, "ASYNC", "Rerunnable jobs: separate configure from execute");
  addBullets(s, [
    "Some work runs repeatedly and shouldn't re-specify all its configuration on every invocation.",
    "Split the concern: a Job resource holds the configuration; an execution runs it and produces an Operation.",
    "Execution can be on-demand (POST to run) or on a server-owned schedule — the client doesn't hold the clock.",
    "In our domain: a reconcile Job re-checks manifests against bookings, run nightly or on demand.",
    "The alternative — one fat custom method carrying all config every time — couples permission-to-configure with permission-to-run.",
  ], { fontSize: 16 });
  addNotes(s, "Rerunnable jobs are the async pattern's cousin, for work that recurs. The motivating observation: some functionality runs over and over, and making the client re-send all of its configuration on every call is both wasteful and a security smell. So split it into two resources. A Job resource holds the configuration — what to reconcile, with what parameters — and it persists. Executing the job is a separate act that produces an Operation, exactly the long-running-operation resource from the last pattern, so you get status and polling for free. The execution can be triggered two ways: on demand, by POSTing to run the job, or on a schedule the server owns — and that last point matters, because the client shouldn't have to stay running to fire a nightly task; the server holds the clock. In our domain the concrete example is a reconcile job that re-checks consolidated manifests against the bookings they claim to cover, which you'd run nightly and also on demand after a correction. The design payoff is in the last bullet: by separating the Job (configure) from its execution (run), you can grant different permissions to each — someone may be allowed to run a reconcile without being allowed to change what it reconciles. Fold both into one fat custom method that carries all the config every time, and you've welded those two permissions together and lost that control.");
}

/* ======================= DIVIDER 06 ======================= */
divider("06", "Evolution & lifecycle",
  "Letting a resource advertise its own next steps, deleting responsibly, and versioning without breakage.",
  "A real API lives for years and changes constantly. This section is about change: HATEOAS so a resource advertises its own legal next steps rather than baking them into clients; soft deletion with a lawful purge path; and the four versioning strategies with their very different caching consequences.");

/* --- HATEOAS diagram --- */
{
  const s = S();
  addDiagramSlide(s, "LIFECYCLE", "HATEOAS: the response drives the state machine",
    "r12-hateoas-fsm",
    "The links a booking carries are exactly the transitions legal from its current state — the client follows, never hard-codes.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "HATEOAS — Hypermedia As The Engine Of Application State — is the REST constraint everyone skips and then reinvents badly. The idea: a response doesn't just carry data, it carries the links to the operations that are legal right now, and the client navigates by following them rather than by hard-coding URL templates and business rules. The clean way to see it is as a finite state machine, which maps perfectly onto our booking lifecycle. A booking moves PENDING to CONFIRMED to IN_TRANSIT to DELIVERED, and from the early states it can also be CANCELLED. HATEOAS says the _links in each response are exactly the transitions legal from that booking's current state. A PENDING booking comes back with a confirm link and a cancel link, because those are its legal moves. An IN_TRANSIT booking offers neither — you can't confirm what's already confirmed, and the cancel window has closed — so those links simply aren't there. A DELIVERED booking is terminal and offers only self. The benefit is that the client stops encoding the state machine. It doesn't need to know 'you can only cancel while pending' — it just renders the links the server sent and disables the rest, and if the rules change, the server changes which links it emits and every client follows along without a redeploy. The server owns the state machine; the client owns rendering what it's handed.");
}

/* --- HATEOAS code --- */
{
  const s = S();
  addCodeSlide(s, "LIFECYCLE", "State-dependent _links on a Booking", "json",
    [
      "// GET /bookings/bkg_01H...  — a PENDING booking",
      "{",
      "  \"id\": \"bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4\",",
      "  \"status\": \"PENDING\",",
      "  \"origin\": { \"unLocode\": \"USNYC\" },",
      "  \"destination\": { \"unLocode\": \"NLRTM\" },",
      "  \"_links\": {",
      "    \"self\":    { \"href\": \"/bookings/bkg_01H...\" },",
      "    \"confirm\": { \"href\": \"/bookings/bkg_01H.../confirmation\", \"method\": \"POST\" },",
      "    \"cancel\":  { \"href\": \"/bookings/bkg_01H...\", \"method\": \"DELETE\" }",
      "  }",
      "}",
    ],
    "Once DELIVERED, _links carries only self — the confirm and cancel affordances vanish because they're no longer legal.");
  addNotes(s, "Here's what the client actually receives. This is a PENDING booking, and the interesting part is the _links object. Each link has an href and, where it isn't a plain GET, a method — so confirm is a POST to the confirmation sub-resource, and cancel is a DELETE on the booking itself. self is the canonical URI of the resource, which every resource should carry. The relation name — confirm, cancel, self — is the contract; it's a stable string the client keys on, following RFC 8288 web-linking conventions. The behaviour that makes this HATEOAS rather than decoration: when you GET this same booking after it's been delivered, confirm and cancel are simply gone from _links, because they're no longer legal transitions, and self is all that remains. A well-built client renders buttons from this map — it shows Confirm and Cancel because the links are present, and when they disappear it stops offering them, with zero client-side knowledge of the rule 'you can only cancel while pending'. That rule lives in exactly one place, the server, and it's expressed by which links get emitted. There's no universal standard for the link format — HAL, JSON:API, and plain _links all exist — so the site picks one simple shape and holds it consistently across every resource, which is the thing that actually matters.");
}

/* --- soft deletion --- */
{
  const s = S();
  addContentTitle(s, "LIFECYCLE", "Soft deletion & GDPR purge");
  addTwoColBullets(s,
    [
      { text: "Why soft-delete", options: { bold: true, bullet: false } },
      "Recover from accidental deletes; support undelete.",
      "History, audit, and referential integrity.",
      "A long-running op may still need the 'deleted' row.",
      "DELETE flips status to CANCELLED; hidden from default queries.",
    ],
    [
      { text: "But GDPR still applies", options: { bold: true, bullet: false } },
      "Regulation can require true erasure, not just hiding.",
      "Keep a separate purge path for lawful hard-deletion.",
      "Purge is auditable and distinct from everyday cancel.",
      "Soft-deleted rows must stay out of normal responses.",
    ],
    { fontSize: 15 });
  addCaption(s, "Soft delete is the default; purge is the exception. Model both — don't let 'we never really delete' quietly become a compliance breach.");
  addNotes(s, "Deletion is rarely as simple as removing a row, so model two distinct operations. Soft deletion is the default, and there are good reasons: it lets you recover from accidental deletes and support undelete; it preserves history and audit trails; it protects referential integrity so you don't cascade-delete half the database; and it handles the subtle case where a long-running operation still needs data for a resource a user has 'deleted'. In our domain, DELETE on a booking doesn't erase it — it flips status to CANCELLED and hides it from default queries, which is why DELETE is idempotent and returns 204. The complication, in the right column, is that soft deletion alone can put you on the wrong side of the law. GDPR's right to erasure can require that data actually be gone, not merely marked hidden — a row you've flagged CANCELLED but kept is still personal data you're processing. So you need a separate, deliberate purge path for lawful hard-deletion: distinct from everyday cancel, auditable, and ideally restricted to a narrow set of operators. The caption is the trap to avoid: 'we never really delete anything' is a fine engineering default right up until it becomes a compliance violation. Model soft delete as the common case and purge as the governed exception — and make sure soft-deleted rows genuinely stay out of normal query results, because a 'deleted' booking showing up in a list is both a bug and, potentially, a breach.");
}

/* --- versioning --- */
{
  const s = S();
  addContentTitle(s, "LIFECYCLE", "Versioning: four strategies, different caching");
  addStatusTable(s, [
    { code: "URI", name: "/v2/bookings/{id}", purpose: "Simplest and most visible; cache-friendly. Every link must carry the version." },
    { code: "Query", name: "/bookings/{id}?version=2", purpose: "Same URI base; some proxies won't cache query-string responses." },
    { code: "Header", name: "Api-Version: 2", purpose: "Clean URLs; needs custom header logic and complicates HATEOAS links." },
    { code: "Media type", name: "Accept: …v2+json", purpose: "Purest; composes with content negotiation and HATEOAS. Caching needs Vary." },
  ], { colW: [1.90, 3.70, 6.49], rowH: 0.70 });
  addCaption(s, "Additive changes (new optional fields) need no new version if clients ignore unknown fields. Removing/renaming is breaking — then choose.");
  addNotes(s, "Most APIs eventually change in ways that break someone, and there are four places to put the version — each with a different caching story, which is the axis people forget. URI versioning — /v2/bookings — is the simplest and most visible, it's cache-friendly because the version is part of the key, and tooling loves it; the cost is that every link you emit has to carry the version, which complicates HATEOAS. Query-string versioning — ?version=2 — keeps the same base URI, which is semantically nice, but some older proxies and browsers won't cache responses to URLs with query strings, so you can quietly lose caching. Header versioning — a custom Api-Version header — gives you clean URLs, but it needs custom logic to read the header and it complicates HATEOAS because your links now have to describe a header too. Media-type versioning — Accept: application/vnd.shipping.v2+json — is arguably the purest: it rides the content-negotiation machinery we already discussed and composes naturally with HATEOAS, which can advertise the media type in links; the caveat is caches need a Vary: Accept header to avoid serving the wrong version. The caption is the liberating part: a lot of change doesn't need a new version at all. Adding a new optional field is non-breaking as long as clients ignore unknown fields — which well-built clients do. You only need a versioning strategy for genuinely breaking changes: removing a field, renaming one, or changing a relationship. Pick the strategy that fits your caching and your clients, then hold it. The site's examples use media-type versioning; the implementation decks show how each stack wires it.");
}

/* ======================= DIVIDER 07 ======================= */
divider("07", "Large payloads & streaming",
  "Moving manifests in chunks, and pushing data as it's produced.",
  "Not every resource is a few hundred bytes of JSON. A cargo manifest can be tens of megabytes, and some data is best pushed as it's produced rather than returned in one response. This section covers Range requests for large binaries and the streaming options the site adds.");

/* --- Range diagram --- */
{
  const s = S();
  addDiagramSlide(s, "PAYLOADS", "Large binary resources & Range requests",
    "r15-range",
    "HEAD to learn size and range support, then GET byte ranges; the server answers 206 Partial Content with Content-Range.",
    { x: 1.60, y: 1.70, w: 10.13, h: 4.55 });
  addNotes(s, "Large binary resources — a cargo manifest PDF that can run to many megabytes — break the one-request-one-response assumption, especially over flaky connections. The pattern is built from standard HTTP range machinery. First, the client issues a HEAD request: HEAD returns all the headers a GET would but no body, so the client learns the manifest's size from Content-Length and, crucially, learns the server supports ranges from Accept-Ranges: bytes — without downloading a single byte of a file it may not be able to handle whole. Then the client fetches in chunks with a Range header: Range: bytes=0-1048575 asks for the first megabyte. The server answers not 200 but 206 Partial Content, includes a Content-Range header stating exactly which slice this is and the total size — bytes 0 through 1048575 of 5242880 — and sends just that megabyte. The client repeats with the next range to resume. This is exactly how download managers and video scrubbing work, and it buys you three things: resumability (a dropped connection costs you one chunk, not the whole file), the ability to fetch only the part you need, and backpressure-friendly transfer. One edge to handle: if the client asks for a range past the end of the resource, the correct answer is 416 Range Not Satisfiable, which our contract declares. HEAD plus Range plus 206 is entirely standard HTTP — no custom chunking protocol required.");
}

/* --- streaming --- */
{
  const s = S();
  addContentTitle(s, "PAYLOADS", "Streaming: push data as it's produced");
  addStatusTable(s, [
    { code: "SSE", name: "Server-Sent Events", purpose: "text/event-stream; one-way server→client, auto-reconnect, event ids. Great for live booking status." },
    { code: "NDJSON", name: "Newline-delimited JSON", purpose: "application/x-ndjson; one JSON object per line — stream a large result set without buffering it all." },
    { code: "Chunked", name: "Transfer-Encoding: chunked", purpose: "HTTP/1.1 framing underneath; send a response whose length isn't known up front." },
  ], { colW: [1.50, 3.40, 7.19], rowH: 0.78 });
  addCaption(s, "Streaming stays within REST's request/response for a single long response; a bidirectional, session-shaped need is the WebSockets branch instead.");
  addNotes(s, "Streaming is about a different shape than Range: not fetching a big static file in pieces, but sending data as it's produced. Three options, all plain HTTP. Server-Sent Events — media type text/event-stream — is a one-way server-to-client channel with real ergonomics built in: automatic reconnection, event IDs so a client can resume from where it dropped, and named event types. It's ideal for pushing live booking status updates to a dashboard, and it's dramatically simpler than a WebSocket when you only need one direction. NDJSON — newline-delimited JSON, application/x-ndjson — is the streaming answer for large result sets: instead of buffering a hundred thousand bookings into one giant array the server has to hold in memory and the client has to parse all at once, you emit one JSON object per line and both sides process incrementally. Chunked transfer encoding is the HTTP/1.1 framing underneath both of these — it's how you send a response whose total length you don't know when you start writing it. The caption draws the boundary back to the decision framework: all three of these are still request/response — one request, one long response — so they stay firmly within REST. The moment you genuinely need bidirectional, long-lived, session-shaped communication, you've crossed into the WebSockets branch, which is a different sibling in this series. Match the mechanism to the interaction shape. The reactive and async implementations of these streams are in the Quarkus and Python decks.");
}

/* ======================= DIVIDER 08 ======================= */
divider("08", "Multi-protocol contracts",
  "One schema across four contract languages, so the synchronous and asynchronous promises never drift.",
  "The governance story that ties the series together: the same booking service that answers REST synchronously also announces state changes asynchronously, and that second promise needs a contract too. This section shows how one shared schema keeps OpenAPI, AsyncAPI, CloudEvents, and Arazzo from drifting apart.");

/* --- multi-protocol diagram --- */
{
  const s = S();
  addDiagramSlide(s, "CONTRACTS", "Multi-protocol contracts around one schema",
    "r21-multiprotocol",
    "OpenAPI, AsyncAPI, CloudEvents, and Arazzo each $ref the same JSON Schema — one definition, many protocols, no drift.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "This answers a real production problem: 'the contract' was never just the OpenAPI document. The same booking service that answers POST /bookings synchronously also tells the rest of the organization, asynchronously, that a booking changed state — and that second promise drifts the same way an undocumented REST response does unless you write it down too. Four contract languages, each answering a different question. OpenAPI: what does a client send and get back, right now, on this connection — the synchronous surface. AsyncAPI: what gets published, to which channel, in what shape, independent of who's listening — our booking lifecycle events on a Kafka channel. CloudEvents: given that something is published as an event, what does the envelope around it look like — specversion, id, source, type, subject, time, and the data slot. Arazzo: in what order do several already-contracted operations get called to achieve one business outcome — the book-then-confirm-then-poll workflow. The spine that makes this one system rather than four is in the center: all four $ref the same JSON Schema file. Booking and BookingEvent share the exact same Location and Money definitions, declared once. So a field rename propagates to the synchronous and asynchronous contracts together, and CI greps both documents to prove they still reference the shared file. Underneath, the governance tier: artifacts are published to Apicurio Registry — the xRegistry touchpoint — and catalogued in OpenMetadata, so the contracts are discoverable, not just committed.");
}

/* --- CloudEvents envelope code --- */
{
  const s = S();
  addCodeSlide(s, "CONTRACTS", "One schema, both sides: the CloudEvents envelope", "json",
    [
      "// Published to shipping.bookings.lifecycle when a booking confirms",
      "{",
      "  \"specversion\": \"1.0\",",
      "  \"id\": \"evt_01H...\",",
      "  \"source\": \"/shipping/bookings\",",
      "  \"type\": \"dev.patterncatalyst.shipping.booking.confirmed\",",
      "  \"subject\": \"bkg_01H...\",",
      "  \"time\": \"2026-10-11T14:30:00Z\",",
      "  \"datacontenttype\": \"application/json\",",
      "  \"data\": {                         // data = $defs/BookingEvent — same schema",
      "    \"bookingId\": \"bkg_01H...\", \"status\": \"CONFIRMED\",",
      "    \"previousStatus\": \"PENDING\", \"origin\": { \"unLocode\": \"USNYC\" }",
      "  }",
      "}",
    ],
    "data is the shared BookingEvent type; its origin/destination are the same $defs/Location the REST Booking uses.");
  addNotes(s, "This is the shared-schema story made concrete. When a booking confirms, the service publishes a CloudEvents-enveloped message to the shipping.bookings.lifecycle channel. The envelope is the fixed CloudEvents context: specversion 1.0, a unique id, a source URI naming where it came from, a type in reverse-DNS form that names the event, subject set to the booking's id so a consumer knows which resource it's about, time, and datacontenttype. The payload inside data is the key move: it's the BookingEvent type from the shared JSON Schema, and BookingEvent deliberately carries fewer fields than Booking — bookingId, the new status, the previousStatus it transitioned from, origin, destination, occurredAt — because an event announcing a change doesn't need the full cargo manifest; a subscriber that wants more can GET the booking. But — and this is the whole point — BookingEvent.origin references the exact same $defs/Location that Booking.origin uses in the REST contract. One Location definition, referenced from both the synchronous and the asynchronous side, so they cannot drift. CI greps both documents for the shared schema reference and fails if either stops using it, so 'one schema, two protocol contracts' is a checked claim, not a comment. How each stack actually publishes to Kafka — and swallows a publish failure so it never becomes a 5xx on the REST call — is in the implementation decks.");
}

/* ======================= DIVIDER 09 ======================= */
divider("09", "Testing & running it",
  "Proving both stacks honour the contract, and running the same artifact from laptop to OpenShift.",
  "Two concepts that make the whole thing credible: a testing strategy that proves an implementation honours the contract at every level, and a deployment story where the same container image runs unchanged from a laptop to a cluster to OpenShift. No managed cloud on the primary path.");

/* --- testing --- */
{
  const s = S();
  addContentTitle(s, "TESTING", "The test pyramid");
  addStatusTable(s, [
    { code: "Contract", name: "schema + lint", purpose: "Lint OpenAPI & AsyncAPI; validate each stack against the shared schema — drift fails CI." },
    { code: "Integration", name: "real deps", purpose: "Exercise endpoints against a real Postgres & Kafka (containerized deps), not mocks." },
    { code: "API/E2E", name: "Newman", purpose: "Run shared collections against the live service; assert status codes, headers, and bodies." },
    { code: "Load", name: "throughput", purpose: "Confirm the pagination caps and the async flow hold under concurrency." },
  ], { colW: [1.90, 2.60, 7.59], rowH: 0.78 });
  addCaption(s, "Every layer checks the same contract from a different angle — the point is that two implementations stay interchangeable.");
  addNotes(s, "Testing is structured as a pyramid where every layer checks the same contract from a different angle — because the whole promise of this series is that two implementations stay interchangeable, and that only holds if it's tested. At the base, contract tests: lint the OpenAPI and AsyncAPI documents for correctness and style, and validate each stack against the shared JSON Schema, so any drift between code and contract fails the build before anything runs. Next, integration tests against real dependencies, not mocks: exercise the endpoints against a genuine Postgres and a genuine Kafka in containers, so you catch the things mocks hide — transaction behaviour, serialization, real error codes. Above that, API or end-to-end tests: shared collections run headless by Newman hit the actually-running service and assert the full HTTP contract — status codes, headers like Location and Content-Range, and body shapes — which is the closest thing to what a real client sees, and because the collection is shared, the exact same assertions run against both stacks. A load pass on top confirms the properties that only appear under concurrency hold up: the pagination limit cap actually caps, the async 202/poll/303 flow doesn't fall over. The shape of the pyramid is the usual advice — many fast contract and unit checks, fewer integration, fewer still end-to-end — but the framing here is specific: each layer is a different lens on one contract. The stack-specific test tooling — the in-process test harnesses — is shown in the implementation decks.");
}

/* --- deployment tiers diagram --- */
{
  const s = S();
  addDiagramSlide(s, "RUNNING IT", "One artifact across three tiers",
    "r25-deployment-tiers",
    "The same container image and the same contract: Docker/Podman Compose → minikube → OpenShift Local. No managed cloud.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "The running story is deliberately boring, which is the point — the same artifact promotes across three tiers with nothing rebuilt. Tier one is local: Docker or Podman Compose brings up the service alongside Postgres and Kafka, plus the LGTM observability stack so you get distributed tracing from the first run — you can watch a single booking request flow through the service and into the event publish. Tier two is Kubernetes on minikube: the same container image, now described by Deployments, Services, and an Ingress — standard Kubernetes primitives, single-node, on your workstation. Tier three is OpenShift Local, CRC: again the same image, now with Routes instead of Ingress, BuildConfig for in-cluster builds, and the restricted-v2 security context constraint, which is the realistic production posture — an image that runs as an arbitrary non-root user with no special privileges. The arrows say 'promote' because that's literally the motion: the image you built once moves up the tiers; only the surrounding Kubernetes and OpenShift manifests change, never the application. This reflects a house rule the series holds throughout: examples run on plain infrastructure — Docker Engine on a Fedora or RHEL workstation, plain minikube, OpenShift Local — and there is no managed cloud service on the primary path. That keeps the whole thing reproducible on a laptop and portable to any conformant cluster, rather than quietly depending on one vendor's hosted database or queue.");
}

/* ======================= DIVIDER 10 ======================= */
divider("10", "The complete project & wrap-up",
  "The whole arc in one service — and where to go deeper.",
  "Everything we've covered isn't a bag of isolated tricks — it composes into one coherent service. This closing section shows the complete project and sends you to the contract-first material, the site chapters, and the two implementation decks to go deeper.");

/* --- complete project --- */
{
  const s = S();
  addContentTitle(s, "COMPLETE PROJECT", "The whole arc, one service");
  addBullets(s, [
    "One OpenAPI contract; Booking, Cargo, Operation, Manifest modelled as resources.",
    "Methods and status codes by the book; retries safe by the idempotency matrix.",
    "Keyset pagination, Range downloads, and streaming for the collection and the manifest.",
    "Async confirmation (202 → poll → 303) plus a CloudEvents stream off the same booking row.",
    "HATEOAS-driven lifecycle, soft deletion with purge, and a versioning strategy — the patterns, ready to implement in either stack.",
  ], { fontSize: 16 });
  addNotes(s, "The complete project is where every pattern stops being a slide and becomes one running system, so it's worth seeing them assembled. One OpenAPI contract defines the surface, and the domain is modelled as resources — Booking as the aggregate root, Cargo as a sub-resource, Operation for long-running work, Manifest as the large binary. The methods and status codes follow the semantics we covered, and because the design respects the safe/idempotent matrix, the client and gateway retries are safe by construction rather than by luck. Reading the collection uses keyset pagination with a capped limit; fetching the manifest uses HEAD plus Range plus 206; live status uses streaming. Confirmation is the async operation — 202, poll the Operation, 303 to the result — and the very same state transition emits a CloudEvents message onto the lifecycle stream off the same booking row, with the payload typed by the shared schema so the two can't disagree. The lifecycle is HATEOAS-driven, so clients follow links instead of hard-coding the state machine; deletion is soft with a governed purge path for GDPR; and there's a deliberate versioning strategy for the day a breaking change arrives. That's the whole 100-level arc as one design. On the site it ships twice — Quarkus and Python/FastAPI — validated against the one contract in CI, and those two builds are exactly what the companion implementation decks walk through.");
}

/* --- OpenAPI wrap --- */
{
  const s = S();
  addContentTitle(s, "WRAP-UP", "Contract-first, and where to go deeper");
  addBullets(s, [
    "OpenAPI is design up front: it promotes contract-first and interoperability, and both stacks generate docs from it.",
    "Define each type once in shared schema; let every protocol and both stacks reference it.",
    "Cite the standards: Problem Details RFC 9457, JSON Patch RFC 6902, Merge Patch RFC 7396, web linking RFC 8288.",
    "Deprecation (RFC 9745) and Sunset (RFC 8594) are RFCs; Idempotency-Key and RateLimit-* are still IETF drafts.",
    "Go deeper: the site chapters, the contracts/ directory, and the Quarkus and Python/FastAPI implementation decks.",
  ], { fontSize: 16 });
  addNotes(s, "To close the technical arc, a word on OpenAPI as the organizing idea and a pointer to the standards. OpenAPI pays off because it forces design up front — it promotes contract-first thinking and interoperability, and both stacks generate their interactive docs straight from the contract, so the documentation can't lie about the implementation. The discipline that makes it scale is the one we kept returning to: define each type exactly once in shared schema, and let every protocol — OpenAPI, AsyncAPI, CloudEvents, Arazzo — and both stacks reference it. On standards, be precise, because credibility lives in the details: Problem Details is RFC 9457, JSON Patch is RFC 6902, JSON Merge Patch is RFC 7396, and web linking for your HATEOAS relations is RFC 8288 — all finished RFCs you can cite. Two more worth knowing the status of: Deprecation is now RFC 9745 and Sunset is RFC 8594, both real RFCs for signalling an endpoint's end of life; whereas Idempotency-Key and the RateLimit-* headers are still IETF Internet-Drafts, widely implemented but not yet ratified — so present them as drafts, not standards. From here, go deeper in three places: the site chapters expand every one of these topics, the contracts directory holds the real OpenAPI, AsyncAPI, CloudEvents, and Arazzo documents, and the two implementation decks show the same patterns built in Quarkus and in Python/FastAPI.");
}

/* --- Q&A / thank you --- */
{
  const s = S();
  addContentTitle(s, "THANK YOU", "Q&A");
  addBullets(s, [
    "Questions on any pattern — resources, methods, async, HATEOAS, versioning, multi-protocol?",
    "The full site, contracts, and both-stack examples: github.com/patterncatalyst/api-patterns-and-practices-rest",
  ], { fontSize: 17 });
  addCaption(s, "Red Hat is the world's leading provider of enterprise open source software solutions — trusted by the Fortune 500 for award-winning support, training, and consulting.");
  addNotes(s, "Thank you. That's the whole 100-level arc: start from what REST actually is and a framework for choosing it on purpose; design resources as nouns pinned to one contract; get the method semantics, status codes, and partial updates right; read large collections safely; model asynchronous work and rerunnable jobs; let resources drive their own lifecycle through HATEOAS; delete responsibly and version without breakage; move large payloads and stream; and tie the synchronous and asynchronous worlds together with one shared schema across four contract languages. Everything here is the pattern and the reasoning — stack-agnostic by design. When you want the how, the two companion decks take it from here: one builds every one of these in Quarkus, the other in Python/FastAPI, against the same contract and the same shipping domain. I'm happy to take questions on any of it. The complete site, the contracts directory, and the runnable both-stack examples are all public on the Pattern Catalyst GitHub organization. And the standard Red Hat close: Red Hat is the world's leading provider of enterprise open source software solutions, trusted by the Fortune 500 for award-winning support, training, and consulting services.");
}

pres.writeFile({ fileName: OUT })
  .then((p) => console.log("WROTE", p, "slides:", pageNum))
  .catch((e) => { console.error(e); process.exit(1); });
