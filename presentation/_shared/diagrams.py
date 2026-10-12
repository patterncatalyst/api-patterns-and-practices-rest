"""
diagrams.py — Scene diagrams for the "API Patterns & Practices: REST" 101 deck.

Shipping / cargo domain (NOT coffee-shop). Authored against the site's figures
and contracts (contracts/openapi/shipping-api.yaml, contracts/schemas/shipping.schema.json,
_plans/domain-glossary.md). Run:  python3 build_diagrams.py

Color by role (dgen PALETTE):
  rest=API surface  svc=clients/services  data=stores/schema  platform=infra/runtime
  govern=policy/lifecycle  danger=failure/terminal  neutral/muted=text
"""
from dgen import Scene, PALETTE


# --------------------------------------------------------------------------
def decision_axes():
    s = Scene("r02-decision-axes", width=1300, height=640,
              title="The API decision framework",
              subtitle="Read the interaction off seven axes before you pick the style — habit is not an axis.")
    s.panel(40, 110, 470, 500)
    s.label(64, 142, "The seven axes", size=15, weight="bold", color=PALETTE["rest"])
    axes = [
        "1 · Interaction shape  (req/resp · stream · event)",
        "2 · Payload size & shape",
        "3 · Latency & real-time need",
        "4 · Cacheability",
        "5 · Client diversity",
        "6 · Evolution & versioning needs",
        "7 · Operational constraints (proxies, CDN)",
    ]
    for i, a in enumerate(axes):
        s.label(64, 182 + i * 56, a, size=13, color=PALETTE["neutral"])

    s.box(590, 265, 210, 110, "Run the interaction",
          ["through all seven axes", "— let them point"], kind="rest")
    s.arrow(510, 350, 590, 330, kind="neutral")

    outs = [
        ("REST / HTTP", "resource-shaped, cacheable, diverse clients", "rest"),
        ("gRPC", "low-latency, typed, server-to-server", "svc"),
        ("GraphQL", "client-chosen projection of a graph", "data"),
        ("WebSockets", "bidirectional, long-lived session", "platform"),
        ("Events / webhooks", "fire-and-forget to unknown consumers", "govern"),
    ]
    for i, (t, sub, k) in enumerate(outs):
        y = 130 + i * 92
        s.box(900, y, 360, 66, t, [sub], kind=k)
        s.arrow(800, 320, 900, y + 33, kind="neutral")
    s.write()


# --------------------------------------------------------------------------
def idempotency_matrix():
    s = Scene("r05-idempotency-matrix", width=1300, height=560,
              title="HTTP methods: the safe / idempotent matrix",
              subtitle="Safe = no state change. Idempotent = repeating the call lands the same state.")
    methods = [
        ("GET", "yes", "yes", "Read a booking or a page."),
        ("POST", "no", "no", "Create; use Idempotency-Key to dedupe."),
        ("PUT", "no", "yes", "Replace the whole booking."),
        ("PATCH", "no", "no", "Partial update; idempotent only if you design it so."),
        ("DELETE", "no", "yes", "Cancel (soft-delete); repeat is a no-op."),
    ]
    col_x = [360, 540, 720, 900, 1080]
    # row labels
    s.label(70, 205, "Safe?", size=14, weight="bold", color=PALETTE["neutral"])
    s.label(70, 300, "Idempotent?", size=14, weight="bold", color=PALETTE["neutral"])
    s.label(70, 400, "On /bookings", size=13, weight="bold", color=PALETTE["muted"])
    for i, (m, safe, idem, note) in enumerate(methods):
        x = col_x[i]
        s.chip(x, 140, m, kind="rest", w=120)
        for row_y, val in ((190, safe), (285, idem)):
            kind = "platform" if val == "yes" else "danger"
            s.box(x, row_y, 120, 50, val.upper(), kind=kind)
        # per-method note, wrapped to two short lines
        words = note.split()
        mid = len(words) // 2 + 1
        s.label(x + 60, 400, " ".join(words[:mid]), size=10, color=PALETTE["muted"], anchor="middle")
        s.label(x + 60, 416, " ".join(words[mid:]), size=10, color=PALETTE["muted"], anchor="middle")
    s.panel(70, 470, 1160, 60)
    s.label(94, 505, "PUT and DELETE are idempotent by HTTP contract; POST and PATCH are not — "
                     "make unsafe creates safe to retry with an Idempotency-Key (IETF draft).",
            size=13, color=PALETTE["neutral"])
    s.write()


# --------------------------------------------------------------------------
def async_flow():
    s = Scene("r10-async-flow", width=1300, height=640,
              title="Asynchronous operations: 202 · poll · 303",
              subtitle="Confirmation runs routing + capacity checks that exceed one request/response.")
    cx, sx = 300, 820
    s.box(180, 96, 240, 54, "Client", kind="svc")
    s.box(700, 96, 240, 54, "Shipping API", kind="rest")
    s.divider(300, 150, 300, 600)
    s.divider(820, 150, 820, 600)

    def req(y, text):
        s.arrow(cx, y, sx, y, kind="rest")
        s.label(cx + 20, y - 8, text, size=12, color=PALETTE["neutral"])

    def resp(y, text, kind="svc"):
        s.arrow(sx, y, cx, y, kind=kind, dashed=True)
        s.label(sx - 20, y - 8, text, size=12, color=PALETTE["muted"], anchor="end")

    req(190, "POST /bookings/{id}/confirmation")
    resp(235, "202 Accepted  ·  Location: /operations/op_…")
    req(315, "GET /operations/op_…   (poll)")
    resp(360, "200  { status: RUNNING }")
    req(440, "GET /operations/op_…   (poll)")
    resp(485, "303 See Other  ·  Location: /bookings/{id}", kind="platform")
    req(560, "GET /bookings/{id}")
    resp(600, "200  { status: CONFIRMED }", kind="platform")

    s.panel(880, 300, 400, 110)
    s.label(904, 335, "Poll loop until the Operation", size=13, color=PALETTE["govern"])
    s.label(904, 360, "resolves. The Operation carries a", size=13, color=PALETTE["govern"])
    s.label(904, 385, "cancel link while it is RUNNING.", size=13, color=PALETTE["govern"])
    s.write()


# --------------------------------------------------------------------------
def pagination():
    s = Scene("r08-pagination", width=1300, height=600,
              title="Pagination: offset vs keyset vs seek",
              subtitle="Pick by consistency under writes, depth cost, and coupling to the sort.")
    rows = [
        ("Offset", "GET /bookings?limit=20&offset=100", "danger",
         "Simple. Slow at depth; page drift when rows are inserted."),
        ("Keyset", "GET /bookings?limit=20&createdAt:lte=2026-10-11T00:00:00Z", "govern",
         "Consistent + fast. Couples paging to the sort key / filters."),
        ("Seek", "GET /bookings?limit=20&cursor=…   (opaque)", "platform",
         "Opaque cursor decouples paging from filters. More backend work."),
    ]
    for i, (name, query, kind, note) in enumerate(rows):
        y = 120 + i * 150
        s.box(60, y, 200, 110, name, kind=kind)
        s.code_block(290, y, 640, 50, [query])
        s.label(290, y + 86, note, size=13, color=PALETTE["neutral"])
    s.panel(970, 120, 270, 410)
    s.label(994, 152, "Always:", size=13, weight="bold", color=PALETTE["rest"])
    for i, ln in enumerate([
        "• cap limit (DoS guard)",
        "• ship page metadata",
        "   (count, nextCursor)",
        "• sane defaults",
        "   (limit=20)",
        "• fields= for sparse",
        "   projections",
    ]):
        s.label(994, 190 + i * 34, ln, size=12, color=PALETTE["neutral"])
    s.write()


# --------------------------------------------------------------------------
def hateoas_fsm():
    s = Scene("r12-hateoas-fsm", width=1300, height=600,
              title="HATEOAS: links are the booking state machine",
              subtitle="The _links a response carries are exactly the transitions legal from its current state.")
    states = [
        (40, "PENDING", "svc"),
        (360, "CONFIRMED", "svc"),
        (680, "IN_TRANSIT", "svc"),
        (1000, "DELIVERED", "platform"),
    ]
    for x, name, kind in states:
        s.box(x, 150, 220, 80, name, kind=kind)
    s.arrow(260, 190, 360, 190, kind="rest", label="confirm")
    s.arrow(580, 190, 680, 190, kind="rest", label="load")
    s.arrow(900, 190, 1000, 190, kind="rest", label="deliver")

    s.box(470, 420, 220, 70, "CANCELLED", kind="danger")
    s.arrow(150, 230, 500, 420, kind="danger", label="cancel")
    s.arrow(470, 230, 600, 420, kind="danger", label="cancel")

    s.panel(760, 380, 480, 150)
    s.label(784, 412, "PENDING  ·  _links: { self, confirm, cancel }", size=13, color=PALETTE["neutral"])
    s.label(784, 442, "IN_TRANSIT  ·  _links: { self }", size=13, color=PALETTE["neutral"])
    s.label(784, 472, "DELIVERED  ·  _links: { self }  (terminal)", size=13, color=PALETTE["neutral"])
    s.label(784, 505, "The client follows links; it never hard-codes the FSM.",
            size=12, color=PALETTE["muted"])
    s.write()


# --------------------------------------------------------------------------
def multiprotocol():
    s = Scene("r21-multiprotocol", width=1300, height=640,
              title="Multi-protocol contracts around one shared schema",
              subtitle="Four contract languages $ref the same JSON Schema, so sync and async never drift.")
    s.box(530, 270, 240, 110, "shipping.schema.json",
          ["$defs: Booking, BookingEvent,", "Location, Money, Problem"], kind="data", mono=True)

    corners = [
        (100, 120, "OpenAPI 3.1", "synchronous request/response", "rest"),
        (960, 120, "AsyncAPI 3.0", "event channels (Kafka)", "svc"),
        (100, 450, "CloudEvents 1.0", "the event envelope", "govern"),
        (960, 450, "Arazzo 1.0.1", "multi-step workflow", "platform"),
    ]
    anchors = [(340, 160, 530, 290), (960, 160, 770, 290),
               (340, 490, 530, 360), (960, 490, 770, 360)]
    for (x, y, t, sub, k), (ax, ay, bx, by) in zip(corners, anchors):
        s.box(x, y, 240, 80, t, [sub], kind=k)
        s.arrow(ax, ay, bx, by, kind="neutral", label="$ref")

    s.panel(100, 575, 1100, 50)
    s.label(124, 605, "Governance tier:  published to Apicurio Registry (xRegistry touchpoint)  "
                      "·  catalogued in OpenMetadata.", size=13, color=PALETTE["govern"])
    s.write()


# --------------------------------------------------------------------------
def deployment_tiers():
    s = Scene("r25-deployment-tiers", width=1300, height=560,
              title="One artifact across three tiers",
              subtitle="The same container image and the same contract, from laptop to cluster to OpenShift.")
    tiers = [
        (40, "Docker / Podman Compose", ["app (Quarkus + FastAPI)", "Postgres · Kafka", "+ LGTM tracing"], "platform"),
        (490, "Kubernetes on minikube", ["Deployments · Services", "Ingress", "same image"], "platform"),
        (940, "OpenShift Local (CRC)", ["Routes · BuildConfig", "restricted-v2 SCC", "same image"], "platform"),
    ]
    for x, t, lines, k in tiers:
        s.box(x, 170, 320, 180, t, lines, kind=k)
    s.arrow(360, 260, 490, 260, kind="rest", label="promote")
    s.arrow(810, 260, 940, 260, kind="rest", label="promote")
    s.panel(40, 400, 1220, 90)
    s.label(64, 432, "Examples run on plain infrastructure: Docker Engine on a Fedora / RHEL workstation,",
            size=13, color=PALETTE["neutral"])
    s.label(64, 458, "unchanged on minikube and on OpenShift Local. No managed cloud on the primary path.",
            size=13, color=PALETTE["neutral"])
    s.write()


# --------------------------------------------------------------------------
def range_requests():
    s = Scene("r15-range", width=1300, height=560,
              title="Large binary resources: HEAD, Range, 206",
              subtitle="Fetch a multi-megabyte cargo manifest in resumable chunks.")
    cx, sx = 300, 820
    s.box(180, 96, 240, 54, "Client", kind="svc")
    s.box(700, 96, 240, 54, "Manifest resource", kind="rest")
    s.divider(300, 150, 300, 520)
    s.divider(820, 150, 820, 520)

    def req(y, text):
        s.arrow(cx, y, sx, y, kind="rest")
        s.label(cx + 20, y - 8, text, size=12, color=PALETTE["neutral"])

    def resp(y, text, kind="svc"):
        s.arrow(sx, y, cx, y, kind=kind, dashed=True)
        s.label(sx - 20, y - 8, text, size=12, color=PALETTE["muted"], anchor="end")

    req(200, "HEAD /bookings/{id}/manifest")
    resp(248, "200  Accept-Ranges: bytes  ·  Content-Length: 5242880")
    req(330, "GET  Range: bytes=0-1048575")
    resp(378, "206 Partial Content", kind="platform")
    resp(408, "Content-Range: bytes 0-1048575/5242880", kind="platform")
    req(468, "GET  Range: bytes=1048576-…   (resume)")
    s.write()


# --------------------------------------------------------------------------
def resource_model():
    s = Scene("r03-resource-model", width=1300, height=560,
              title="Design around resources (nouns, not verbs)",
              subtitle="Collections and items, nested where it reads as ownership — never mirror the DB.")
    s.box(60, 240, 300, 80, "/bookings", ["collection of bookings"], kind="rest")
    s.box(500, 160, 320, 80, "/bookings/{id}", ["one booking (item)"], kind="rest")
    s.box(500, 320, 320, 80, "/bookings/{id}/cargo", ["cargo under a booking"], kind="rest")
    s.arrow(360, 260, 500, 200, kind="neutral", label="GET item")
    s.arrow(360, 300, 500, 360, kind="neutral", label="sub-resource")

    s.panel(880, 150, 360, 300)
    s.label(904, 184, "Avoid", size=14, weight="bold", color=PALETTE["danger"])
    anti = [
        "·  /createBooking  (verb)",
        "·  mirroring table columns",
        "·  chatty API: many tiny GETs",
        "·  extraneous fetching",
    ]
    for i, ln in enumerate(anti):
        s.label(904, 218 + i * 30, ln, size=12, color=PALETTE["danger"])
    s.label(904, 358, "Do instead", size=14, weight="bold", color=PALETTE["platform"])
    good = [
        "·  nouns + HTTP methods",
        "·  links instead of deep nesting",
    ]
    for i, ln in enumerate(good):
        s.label(904, 392 + i * 30, ln, size=12, color=PALETTE["platform"])
    s.write()


# --------------------------------------------------------------------------
def quarkus_buildtime():
    s = Scene("r22-quarkus-buildtime", width=1300, height=600,
              title="Quarkus REST: build-time binding, not runtime reflection",
              subtitle="Resolve @RestHeader / @RestQuery / @RestPath once, at build — not on every request.")
    # Classic path (per request)
    s.panel(40, 120, 1220, 150)
    s.label(64, 150, "Classic JAX-RS — resolved by reflection, every request", size=13,
            weight="bold", color=PALETTE["danger"])
    s.box(70, 175, 230, 70, "Request", kind="danger")
    s.box(430, 175, 320, 70, "reflect: walk @HeaderParam,", ["Method.invoke() per call"], kind="danger")
    s.box(880, 175, 230, 70, "Handler", kind="danger")
    s.arrow(300, 210, 430, 210, kind="danger")
    s.arrow(750, 210, 880, 210, kind="danger")
    s.label(1130, 214, "every req", size=11, color=PALETTE["danger"])
    # Quarkus path
    s.panel(40, 300, 1220, 200)
    s.label(64, 330, "Quarkus REST — a build step generates the binding code once", size=13,
            weight="bold", color=PALETTE["platform"])
    s.box(70, 355, 300, 60, "BUILD: processor reads", ["@RestHeader / @RestQuery"], kind="govern")
    s.arrow(370, 385, 470, 385, kind="neutral", label="generates")
    s.box(470, 355, 300, 60, "bytecode:", ["request.getHeader(...)"], kind="platform", mono=True)
    s.box(70, 435, 230, 50, "Request", kind="svc")
    s.box(430, 435, 340, 50, "generated class (no reflection)", kind="platform")
    s.box(900, 435, 210, 50, "Handler", kind="platform")
    s.arrow(300, 460, 430, 460, kind="platform")
    s.arrow(770, 460, 900, 460, kind="platform")
    # payoff chips
    s.chip(830, 360, "fast start", kind="platform", w=110)
    s.chip(960, 360, "low memory", kind="platform", w=120)
    s.chip(1100, 360, "native-ready", kind="platform", w=130)
    s.write()


# --------------------------------------------------------------------------
def quarkus_reactive_ndjson():
    s = Scene("r22-reactive-ndjson", width=1300, height=560,
              title="Reactive NDJSON: a Multi pipeline, one line at a time",
              subtitle="Multi<String> streamed over the event loop — never buffered — through a dedicated writer.")
    s.box(40, 230, 220, 90, "Multi.ticks()", ["one tick every", "STREAM_INTERVAL"], kind="platform")
    s.box(310, 230, 230, 90, ".select().first(n)", ["clamp limit (DoS guard)"], kind="govern")
    s.box(590, 230, 240, 90, "toJsonLine(event)", ["one NDJSON line / tick"], kind="svc")
    s.box(880, 230, 250, 90, "@Provider writer", ["application/x-ndjson", "writes raw bytes"], kind="rest")
    s.box(1150, 245, 110, 60, "client", kind="svc")
    s.arrow(260, 275, 310, 275, kind="neutral")
    s.arrow(540, 275, 590, 275, kind="neutral")
    s.arrow(830, 275, 880, 275, kind="neutral")
    s.arrow(1130, 275, 1150, 275, kind="rest", label="flush")
    s.panel(40, 370, 1220, 110)
    s.label(64, 402, "Without a narrowly-scoped @Provider writer, Jackson wins the String lookup and",
            size=13, color=PALETTE["danger"])
    s.label(64, 426, "double-encodes each line as a quoted JSON string — breaking newline-delimited JSON.",
            size=13, color=PALETTE["danger"])
    s.label(64, 456, "Backpressure: the next item is produced only when the socket is ready to take it.",
            size=13, color=PALETTE["neutral"])
    s.write()


# --------------------------------------------------------------------------
def fastapi_asgi_dispatch():
    s = Scene("r23-asgi-dispatch", width=1300, height=600,
              title="FastAPI / ASGI: where each handler actually runs",
              subtitle="One uvicorn process, one event loop — async def on the loop, plain def in a threadpool.")
    s.panel(40, 110, 1220, 430)
    s.label(64, 142, "single uvicorn process", size=13, weight="bold", color=PALETTE["neutral"])
    # event loop
    s.box(90, 200, 360, 120, "event loop (main thread)",
          ["multiplexes many requests", "by yielding at each await"], kind="platform")
    s.box(90, 380, 360, 110, "async def handler",
          ["runs ON the loop", "await real I/O — cooperates"], kind="svc")
    s.arrow(270, 380, 270, 320, kind="svc", label="scheduled on")
    # threadpool
    s.box(840, 200, 370, 120, "AnyIO threadpool",
          ["bounded worker threads", "for blocking work"], kind="govern")
    s.box(840, 380, 370, 110, "plain def handler",
          ["offloaded via run_sync", "may block its own thread"], kind="govern")
    s.arrow(1025, 380, 1025, 320, kind="govern", label="offloaded to")
    s.label(650, 300, "Starlette inspects the", size=12, color=PALETTE["muted"], anchor="middle")
    s.label(650, 320, "handler: coroutine or not?", size=12, color=PALETTE["muted"], anchor="middle")
    s.label(650, 470, "GIL: blocking I/O releases it;", size=11, color=PALETTE["danger"], anchor="middle")
    s.label(650, 488, "CPU-bound work does not.", size=11, color=PALETTE["danger"], anchor="middle")
    s.write()


# --------------------------------------------------------------------------
def fastapi_bg_sse():
    s = Scene("r23-bg-sse", width=1300, height=560,
              title="StreamingResponse & BackgroundTasks on one loop",
              subtitle="Stream frames as they're yielded; defer work past the response — both on the event loop.")
    # SSE streaming
    s.panel(40, 120, 590, 360)
    s.label(64, 152, "StreamingResponse (SSE)", size=13, weight="bold", color=PALETTE["svc"])
    s.box(70, 185, 300, 70, "async generator", ["await sleep; yield frame"], kind="svc")
    s.arrow(370, 220, 470, 220, kind="svc")
    s.box(470, 185, 130, 70, "socket", ["flush now"], kind="rest")
    s.label(70, 300, "data: {...}\\n\\n   (t = 0.0s)", size=12, color=PALETTE["muted"], mono=True)
    s.label(70, 330, "data: {...}\\n\\n   (t = 0.25s)", size=12, color=PALETTE["muted"], mono=True)
    s.label(70, 360, "data: {...}\\n\\n   (t = 0.50s)", size=12, color=PALETTE["muted"], mono=True)
    s.label(70, 400, "each frame leaves as it is produced", size=12, color=PALETTE["neutral"])
    # BackgroundTasks
    s.panel(670, 120, 590, 360)
    s.label(694, 152, "BackgroundTasks (202 now, work later)", size=13, weight="bold", color=PALETTE["govern"])
    s.box(700, 190, 240, 70, "POST /notify", ["add_task(...)"], kind="svc")
    s.arrow(940, 225, 1050, 225, kind="rest", label="202 now")
    s.box(1050, 190, 180, 70, "client", kind="svc")
    s.box(700, 320, 240, 80, "deferred task", ["runs after response", "same event loop"], kind="govern")
    s.arrow(820, 260, 820, 320, kind="govern", label="later turn")
    s.label(700, 440, "202 Accepted is a promise: accepted, not yet done.", size=12, color=PALETTE["neutral"])
    s.write()


# --------------------------------------------------------------------------
def test_pyramid():
    s = Scene("r24-test-pyramid", width=1300, height=600,
              title="The test pyramid: every layer checks one contract",
              subtitle="Many fast checks at the base, fewer slow ones on top — all against the shared schema.")
    levels = [
        (720, 440, "Contract — lint + schema validation", "platform", "fast · many · drift fails CI"),
        (560, 360, "Integration — real Postgres & Kafka", "svc", "@QuarkusTest · pytest + TestClient"),
        (400, 280, "API / E2E — shared Newman collection", "govern", "same assertions, both stacks"),
        (240, 200, "Load — throughput under concurrency", "rest", "caps + async flow hold"),
    ]
    for w, y, title, kind, note in levels:
        x = (1300 - w) / 2 - 150
        s.box(x, y, w, 70, title, kind=kind)
        s.label(x + w + 30, y + 40, note, size=12, color=PALETTE["muted"])
    s.write()


SCENES = [
    decision_axes,
    idempotency_matrix,
    async_flow,
    pagination,
    hateoas_fsm,
    multiprotocol,
    deployment_tiers,
    range_requests,
    resource_model,
    quarkus_buildtime,
    quarkus_reactive_ndjson,
    fastapi_asgi_dispatch,
    fastapi_bg_sse,
    test_pyramid,
]


if __name__ == "__main__":
    for fn in SCENES:
        fn()
        print(f"  built {fn.__name__}")
