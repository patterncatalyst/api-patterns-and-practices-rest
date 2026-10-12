// deck.js — "API Patterns & Practices: REST — Python / FastAPI Implementation".
// How the 100-level patterns are built in FastAPI, shipping/cargo domain,
// against one OpenAPI contract. Real code from examples/*/python/** and
// _docs/23-fastapi-in-depth.md.
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

const OUT = path.resolve(__dirname, "api-patterns-rest-python-r1.0.pptx");
const REV = "r1.0";

const pres = newDeck();
pres.title = "API Patterns & Practices: REST — Python / FastAPI Implementation";
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
  s.addText([{ text: "The Python /", options: { breakLine: true } }, { text: "FastAPI build." }], {
    x: 5.95, y: 2.28, w: 6.95, h: 2.00, fontFace: FONT.title, fontSize: 48, bold: true, color: COLOR.ink, align: "left", valign: "top" });
  s.addText("Every REST pattern from the 100-level deck, built in FastAPI — Pydantic v2 models, ASGI async vs threadpool, StreamingResponse, BackgroundTasks, and CloudEvents over Kafka — in the shipping & cargo domain, against one OpenAPI contract.", {
    x: 6.00, y: 4.30, w: 6.80, h: 1.30, fontFace: FONT.body, fontSize: 16, italic: true, color: COLOR.caption, align: "left", valign: "top" });
  s.addText([
    { text: "Robert Sedor", options: { bold: true, color: COLOR.ink, breakLine: true } },
    { text: "Principal Chief Architect, Application Development", options: { color: COLOR.caption } },
  ], { x: 6.00, y: 5.75, w: 6.70, h: 0.80, fontFace: FONT.body, fontSize: 15, align: "left", valign: "top" });
  s.addText(REV, { x: 11.85, y: 6.40, w: 0.95, h: 0.30, fontFace: FONT.mono, fontSize: 11, color: COLOR.caption, align: "right", valign: "middle" });
  try { s.addImage({ path: `${ASSETS}/logo-candidate-2.png`, x: 11.10, y: 6.80, w: 1.55, h: 0.37 }); } catch (e) {}
  addNotes(s, "Welcome to the Python and FastAPI implementation deck — deck three of three in the API Patterns & Practices: REST series. The 100-level deck established the patterns and the reasoning, stack-agnostic; the Quarkus deck showed one implementation; this deck shows the other, in FastAPI, against the same single OpenAPI contract and the same shipping and cargo domain. Everything is real code from the runnable examples under examples/*/python and the Chapter 23 deep-dive. FastAPI's defining concern is the mirror image of Quarkus's: where Quarkus decides at build time how a request maps onto a method, FastAPI decides at request time where each handler runs — on the single shared event loop, or offloaded to a threadpool. That one distinction underlies streaming, background work, and performance, so we start there. I'm Robert Sedor. By the end you'll have seen the Pydantic v2 models with Field constraints, the exception-handler approach to Problem Details, keyset pagination, the async operation, HATEOAS, media-type versioning, StreamingResponse and BackgroundTasks, the confluent-kafka CloudEvents publisher, and pytest with TestClient.");
}

/* ======================= 2 · AGENDA ======================= */
{
  const s = S();
  addContentTitle(s, "ROADMAP", "Agenda");
  addTwoColBullets(s,
    [
      "ASGI: async def on the loop vs plain def",
      "Pydantic v2 models with Field constraints",
      "Problem Details via exception handlers",
      "Content negotiation & partial updates",
      "Keyset pagination",
      "Async operations (202 → poll → 303)",
    ],
    [
      "HATEOAS links from the lifecycle FSM",
      "Versioning & soft deletion",
      "StreamingResponse / SSE + BackgroundTasks",
      "CloudEvents over Kafka (confluent-kafka)",
      "Testing (pytest + TestClient), running it",
      "Ecosystem · wrap-up · Q&A",
    ],
    { fontSize: 15 });
  addNotes(s, "The arc follows the same pattern order as the other two decks, so all three map one to one — but every stop here is FastAPI code. We open with the ASGI execution model, the async-def-versus-plain-def distinction that everything else depends on. Then the Pydantic v2 models that serve as DTOs, and the exception-handler approach to turning failures into RFC 9457 Problem Details. The middle covers HTTP semantics in FastAPI, keyset pagination, and the asynchronous operation. Then the lifecycle patterns — HATEOAS, media-type versioning, soft deletion — followed by the two streaming mechanics FastAPI is known for, StreamingResponse and BackgroundTasks, and the confluent-kafka CloudEvents publisher. We finish with testing via pytest and TestClient, running across the three tiers, and the ecosystem. A short appendix carries extra code variants. Speaker notes on every slide, appendix included.");
}

/* ======================= 3 · SERIES MAP ======================= */
{
  const s = S();
  addContentTitle(s, "SERIES MAP", "Where this deck sits");
  addBullets(s, [
    "Deck 1 (100-level) is the patterns and the why, stack-agnostic — start there for the reasoning.",
    "This deck is the FastAPI HOW: the same shipping/cargo contract realized in FastAPI, with real code.",
    "The Quarkus sibling deck does the identical arc in Java — both are validated against the one OpenAPI contract in CI.",
    "Code shown here is lifted from examples/*/python/** and the Chapter 23 deep-dive; Python 3.14, Pydantic v2, uvicorn.",
  ], { fontSize: 17 });
  addCaption(s, "Same patterns, same domain, same contract — this deck is the FastAPI realization of them.");
  addNotes(s, "The same orientation as the Quarkus deck. Deck one, the 100-level, carries the patterns and the reasoning, stack-agnostic — that's where the why lives. This deck is the FastAPI how: each pattern realized in real FastAPI code against the same shipping and cargo contract and domain. The Quarkus sibling deck walks the identical arc in Java, and the reason both exist is that the two are validated against the one OpenAPI contract in CI, so they stay interchangeable — a client can't tell which stack answered. All the code is real, from examples slash star slash python and the Chapter 23 deep-dive, on pinned versions — Python 3.14, Pydantic v2, uvicorn. A useful way to watch this deck: notice how often the FastAPI code reaches the identical HTTP contract as the Quarkus code by a completely different route — relative Location headers set by hand, the same status codes, the same Problem shape — because that byte-for-byte parity is exactly what the shared tests enforce.");
}

/* ======================= DIVIDER 01 ======================= */
divider("01", "FastAPI & the ASGI model",
  "One event loop, many requests — async def on the loop, plain def in a threadpool.",
  "FastAPI's defining decision is made at request time, every time: which execution context runs this handler — the single event loop every other request shares, or a worker thread from a bounded pool. Get that split right and streaming, background work, and throughput all follow; get it wrong and one blocking call stalls every request.");

/* --- ASGI diagram --- */
{
  const s = S();
  addDiagramSlide(s, "ASGI", "Where each handler actually runs",
    "r23-asgi-dispatch",
    "async def runs ON the event loop (cooperates at await); plain def is offloaded to the AnyIO threadpool.",
    { x: 1.10, y: 1.72, w: 11.13, h: 4.60 });
  addNotes(s, "FastAPI is a thin layer over Starlette, and Starlette is built on ASGI — the asynchronous server gateway interface. Where the old WSGI contract is synchronous and single-shot, so your only lever for concurrency is more processes or threads, ASGI is asynchronous: one process can hold many requests in flight at once without a thread each — as long as none of them blocks the thread driving all of them. That thread is the event loop, and in the simplest deployment it's uvicorn's single process with one event-loop thread. The loop drives every coroutine that's waiting on something by resuming whichever just became unblocked. An async def route is such a coroutine: it runs until it hits an await, then yields control so another request's coroutine can progress. The critical design decision is on the diagram: FastAPI accepts both async def and plain def handlers, and they run in different places. An async def handler runs ON the event loop. A plain def handler is detected as not-a-coroutine and offloaded to a worker thread from AnyIO's threadpool, so it can block freely without freezing the loop. This is the mirror of Quarkus's choice — Quarkus decides at build time how a request binds; FastAPI decides at request time where the handler runs. Both are invisible on the wire, which is why you have to open the box.");
}

/* --- async vs plain def code --- */
{
  const s = S();
  addCodeSlide(s, "ASGI", "async def vs plain def — and the GIL", "python · FastAPI",
    [
      "@app.get('/thread/async')",
      "async def thread_async() -> dict:        # runs ON the event loop",
      "    return _thread_report('async')       # main thread, every call",
      "",
      "@app.get('/thread/sync')",
      "def thread_sync() -> dict:               # plain def -> AnyIO threadpool",
      "    return _thread_report('sync')        # a worker thread, every call",
      "",
      "# async def + await for awaitable I/O (asyncpg, httpx, async Kafka)",
      "# plain def for blocking libraries with no async equivalent",
      "# GIL: blocking I/O releases it (loop stays free); CPU-bound work does not",
    ],
    "Writing async def around a blocking call is the trap: it looks safe, schedules on the loop, and stalls every request.",
    { fontSize: 12 });
  addNotes(s, "The two-endpoint demonstration from Chapter 23. thread_async is declared async def, so Starlette awaits it directly on the event loop, and threading.current_thread is always the main thread. thread_sync is a plain def, so Starlette offloads it via AnyIO's run_sync to a threadpool worker, and the same check always reports a non-main thread. This split is deterministic — a property of which kind of function it is, not of scheduling luck. The rule in the comments is the one every real handler is written against: use async def with await for anything awaitable — an async database driver like asyncpg, httpx, an async Kafka client — so it cooperates with the loop; use plain def for anything built on a blocking library with no async equivalent, so the threadpool isolates its blocking. The GIL shapes what offloading buys: CPython runs only one thread of Python bytecode at a time, so offloading doesn't give parallelism — it gives concurrency, which is enough as long as the offloaded work periodically releases the GIL. Blocking I/O does release it — a socket or file read hands the GIL back while waiting on the kernel — which is the window the loop needs. CPU-bound Python doesn't, so a tight pure-Python loop still contends. The caption is the failure mode this whole split exists to prevent: writing async def around a blocking call looks safe, schedules on the loop, and freezes every in-flight request for the duration — with no symptom until load.");
}

/* --- when to use which --- */
{
  const s = S();
  addContentTitle(s, "ASGI", "Choosing async def or plain def, per endpoint");
  addTwoColBullets(s,
    [
      { text: "async def when…", options: { bold: true, bullet: false } },
      "Every I/O call has a real async driver (asyncpg, httpx).",
      "You await an async Kafka client or async ORM.",
      "You need StreamingResponse or BackgroundTasks (both live on the loop).",
    ],
    [
      { text: "plain def when…", options: { bold: true, bullet: false } },
      "The only dependency is a blocking library (sync ORM, legacy SDK).",
      "A short CPU-bound computation with no async equivalent.",
      "Offloading to the threadpool keeps the loop free for everyone.",
    ],
    { fontSize: 15 });
  addCaption(s, "Decide per endpoint, not per service. The deciding question is always: what does this handler block on?");
  addNotes(s, "The Chapter 23 Decision callout, as guidance you can apply. Choose per endpoint, not once for the whole service, and the deciding question is always 'what does this handler block on?' Use async def when every I/O call inside it has a real async driver — asyncpg over psycopg2, httpx over requests, an async Kafka client — because then async def is close to free and the handler cooperates with the loop the way StreamingResponse and BackgroundTasks both require. Reach for plain def the moment a handler's only dependency is a blocking library with no async equivalent — a synchronous ORM, a legacy SDK, or a short CPU-bound computation — because declaring async def around a blocking call doesn't make it non-blocking, it just hides a stalled loop behind a signature that looks safe. And the honest boundary: once the blocking work is CPU-bound and large, a threadpool's cooperative concurrency isn't the fix at all — true parallel computation needs multiple processes or a C extension that drops the GIL. One more calibration: on a low-traffic internal service where no slow handler ever competes with enough concurrent requests for a stall to be noticeable, the distinction barely matters — it matters in proportion to how many requests share that one loop when a handler blocks it.");
}

/* ======================= DIVIDER 02 ======================= */
divider("02", "Contract-first & the resource model",
  "Pydantic v2 models, the booking handlers, and Problem Details via exception handlers.",
  "The resource layer in FastAPI: Pydantic v2 models whose Field constraints mirror the shared schema, handlers that implement the booking surface, and an exception-handler that turns validation failures into application/problem+json.");

/* --- pydantic models --- */
{
  const s = S();
  addCodeSlide(s, "RESOURCES", "Pydantic v2 models with Field constraints", "python · FastAPI",
    [
      "class Location(BaseModel):",
      "    model_config = ConfigDict(extra='forbid')   # reject unknown fields",
      "    unLocode: str = Field(pattern=r'^[A-Z]{2}[A-Z0-9]{3}$')",
      "    name: Optional[str] = None",
      "    country: Optional[str] = Field(default=None, pattern=r'^[A-Z]{2}$')",
      "",
      "class Dimensions(BaseModel):",
      "    model_config = ConfigDict(extra='forbid')",
      "    weightKg: float = Field(gt=0)                # mirrors @Positive on Quarkus",
      "    volumeM3: Optional[float] = Field(default=None, gt=0)",
      "",
      "class BookingRequest(BaseModel):",
      "    model_config = ConfigDict(extra='forbid')",
      "    origin: Location; destination: Location",
      "    cargo: list[CargoRequest] = Field(min_length=1)   # >= 1 cargo item",
    ],
    "Field(...) constraints and extra='forbid' mirror the shared JSON Schema — a shape drift fails validation on the way in.",
    { fontSize: 11 });
  addNotes(s, "Pydantic v2 models are the FastAPI equivalent of the Quarkus records-plus-Bean-Validation, and they're chosen so the two stacks reject the same malformed input. Each model sets model_config extra='forbid', which rejects unknown fields — the Pydantic equivalent of a strict schema's additionalProperties false — so a client can't smuggle in fields the contract doesn't declare. The constraints live in Field: Location's unLocode has the UN/LOCODE regex pattern, country has its own; Dimensions' weightKg uses gt=0, which mirrors the @Positive on the Quarkus side; BookingRequest requires at least one cargo item with min_length=1. The field names, requiredness, and patterns all intentionally match the shared JSON Schema, so a shape drift here surfaces two ways: as a Pydantic validation error on the way in, and as a response-validation failure on the way out in CI. Nesting works the way @Valid cascades in Quarkus — a BookingRequest contains Location and CargoRequest models, and validating the outer model validates all of them. This is the contract-first discipline made concrete in Python: the model is the schema, in code.");
}

/* --- app + create_booking --- */
{
  const s = S();
  addCodeSlide(s, "RESOURCES", "The booking handlers", "python · FastAPI",
    [
      "app = FastAPI(title='shipping-python')   # (APIRouter to split at scale)",
      "",
      "@app.post('/bookings')",
      "def create_booking(payload: BookingRequest) -> JSONResponse:",
      "    cargo_items = [Cargo(id=f'crg_{generate_ulid()}', **item.model_dump())",
      "                   for item in payload.cargo]",
      "    booking = Booking(id=f'bkg_{generate_ulid()}', status=BookingStatus.PENDING,",
      "        origin=payload.origin, destination=payload.destination,",
      "        cargo=cargo_items, quote=compute_quote(cargo_items),",
      "        requestedPickup=payload.requestedPickup, createdAt=_now_utc())",
      "    store.put(booking)",
      "    return _json(201, booking, headers={'Location': f'/bookings/{booking.id}'})",
    ],
    "payload: BookingRequest validates the body automatically; the server mints the id and returns 201 + a relative Location.",
    { fontSize: 11 });
  addNotes(s, "The create handler, and the FastAPI ergonomics are worth noticing. The type annotation payload: BookingRequest is all it takes to get automatic request-body validation — FastAPI reads the Pydantic model, validates the incoming JSON against it, and hands you a typed object, or raises a validation error before your code runs. The handler mints the server-assigned id with a bkg_ prefix and ULID body, sets status PENDING, computes the quote, persists, and returns. The _json helper serializes with mode='json' and exclude_none=True — that exclude_none matters because the shared schema doesn't declare nulls for optional fields, so omitting them rather than emitting JSON null keeps the response schema-valid. And the Location header is set as a literal relative path, exactly like the Quarkus side, so the two stacks stay byte-identical. These examples use @app decorators directly for simplicity; at scale you'd split the surface across APIRouter instances and include them, which is the same decorator model one level up. Note this handler is a plain def — it does no awaitable I/O, just in-memory work — so FastAPI runs it in the threadpool, which is the correct choice from the ASGI section.");
}

/* --- Problem via exception handler --- */
{
  const s = S();
  addCodeSlide(s, "RESOURCES", "Problem Details via an exception handler", "python · FastAPI",
    [
      "def _problem(status_code: int, title: str, detail: str | None = None) -> JSONResponse:",
      "    body = Problem(title=title, status=status_code, detail=detail)",
      "    return JSONResponse(status_code=status_code,",
      "        content=body.model_dump(mode='json', exclude_none=True),",
      "        media_type='application/problem+json')",
      "",
      "@app.exception_handler(RequestValidationError)",
      "async def validation_exception_handler(request, exc) -> JSONResponse:",
      "    return _problem(400, 'Validation failed', str(exc.errors()))",
      "",
      "# handlers return _problem(404, ...), _problem(409, ...), _problem(415, ...)",
    ],
    "One exception handler catches FastAPI's own validation error; a shared _problem helper shapes every error as RFC 9457.",
    { fontSize: 12 });
  addNotes(s, "The FastAPI counterpart to Quarkus's exception mappers. There are two moving parts. First, a shared _problem helper that builds a Problem model and returns it as a JSONResponse with the application/problem+json media type and exclude_none serialization — every deliberate error in the handlers calls this, so 404 not found, 409 conflict on an illegal transition, and 415 unsupported media type all come back in the same RFC 9457 shape. Second, the @app.exception_handler decorator registers a handler for RequestValidationError, which is what FastAPI raises when a request body fails Pydantic validation — it catches that framework-raised error and routes it through the same _problem helper as a 400. That's the key parallel to the Quarkus mappers: the errors FastAPI raises itself, before your handler runs, are brought into the same Problem shape as the errors you raise deliberately, so a client only ever sees one error format across the whole API. The same discipline, a different mechanism — Quarkus uses @Provider ExceptionMappers keyed on exception type; FastAPI uses @app.exception_handler plus a shared helper.");
}

/* ======================= DIVIDER 03 ======================= */
divider("03", "HTTP semantics in FastAPI",
  "Content negotiation, merge-patch, and status codes.",
  "The semantics patterns in FastAPI code: a PATCH that checks the merge-patch media type by hand, status codes set explicitly, and the Location header shaped to match the contract and the Quarkus stack.");

/* --- merge patch --- */
{
  const s = S();
  addCodeSlide(s, "SEMANTICS", "Merge-patch, checked by media type", "python · FastAPI",
    [
      "@app.patch('/bookings/{booking_id}')",
      "async def patch_booking(booking_id: str, request: Request) -> JSONResponse:",
      "    content_type = request.headers.get('content-type', '')",
      "    if not content_type.startswith('application/merge-patch+json'):",
      "        return _problem(415, 'Unsupported Media Type',",
      "            'PATCH requires Content-Type: application/merge-patch+json')",
      "    existing = store.get(booking_id)",
      "    if existing is None: return _problem(404, 'Booking not found', ...)",
      "    patch_doc = await request.json()",
      "    merged = _merge_patch(existing.model_dump(mode='json', exclude_none=True), patch_doc)",
      "    merged['id'] = existing.id; merged['createdAt'] = existing.createdAt  # readOnly",
      "    updated = Booking.model_validate(merged)   # re-validate the result",
      "    store.put(updated); return _json(200, updated)",
    ],
    "async def here — it awaits request.json(); id/createdAt are restored so a patch can't overwrite server-assigned fields.",
    { fontSize: 10 });
  addNotes(s, "Partial updates, FastAPI-side, and notice this handler is async def — because it awaits request.json to read the raw body, which is awaitable I/O, so async def is the correct choice. Unlike Quarkus, where @Consumes scoping lets the framework reject a wrong media type before the method runs, here the check is explicit: read the Content-Type header and return a 415 Problem if it isn't application/merge-patch+json. Both reach the same contract; FastAPI just does it in the handler. Then it reads the sparse patch document as raw JSON — not a typed model, because a merge patch only carries the fields being changed — and applies RFC 7396 merge semantics with the recursive _merge_patch helper, where a null value means remove. The critical safety lines are the same as Quarkus: after merging, id and createdAt are explicitly restored from the existing booking, because they're server-assigned and readOnly, so a client can't overwrite them. Finally — and this is a nice Pydantic touch — the merged dict is re-validated through Booking.model_validate before being stored, so a patch that would produce an invalid booking is rejected with a Problem rather than persisted. Same contract, same safety, idiomatic Python.");
}

/* --- status codes --- */
{
  const s = S();
  addContentTitle(s, "SEMANTICS", "Status codes, set deliberately");
  addStatusTable(s, [
    { code: "201", name: "_json(201, ..., headers)", purpose: "create_booking — plus a literal relative Location header to the new booking." },
    { code: "202", name: "_json(202, operation, ...)", purpose: "request_confirmation — Location points at the Operation to poll." },
    { code: "204", name: "Response(status_code=204)", purpose: "delete_booking (soft-delete) and operation cancel — success, empty body." },
    { code: "303", name: "Response(303, headers=...)", purpose: "get_operation — once SUCCEEDED, Location to the confirmed booking." },
    { code: "4xx", name: "_problem(...)", purpose: "404/409/415/400 all return application/problem+json via the shared helper." },
  ], { colW: [0.95, 3.85, 7.29], rowH: 0.62 });
  addCaption(s, "status_code on the decorator or the Response; the Location header is literal/relative so both stacks stay byte-identical.");
  addNotes(s, "Status codes in FastAPI are set either on the route decorator — status_code=204 on the delete — or on the Response or JSONResponse object directly, and the examples do so deliberately. create_booking returns 201 with the relative Location header. request_confirmation returns 202 with Location pointing at the Operation. delete_booking and operation cancel return a bare Response with status_code 204 and no body, right for a soft-delete that succeeded. get_operation returns a Response with status_code 303 and a Location header once the operation has SUCCEEDED, redirecting to the confirmed booking. And the whole 4xx family flows through the _problem helper so it's application/problem+json. The same discipline as Quarkus, and the same reason: the Location header is built as a literal relative path rather than through any framework helper that might absolutize it, specifically so the FastAPI and Quarkus responses are byte-for-byte identical and the shared contract tests pass against both. It's striking how much of 'matching the contract' comes down to small, deliberate choices like this one on both stacks.");
}

/* ======================= DIVIDER 04 ======================= */
divider("04", "Collections at scale",
  "Keyset pagination with query-parameter knobs, capped.",
  "Reading the booking collection safely in FastAPI: typed query parameters, a hard cap on page size, and an opaque keyset cursor as the default strategy — with offset and seek supported for comparison.");

/* --- pagination diagram --- */
{
  const s = S();
  addDiagramSlide(s, "COLLECTIONS", "Pagination strategies",
    "r08-pagination",
    "FastAPI defaults to keyset-with-cursor; offset and seek supported so the trade-offs are visible side by side.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "The same strategy spectrum — offset, keyset, seek — implemented on one FastAPI list_bookings endpoint so the trade-offs are visible in running code. Offset is simple but drifts and slows at depth; keyset pages on the last-seen sort key, consistent and fast but coupled to the sort; seek adds an opaque cursor that decouples paging from filters. Keyset-with-cursor is the default and stable strategy, matching the shared contract. The next slide is the handler. The invariant across all three, and the real takeaway, is the same as on Quarkus: the page limit is clamped in code, never honoured unbounded, because an unbounded limit is a denial-of-service vector regardless of the client's intent.");
}

/* --- pagination code --- */
{
  const s = S();
  addCodeSlide(s, "COLLECTIONS", "Keyset pagination in FastAPI", "python · FastAPI",
    [
      "@app.get('/bookings')",
      "def list_bookings(",
      "    limit: int | None = None,        # page size, clamped to [1, 100]",
      "    offset: int | None = None,       # offset pagination (comparison)",
      "    after_id: str | None = None,     # seek pagination",
      "    cursor: str | None = None,       # keyset — the DEFAULT strategy",
      "    fields: str | None = None,       # sparse fieldset projection",
      ") -> JSONResponse:",
      "    visible = store.list_visible()",
      "    effective_limit = _clamp_limit(limit)            # DoS guard: max 100",
      "    page_items, next_cursor = _compute_page(visible, offset, after_id, cursor, effective_limit)",
      "    page_meta = PageMeta(limit=effective_limit, count=len(page_items), nextCursor=next_cursor)",
      "    return _json(200, BookingCollection(items=page_items, page=page_meta))",
    ],
    "Query knobs are just typed function parameters; _clamp_limit enforces the schema max, nextCursor is null on the last page.",
    { fontSize: 10 });
  addNotes(s, "The real FastAPI pagination handler, and the ergonomics are delightful: the query parameters are just typed function parameters with defaults, and FastAPI parses, validates, and injects them — no annotations needed beyond the type hints. The four knobs mirror the Quarkus side exactly: limit, offset, after_id for seek, cursor for keyset which is the default, and fields for sparse projection. The first real action is _clamp_limit, forcing the limit into 1 to 100 to match the shared schema's maximum — the same DoS guard as Quarkus, because an unbounded limit lets a client force an arbitrarily large response. _compute_page dispatches to the right strategy and returns the page plus an opaque next cursor, which is a base64 token the client treats as opaque. The response is a BookingCollection with a PageMeta carrying the applied limit, the count, and nextCursor, null on the last page as the end-of-collection signal. One subtlety noted in the source: when fields is present, the sparse projection is built by hand rather than through the Booking model, because a projected object isn't a schema-conforming full Booking — the same edge the Quarkus side handles. Same contract, same guards, idiomatic Python.");
}

/* ======================= DIVIDER 05 ======================= */
divider("05", "Asynchronous operations",
  "The 202 → poll → 303 protocol in FastAPI handlers.",
  "Confirmation can't finish in one request, so it's the asynchronous operation pattern: the confirmation handler accepts the work with 202 and an Operation to poll, and the operation handlers serve the poll and the 303 redirect to the result.");

/* --- async diagram --- */
{
  const s = S();
  addDiagramSlide(s, "ASYNC", "202 → poll → 303",
    "r10-async-flow",
    "The confirmation handler returns 202 + the Operation URI; the operation handler polls and 303s once SUCCEEDED.",
    { x: 1.60, y: 1.70, w: 10.13, h: 4.55 });
  addNotes(s, "The same 202-poll-303 flow, in FastAPI handlers. POST to the confirmation sub-resource accepts the work and returns 202 with Location pointing at a new Operation resource, without blocking on the routing and capacity checks. The client polls the Operation; while PENDING or RUNNING it gets 200 with the body, and once SUCCEEDED the same GET returns 303 with Location pointing at the confirmed booking. The Operation is durable, so a client can come back and ask whether its confirmation finished. The next two slides are the handlers — and there's a nice FastAPI-specific wrinkle in the confirmation handler worth watching for.");
}

/* --- 202 half --- */
{
  const s = S();
  addCodeSlide(s, "ASYNC", "The 202 half — and why it's async def", "python · FastAPI",
    [
      "@app.post('/bookings/{booking_id}/confirmation', status_code=202)",
      "async def request_confirmation(booking_id: str) -> JSONResponse:",
      "    # async def (not def): start_confirmation() schedules an asyncio task,",
      "    # which needs a running event loop — a plain def runs in a threadpool",
      "    # where there is none.",
      "    booking = store.get(booking_id)",
      "    if booking is None: return _problem(404, 'Booking not found', ...)",
      "    if booking.status != BookingStatus.PENDING:",
      "        return _problem(409, 'Booking not confirmable',",
      "            f'Booking {booking_id} is not PENDING (status={booking.status.value})')",
      "    op_id = f'op_{generate_ulid()}'",
      "    operation = operations.start_confirmation(op_id, booking_id)",
      "    return _json(202, operation, headers={'Location': f'/operations/{op_id}'})",
    ],
    "A confirm on a non-PENDING booking is 409. This handler must be async def so it can schedule the background asyncio task.",
    { fontSize: 10 });
  addNotes(s, "The accept half, and it's the clearest payoff of the ASGI section. The guards are the same as Quarkus: a missing booking is 404, and confirming a non-PENDING booking is a 409 Conflict because it's an illegal state transition. But look at the comment explaining why this handler is async def when most handlers in this module are plain def: start_confirmation schedules a background asyncio task to do the confirmation work, and asyncio.create_task needs a running event loop. A plain def handler runs in the threadpool, where there is no event loop, so scheduling the task would fail. An async def handler runs directly on the loop the background task is scheduled onto. This is exactly the per-endpoint decision from the ASGI section, with a concrete consequence — and it's the kind of thing that's invisible until you need it. It mints the Operation id, starts the work, and returns 202 with the relative Location header pointing at the Operation. The Python and Quarkus confirmation handlers reach an identical 202 response by different runtime mechanisms — Quarkus runs the work off-thread via its own machinery, FastAPI schedules an asyncio task on the loop.");
}

/* --- poll/303 half --- */
{
  const s = S();
  addCodeSlide(s, "ASYNC", "The poll half — 200 running, 303 done", "python · FastAPI",
    [
      "@app.get('/operations/{operation_id}')",
      "def get_operation(operation_id: str) -> Response:",
      "    operation = operations.get(operation_id)",
      "    if operation is None: return _problem(404, 'Operation not found', ...)",
      "    if operation.status == OperationStatus.SUCCEEDED:",
      "        return Response(status_code=303, headers={'Location': operation.resource})",
      "    return _json(200, operation)         # PENDING / RUNNING / FAILED",
      "",
      "@app.delete('/operations/{operation_id}', status_code=204)",
      "def cancel_operation(operation_id: str) -> Response:",
      "    operations.cancel(operation_id)      # idempotent: 204 either way",
      "    return Response(status_code=204)",
    ],
    "SUCCEEDED → 303 to the booking; otherwise 200 with the Operation. DELETE cancels and is idempotent.",
    { fontSize: 11 });
  addNotes(s, "The poll and cancel half. get_operation is the heart: if the operation has SUCCEEDED, return a 303 with Location pointing at operation.resource — the confirmed booking — so the client follows the redirect to the result; any other status returns 200 with the Operation body so the client keeps polling or sees FAILED with its error. That's the whole 202-poll-303 contract. Notice get_operation is a plain def — it does only in-memory lookups, no awaitable I/O, so plain def is correct and FastAPI runs it in the threadpool. The DELETE provides the cancel affordance: it cancels a still-running operation and returns 204, and it's idempotent — cancelling an already-terminal operation is a no-op that still returns 204, mirroring DELETE on a booking. Line for line this matches the Quarkus OperationResource, which is the point of the whole series: the same protocol, implemented idiomatically in each stack, reaching the same wire behaviour the shared tests verify against both.");
}

/* ======================= DIVIDER 06 ======================= */
divider("06", "Lifecycle: HATEOAS, versioning, soft delete",
  "Links from the state machine, media-type versioning, and soft deletion.",
  "The evolution patterns in FastAPI: a link builder that emits exactly the legal transitions, media-type versioning that projects one stored resource into an older representation, and a soft-delete via model_copy.");

/* --- HATEOAS diagram --- */
{
  const s = S();
  addDiagramSlide(s, "LIFECYCLE", "HATEOAS: links are the state machine",
    "r12-hateoas-fsm",
    "links_for_booking emits self everywhere, confirm+cancel while PENDING, cancel while CONFIRMED, self-only once terminal.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "The booking lifecycle state machine, implemented in FastAPI by a small links_for_booking function that maps a booking's current status to the set of links it should carry — mirroring the Quarkus HateoasLinks relation for relation. The response is the state machine; the client follows links instead of hard-coding the rules. The next slide is that builder plus the helper that attaches the links to each response.");
}

/* --- HATEOAS code --- */
{
  const s = S();
  addCodeSlide(s, "LIFECYCLE", "Building _links from the lifecycle FSM", "python · FastAPI",
    [
      "def links_for_booking(booking_id: str, status: BookingStatus) -> dict[str, Link]:",
      "    links = {'self': Link(href=f'/bookings/{booking_id}', method='GET', ...)}",
      "    if status == BookingStatus.PENDING:",
      "        links['confirm'] = Link(href=f'/bookings/{booking_id}/confirmation', method='POST', ...)",
      "        links['cancel']  = Link(href=f'/bookings/{booking_id}', method='DELETE', ...)",
      "    elif status == BookingStatus.CONFIRMED:",
      "        links['cancel']  = Link(href=f'/bookings/{booking_id}', method='DELETE', ...)",
      "    # IN_TRANSIT, DELIVERED, CANCELLED: self only — terminal",
      "    return links",
      "",
      "def _with_links(b: Booking) -> Booking:    # recompute from CURRENT status",
      "    return b.model_copy(update={'links': links_for_booking(b.id, b.status)})",
    ],
    "The Booking model aliases links to _links on the wire; every response recomputes them from the booking's current status.",
    { fontSize: 11 });
  addNotes(s, "The entire HATEOAS implementation, mirroring the Quarkus one. links_for_booking takes the id and current status and returns the link map: self everywhere, confirm and cancel added while PENDING, only cancel while CONFIRMED, and nothing but self once terminal. Each Link carries href, method, and title. The _with_links helper is the FastAPI-specific glue: it uses Pydantic's model_copy to produce a copy of the booking with the links field freshly computed from the booking's current status, and every response path runs the booking through it. There's a nice Pydantic detail in the model: the field is named links in Python but aliased to _links on the wire, so the Python code is clean while the JSON matches the contract's underscore convention. The payoff is identical to the concept deck and the Quarkus deck: the rule about which transitions are legal lives in exactly this one function, the server emits the links, and a client renders whatever arrives — no client-side state machine, no redeploy when the rules change. Same behaviour as Quarkus, reached through Pydantic's model_copy and field aliasing.");
}

/* --- versioning --- */
{
  const s = S();
  addCodeSlide(s, "LIFECYCLE", "Media-type versioning — one resource, two shapes", "python · FastAPI",
    [
      "MEDIA_TYPE_V1 = 'application/vnd.shipping.v1+json'",
      "MEDIA_TYPE_V2 = 'application/vnd.shipping.v2+json'",
      "",
      "def _wants_v1(accept_header: str | None) -> bool:",
      "    # anything else — v2 type, bare application/json, */*, missing — means v2",
      "    return bool(accept_header) and MEDIA_TYPE_V1 in accept_header",
      "",
      "def _to_v1(booking: Booking) -> BookingV1:        # LOSSY, read-only projection",
      "    return BookingV1(id=booking.id, status=booking.status,",
      "        origin=booking.origin, destination=booking.destination,",
      "        cargoDescription='; '.join(i.description for i in booking.cargo),",
      "        price=booking.quote, createdAt=booking.createdAt)",
      "# response echoes the negotiated Content-Type and sets Vary: Accept",
    ],
    "One stored (v2) resource; v1 is a derived view. The response sets Vary: Accept so caches don't serve the wrong version.",
    { fontSize: 11 });
  addNotes(s, "Media-type versioning in FastAPI, teaching the same lesson as the Quarkus side: versioning is about the representation a client gets back, not about forking the resource. Two vendor media types. _wants_v1 reads the Accept header — anything that isn't explicitly the v1 type, including a bare application/json, a wildcard, or the v2 type, means 'give me current', so no-opinion and current behave identically. The crucial design choice is in _to_v1: there is no v1 store and no v1 write path — the one booking is always stored in the current v2 shape, and v1 is a read-only projection computed on the way out. And it's deliberately lossy: v1's single cargoDescription string is built by joining the v2 cargo descriptions, and v1 can't recover the individual items, weights, or hazardous flags from it — the honest cost of carrying an old representation forward. On the endpoint, the response echoes the negotiated vendor type in Content-Type and sets Vary: Accept, so a shared cache treats the URL as having more than one representation and won't serve a cached v1 body to a client that asked for v2. That Vary header is the caching subtlety from the concept deck, in Python.");
}

/* --- soft delete --- */
{
  const s = S();
  addCodeSlide(s, "LIFECYCLE", "Soft deletion — model_copy, don't erase", "python · FastAPI",
    [
      "@app.delete('/bookings/{booking_id}', status_code=204)",
      "def delete_booking(booking_id: str) -> Response:",
      "    existing = store.get(booking_id)",
      "    if existing is None:",
      "        return _problem(404, 'Booking not found', f'No booking with id {booking_id}')",
      "    cancelled = existing.model_copy(",
      "        update={'status': BookingStatus.CANCELLED, 'updatedAt': _now_utc()})",
      "    store.put(cancelled)",
      "    return Response(status_code=204)      # idempotent",
      "",
      "# store.list_visible() excludes CANCELLED; a separate governed purge",
      "# does hard-deletion (GDPR right-to-erasure).",
    ],
    "Pydantic's model_copy flips status to CANCELLED; the row persists for audit/undelete and stays out of default queries.",
    { fontSize: 11 });
  addNotes(s, "Soft deletion in FastAPI, using Pydantic's model_copy — the idiomatic way to produce an updated immutable model. DELETE doesn't erase the row; it copies the booking with status flipped to CANCELLED and updatedAt stamped, persists it, and returns 204. Because the data survives, you get recovery, audit history, and referential integrity, and because flipping an already-cancelled booking to cancelled lands the same state, DELETE is idempotent, as the matrix requires. The two comments carry the rest: the store's list_visible excludes CANCELLED bookings so soft-deleted rows stay out of default queries — a cancelled booking must not appear in a normal list — and there's a separate, governed purge path for lawful hard-deletion, distinct from everyday cancel, because GDPR's right to erasure can require data actually be gone, not merely hidden. Soft-delete is the default; purge is the governed exception. Line for line this matches the Quarkus deleteBooking; the only difference is model_copy versus constructing a new record.");
}

/* ======================= DIVIDER 07 ======================= */
divider("07", "Streaming & deferred work",
  "StreamingResponse / SSE, BackgroundTasks, and Range — all on the event loop.",
  "FastAPI's streaming mechanics, all resting on the ASGI model from the opening: StreamingResponse drips frames as an async generator yields them, BackgroundTasks defers work past the response on the same loop, and Range serves large binaries.");

/* --- bg/sse diagram --- */
{
  const s = S();
  addDiagramSlide(s, "STREAMING", "StreamingResponse & BackgroundTasks on one loop",
    "r23-bg-sse",
    "An async generator yields SSE frames as produced; BackgroundTasks runs deferred work after a 202 — both on the event loop.",
    { x: 1.10, y: 1.72, w: 11.13, h: 4.55 });
  addNotes(s, "Two FastAPI mechanics, both resting on the one event loop from the opening section. On the left, StreamingResponse: it takes an async iterable and writes each item to the socket as it's yielded, rather than materializing the whole body first — so an async generator that awaits between yields produces each frame over time, and each leaves the server as it's produced. On the right, BackgroundTasks: it lets a handler accept a request, return a response immediately — a 202 — and schedule slow work to run after the response has been sent, on the same event loop, a later turn. Both depend on the handler cooperating with the loop, which is why both live in async def territory. The next two slides are each in code, and the examples prove the streaming is real by timestamping each frame's arrival — because a buffered implementation could produce byte-identical output all at once.");
}

/* --- StreamingResponse SSE --- */
{
  const s = S();
  addCodeSlide(s, "STREAMING", "StreamingResponse: SSE from an async generator", "python · FastAPI",
    [
      "async def _sse_event_stream(booking_id: str) -> AsyncIterator[str]:",
      "    for i in range(SSE_EVENT_COUNT):",
      "        await asyncio.sleep(SSE_INTERVAL_SECONDS)   # suspend, yield to the loop",
      "        payload = event_for(booking_id, i)",
      "        yield f'data: {json.dumps(payload)}\\n\\n'    # one SSE frame, flushed now",
      "",
      "@app.get('/bookings/{booking_id}/events')",
      "async def booking_events(booking_id: str) -> Response:",
      "    if _booking_or_404(booking_id) is not None: return ...",
      "    return StreamingResponse(_sse_event_stream(booking_id),",
      "                             media_type='text/event-stream')",
    ],
    "await before each yield hands control to the loop; StreamingResponse writes each frame to the socket as it's produced.",
    { fontSize: 11 });
  addNotes(s, "Server-Sent Events from an async generator, from the Chapter 23 example. _sse_event_stream is an async generator — Python's native vocabulary for a sequence produced over time. The await asyncio.sleep before each yield is the key: it suspends the function, handing control back to the event loop so other requests make progress, and only resumes to produce the next frame when the timer fires. Each yield hands StreamingResponse one SSE frame in the text/event-stream wire format — data colon, the JSON, two newlines — and StreamingResponse writes it to the socket immediately rather than accumulating. The handler is async def because it drives an async generator, and it returns StreamingResponse with the event-stream media type. Why does this matter beyond looking neat? Because a handler that built all five events, serialized them, and handed one complete string to StreamingResponse would pass a status check, a content-type check, even a byte-for-byte body comparison — every observable difference is in when each byte leaves the server. The example's verify script proves real streaming by reading line by line with curl and timestamping each arrival, asserting the spread. Each frame is also schema-validated against the shared BookingEvent as it arrives — streaming doesn't relax the obligation that each unit be schema-valid.");
}

/* --- BackgroundTasks --- */
{
  const s = S();
  addCodeSlide(s, "STREAMING", "BackgroundTasks: a prompt 202, deferred effect", "python · FastAPI",
    [
      "async def _send_notification(booking_id: str, message: str) -> None:",
      "    await asyncio.sleep(NOTIFY_DELAY_SECONDS)       # stands in for email/SMS/webhook",
      "    store.add_notification(booking_id, message, _now_utc())",
      "",
      "@app.post('/bookings/{booking_id}/notify')",
      "async def notify_booking(booking_id: str, payload: NotifyRequest,",
      "                         background_tasks: BackgroundTasks) -> Response:",
      "    if _booking_or_404(booking_id) is not None: return ...",
      "    background_tasks.add_task(_send_notification, booking_id, payload.message)",
      "    return JSONResponse(status_code=202, content={'bookingId': booking_id,",
      "                                                  'status': 'queued'})",
    ],
    "add_task runs AFTER the 202 is flushed, on the same loop — 202 means accepted, not yet done.",
    { fontSize: 11 });
  addNotes(s, "BackgroundTasks answers a different question than streaming: not how to send a long response incrementally, but how to accept a request, trigger slow work, and not make the caller wait. background_tasks.add_task schedules _send_notification to run after the response is sent — Starlette holds the callable, flushes the 202, and only then awaits the task on the same event loop. Because _send_notification is itself async def and only awaits, running it later costs nothing extra in threads — it's the same loop, a later turn. The 202 Accepted makes a specific promise: accepted and will be done, not already done — and a disguised-synchronous handler can fake the status code while breaking the timing. The example's verify script checks both halves: the POST must return far faster than the work takes, which rules out an inline await, and an immediate GET of the notifications must show an empty list — the side effect hasn't happened yet — before it eventually appears on a poll. BackgroundTasks fits fire-and-forget, in-process work that needn't survive a restart; the moment it must survive a crash, retry with backoff, or be inspected independently, you reach for a real task queue — Celery or ARQ — the Python equivalent of Quarkus's JobRunr.");
}

/* --- Range diagram --- */
{
  const s = S();
  addDiagramSlide(s, "PAYLOADS", "Large binaries: HEAD, Range, 206",
    "r15-range",
    "HEAD learns size + range support; GET with a Range header returns 206 Partial Content and a Content-Range.",
    { x: 1.60, y: 1.70, w: 10.13, h: 4.55 });
  addNotes(s, "For large binary resources — a cargo manifest of many megabytes — FastAPI serves the same standard HTTP range machinery from the concept deck with ordinary handlers. HEAD returns headers without a body so the client learns Content-Length and Accept-Ranges before downloading. A GET with a Range header fetches a slice and the server answers 206 Partial Content with a Content-Range stating which bytes and the total; a range past the end is a 416. Nothing FastAPI-specific or exotic — read the Range header, slice, set the status and Content-Range — which is exactly why it's robust and portable. Shown as a diagram because the pattern, not the handler, is the valuable part.");
}

/* ======================= DIVIDER 08 ======================= */
divider("08", "Events & multi-protocol contracts",
  "Publishing CloudEvents to Kafka with confluent-kafka.",
  "The same booking service answers REST synchronously and announces state changes asynchronously. In FastAPI the event side is confluent-kafka: a CloudEvents-enveloped BookingEvent produced to a Kafka topic, off the request thread, typed by the same shared schema as the REST Booking.");

/* --- multi-protocol diagram --- */
{
  const s = S();
  addDiagramSlide(s, "CONTRACTS", "One service, two protocols, one schema",
    "r21-multiprotocol",
    "OpenAPI (sync) and AsyncAPI (events) both $ref the shared JSON Schema; FastAPI produces the CloudEvents envelope to Kafka.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "The multi-protocol picture, with the FastAPI implementation highlighted. The service answers POST /bookings synchronously under the OpenAPI contract, and when a booking confirms it publishes a CloudEvents-enveloped BookingEvent to a Kafka topic declared by the AsyncAPI contract — and both contracts $ref the same shared JSON Schema, so the Booking a REST client reads and the BookingEvent a Kafka consumer reads can't drift on their shared fields. On the FastAPI side the publish path is confluent-kafka, the librdkafka-backed producer this book reaches for. The next slide is the publisher.");
}

/* --- publisher code --- */
{
  const s = S();
  addCodeSlide(s, "CONTRACTS", "The CloudEvents publisher (confluent-kafka)", "python · FastAPI",
    [
      "def publish_confirmed(confirmed: Booking, previous_status: BookingStatus) -> None:",
      "    try:",
      "        data = BookingEvent(bookingId=confirmed.id, status=BookingStatus.CONFIRMED,",
      "            previousStatus=previous_status, origin=confirmed.origin,",
      "            destination=confirmed.destination, occurredAt=_now_utc())",
      "        envelope = {'specversion': '1.0', 'id': f'evt_{generate_ulid()}',",
      "            'source': '/shipping/bookings',",
      "            'type': 'dev.patterncatalyst.shipping.booking.confirmed',",
      "            'subject': confirmed.id, 'time': _now_utc(),",
      "            'datacontenttype': 'application/json',",
      "            'data': data.model_dump(mode='json', exclude_none=True)}",
      "        producer.produce(TOPIC, value=json.dumps(envelope).encode())",
      "        producer.flush(10)                    # bounded wait for the ack",
      "    except Exception:",
      "        logger.exception('failed to publish')  # never surfaced on the REST response",
    ],
    "data is the shared BookingEvent (same $defs/Location as the REST Booking); a failed publish is logged, never a 5xx.",
    { fontSize: 10 });
  addNotes(s, "The FastAPI publisher, and it's the shared-schema thesis in Python. It builds the data payload as a BookingEvent — the shared-schema type carrying bookingId, the new status, the previousStatus, origin, and destination — and those origin and destination values are the same Location type the REST Booking uses, which is what guarantees the sync and async views can't drift. Then it builds the CloudEvents envelope by hand — specversion, a unique evt_ id, the source, the reverse-DNS type, subject set to the booking id, and the data payload — because the point is the envelope shape, not an SDK's conveniences, and the envelope is byte-for-byte the shape the Quarkus publisher produces. It serializes to JSON, produces to the topic via confluent-kafka, and calls flush with a ten-second bound to block until the broker acks, so a caller running this off the request thread knows the event landed. The except block is the production-critical detail, identical in spirit to Quarkus: a failed publish is logged and swallowed, never raised, because this runs after the synchronous REST response has already gone out — a Kafka outage must degrade the event stream, not turn a successful confirmation into an error. Two stacks, two Kafka libraries — SmallRye Reactive Messaging and confluent-kafka — one identical envelope and one shared schema.");
}

/* ======================= DIVIDER 09 ======================= */
divider("09", "Testing & running it",
  "pytest + TestClient, the test pyramid, and the three tiers.",
  "Proving the FastAPI implementation honours the contract: an in-process pytest layer with TestClient, inside the shared test pyramid, and then running the same image from Compose to minikube to OpenShift.");

/* --- test pyramid diagram --- */
{
  const s = S();
  addDiagramSlide(s, "TESTING", "The test pyramid",
    "r24-test-pyramid",
    "pytest + TestClient is the in-process integration layer; contract lint, the shared Newman collection, and load sit around it.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "The shared test pyramid, with the FastAPI layer named. The base is contract lint plus schema validation of responses. The integration layer is pytest with FastAPI's TestClient — an in-process test. Above that, the API/end-to-end layer runs the same shared Newman collection against the running service, so the identical assertions run against both the FastAPI and the Quarkus deployments. A load pass on top. Every layer checks the same contract from a different angle, which is what keeps the two stacks interchangeable. The next slide is the pytest layer.");
}

/* --- pytest TestClient --- */
{
  const s = S();
  addCodeSlide(s, "TESTING", "pytest + TestClient, in-process", "python · FastAPI",
    [
      "from fastapi.testclient import TestClient",
      "from app.main import app",
      "",
      "@pytest.fixture",
      "def client():",
      "    return TestClient(app)              # httpx against the ASGI app, no network",
      "",
      "def test_create_booking_returns_201_with_location_and_body(client):",
      "    resp = client.post('/bookings', json=VALID_BOOKING)",
      "    assert resp.status_code == 201",
      "    assert BOOKING_ID_RE.match(resp.json()['id'])",
      "    assert resp.headers['location'] == f\"/bookings/{resp.json()['id']}\"",
      "    assert resp.json()['quote'] == {'currency': 'USD', 'amount': '3001.25'}",
    ],
    "TestClient drives the ASGI app in-process (no running container); asserts status, headers, and body — the full contract.",
    { fontSize: 11 });
  addNotes(s, "The pytest layer, the symmetric counterpart to the Quarkus @QuarkusTest. FastAPI's TestClient runs httpx directly against the ASGI app in-process — no network, no running container — so it exercises the real app wiring but fast. The test posts a valid booking and asserts the full HTTP contract: 201, a booking id matching the pattern, the relative Location header, and the computed quote down to the exact decimal string. There's an autouse fixture, not shown here, that resets the in-memory store between tests so state doesn't leak. Notice the assertions are the same facts the Quarkus RestAssured test checks — same quote amount, same Location shape, same id pattern — because both are verifying the one shared contract. And the same operational note as the Quarkus side: this pytest suite is the local and build-time layer, symmetric with @QuarkusTest, while the live-container contract checks and the shared Newman collection are what run in CI. Both are real layers of the pyramid; they just run in different places. This is what 'two interchangeable implementations' actually rests on — the same assertions passing against both.");
}

/* --- running it --- */
{
  const s = S();
  addDiagramSlide(s, "RUNNING IT", "One image across three tiers",
    "r25-deployment-tiers",
    "The same FastAPI image on uvicorn: Compose → minikube → OpenShift Local. UBI base images; restricted-v2 on CRC.",
    { x: 1.30, y: 1.70, w: 10.73, h: 4.55 });
  addNotes(s, "Running the FastAPI service across the three tiers, with the Python specifics. Tier one, Docker or Podman Compose, brings the service up on uvicorn alongside Postgres and Kafka plus the LGTM observability stack for tracing from the first run. Tier two is minikube with standard Deployments, Services, and Ingress; tier three is OpenShift Local with Routes, BuildConfig, and the restricted-v2 security context constraint — which the Python image satisfies by running as a non-root user on a UBI base image pinned to an exact tag. The deployment shape is deliberately identical to the Quarkus service — same tiers, same manifests, same observability — because the whole series holds the house rule: examples run on plain infrastructure, Docker Engine on a Fedora or RHEL workstation, plain minikube, OpenShift Local, no managed cloud on the primary path. The runtime differs — uvicorn and CPython rather than the JVM or a native binary — but the operational story is the same, which is exactly what makes the two stacks drop-in alternatives behind the one contract.");
}

/* ======================= DIVIDER 10 ======================= */
divider("10", "Ecosystem & wrap-up",
  "The FastAPI ecosystem for work past plain request/response — and where to go deeper.",
  "Beyond REST itself, the Python ecosystem pieces that come up as a service grows, then where to go next.");

/* --- ecosystem --- */
{
  const s = S();
  addContentTitle(s, "ECOSYSTEM", "The FastAPI ecosystem");
  addBullets(s, [
    "Generated OpenAPI: FastAPI emits /openapi.json and interactive docs from the Pydantic models — and supports native webhooks for the push side.",
    "Async drivers make async def pay off: asyncpg for Postgres, httpx for outbound HTTP, an async Kafka client — await, don't block.",
    "Durable background work: when BackgroundTasks isn't enough (survive a crash, retry with backoff, inspect), reach for Celery or ARQ.",
    "CPU-bound work: offloading to the threadpool won't parallelize it under the GIL — use multiple processes or a C extension that drops it.",
  ], { fontSize: 16 });
  addCaption(s, "FastAPI generates the contract surface and shines at async I/O; reach past it deliberately for durability and true parallelism.");
  addNotes(s, "The FastAPI ecosystem, the counterpart to the Quarkus ecosystem slide. First, generated OpenAPI: FastAPI emits /openapi.json and the interactive Swagger and ReDoc UIs straight from the Pydantic models, so the documentation is generated from the same types that validate requests — it can't drift from the implementation — and FastAPI also has native support for declaring webhooks, the push side of an API, in that same generated schema. Second, async drivers are what make async def pay off: asyncpg for Postgres, httpx for outbound HTTP, an async Kafka client — these are what you await so the handler cooperates with the loop, and reaching for a blocking driver inside async def is the trap the ASGI section warned about. Third, durable background work: BackgroundTasks is fine for fire-and-forget in-process work, but the moment it must survive a crash, retry with backoff, or be inspected independently, you reach for a real task queue — Celery backed by Redis or RabbitMQ, or ARQ for a lighter asyncio-native option, the Python equivalent of Quarkus's JobRunr. Fourth, the honest limit: CPU-bound work won't parallelize on the threadpool under the GIL — that needs multiple processes or a C extension that drops it. FastAPI generates the contract surface and shines at async I/O; reach past it deliberately for durability and true parallelism.");
}

/* --- wrap --- */
{
  const s = S();
  addContentTitle(s, "WRAP-UP", "FastAPI, pattern by pattern");
  addBullets(s, [
    "ASGI: async def on the loop for awaitable I/O, plain def in the threadpool for blocking work — decided per endpoint.",
    "Pydantic v2 models + an exception handler: declarative DTOs, every failure application/problem+json.",
    "StreamingResponse / BackgroundTasks: incremental responses and deferred work, both on the event loop.",
    "confluent-kafka: CloudEvents to Kafka off the request thread, typed by the shared schema.",
    "Go deeper: examples/*/python/**, Chapter 23, and the Quarkus companion deck for the other stack.",
  ], { fontSize: 16 });
  addNotes(s, "Pulling the FastAPI story together. The defining concern is the ASGI execution model — async def on the event loop for awaitable I/O, plain def offloaded to the threadpool for blocking work, decided per endpoint by asking what the handler blocks on. The resource layer is Pydantic v2 models as DTOs with Field constraints that mirror the shared schema, and an @app.exception_handler plus a shared helper that guarantee every failure, framework-raised or deliberate, comes back as application/problem+json. The streaming story is StreamingResponse for incremental responses and BackgroundTasks for deferred work, both living on the one event loop. And the event side is confluent-kafka, publishing a CloudEvents envelope off the request thread, typed by the same shared schema as the REST Booking so the two protocols can't drift. All of it is real code in examples slash star slash python, expanded in Chapter 23. To see the identical patterns in the other stack, the Quarkus companion deck is where to go.");
}

/* --- Q&A --- */
{
  const s = S();
  addContentTitle(s, "THANK YOU", "Q&A");
  addBullets(s, [
    "Questions on any of it — ASGI dispatch, Pydantic, StreamingResponse, BackgroundTasks, the Kafka publisher, pytest?",
    "Code: examples/*/python/** · deep-dive: _docs/23-fastapi-in-depth.md · github.com/patterncatalyst/api-patterns-and-practices-rest",
  ], { fontSize: 16 });
  addCaption(s, "Red Hat is the world's leading provider of enterprise open source software solutions — trusted by the Fortune 500 for support, training, and consulting.");
  addNotes(s, "Thank you. That's every pattern from the 100-level deck, built in FastAPI: the ASGI model and the async-def-versus-plain-def decision, the Pydantic v2 models and the exception-handler Problem shape, content negotiation and merge-patch, keyset pagination, the async operation, HATEOAS links from the lifecycle state machine, media-type versioning, soft deletion, StreamingResponse and BackgroundTasks, and the CloudEvents-over-Kafka publisher on confluent-kafka — all tested with pytest and TestClient and runnable from a laptop to OpenShift. And the recurring theme across all three decks: the same contract, the same domain, the same wire behaviour, reached by two very different runtimes — which is exactly what lets a team pick the stack that fits and know the API behaves identically. I'm happy to take questions on any of it. All the code is under examples slash star slash python, the deep-dive is Chapter 23, and the whole project is public on the Pattern Catalyst GitHub organization. And the standard Red Hat close: Red Hat is the world's leading provider of enterprise open source software solutions, trusted by the Fortune 500 for award-winning support, training, and consulting services.");
}

/* ======================= APPENDIX A ======================= */
divider("A", "Appendix — extra FastAPI code",
  "Reference listings kept out of the main flow: PUT idempotency and the cargo sub-resource.",
  "Appendix material — keep it open in another window rather than reading front to back. These round out the examples but would slow the main narrative.");

/* --- PUT idempotency --- */
{
  const s = S();
  addCodeSlide(s, "APPENDIX A · METHODS", "PUT: full replace, made idempotent", "python · FastAPI",
    [
      "@app.put('/bookings/{booking_id}')",
      "def replace_booking(booking_id: str, payload: BookingRequest) -> JSONResponse:",
      "    existing = store.get(booking_id)",
      "    if existing is None: return _problem(404, 'Booking not found', ...)",
      "    # Deterministic cargo ids keyed on (bookingId, index): PUT must be",
      "    # idempotent, so the SAME body twice yields the SAME ids.",
      "    cargo_items = [Cargo(id=f'crg_{generate_deterministic_ulid(f\"{booking_id}:{i}\")}',",
      "                        **item.model_dump()) for i, item in enumerate(payload.cargo)]",
      "    updated = Booking(id=existing.id, status=existing.status,",
      "        origin=payload.origin, destination=payload.destination, cargo=cargo_items,",
      "        quote=compute_quote(cargo_items), requestedPickup=payload.requestedPickup,",
      "        createdAt=existing.createdAt, updatedAt=_now_utc())",
      "    store.put(updated); return _json(200, updated)",
    ],
    "POST mints random cargo ids; PUT mints deterministic ones so a repeated identical PUT lands byte-identical state.",
    { fontSize: 10 });
  addNotes(s, "An appendix detail easy to get wrong: making PUT genuinely idempotent, and it's the exact mirror of the Quarkus appendix slide. PUT is a full replacement, and the idempotency matrix requires that replacing a booking with the same body twice lands the same state both times. The subtlety is cargo ids: POST correctly mints a fresh random ULID per cargo item, but if PUT did the same, replacing with an identical body twice would produce different ids and the second response wouldn't byte-match the first. So replace_booking uses generate_deterministic_ulid keyed on the booking id and the item index, so the same body always yields the same ids. It also preserves the existing id, status, and createdAt — only client-supplied fields and updatedAt change. This is exactly the kind of correctness detail the shared idempotency tests catch, and showing both the Python and Quarkus versions side by side makes the point that 'PUT is idempotent' is something you implement deliberately, identically, in both stacks.");
}

/* --- cargo sub-resource --- */
{
  const s = S();
  addCodeSlide(s, "APPENDIX A · RESOURCES", "The cargo sub-resource", "python · FastAPI",
    [
      "@app.post('/bookings/{booking_id}/cargo')",
      "def add_cargo(booking_id: str, payload: CargoRequest) -> JSONResponse:",
      "    booking = store.get(booking_id)",
      "    if booking is None: return _problem(404, 'Booking not found', ...)",
      "    cargo = Cargo(id=f'crg_{generate_ulid()}', **payload.model_dump())",
      "    new_cargo_list = [*booking.cargo, cargo]",
      "    updated = booking.model_copy(update={'cargo': new_cargo_list,",
      "        'quote': compute_quote(new_cargo_list), 'updatedAt': _now_utc()})",
      "    store.put(updated)",
      "    return _json(201, cargo, headers={'Location': f'/bookings/{booking_id}/cargo/{cargo.id}'})",
    ],
    "Cargo nests under its booking (genuine ownership); adding one recomputes the quote and 201s with a nested Location.",
    { fontSize: 11 });
  addNotes(s, "The cargo sub-resource in FastAPI, as an appendix reference and the mirror of the Quarkus one. Cargo lives at /bookings/{id}/cargo because it genuinely belongs to a booking — the 'nest when it reads as ownership' guidance in code. add_cargo validates the CargoRequest automatically via the type annotation, mints a crg_ id, appends it to the booking's cargo list, uses model_copy to produce the updated booking with a recomputed quote — because adding cargo changes the price — persists, and returns 201 with a Location pointing at the nested cargo URI. One level of nesting, the sweet spot; deeper than that and the guidance was links instead. The model_copy call is the idiomatic Pydantic way to do the update, versus the Quarkus side constructing a new record — same result, same contract.");
}

pres.writeFile({ fileName: OUT })
  .then((p) => console.log("WROTE", p, "slides:", pageNum))
  .catch((e) => { console.error(e); process.exit(1); });
