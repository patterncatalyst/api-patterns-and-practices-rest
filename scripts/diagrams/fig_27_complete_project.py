#!/usr/bin/env python3
"""Fig 27 — Ch27: the complete project, one glance. A shared contract/schema
feeds both stacks; the booking lifecycle (POST -> async 202 confirm -> poll
-> 303 see-other); a background CloudEvents BookingEvent stream over Kafka;
an Arazzo workflow tying booking -> routing -> tracking; LGTM tracing across
all of it; and the capability tags this book built up (keyset pagination,
HATEOAS, media-type versioning, soft-delete+purge, NDJSON manifest)."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 760

bands = [
    {"x": 20, "y": 20, "w": 900, "h": 90, "label": "shared contract", "fill": "#fff8ef"},
    {"x": 20, "y": 130, "w": 430, "h": 160, "label": "Quarkus stack", "fill": "#fafafa"},
    {"x": 470, "y": 130, "w": 450, "h": 160, "label": "Python stack", "fill": "#fafafa"},
    {"x": 20, "y": 310, "w": 900, "h": 140, "label": "booking lifecycle", "fill": "#fafafa"},
    {"x": 20, "y": 470, "w": 440, "h": 110, "label": "async event stream", "fill": "#fafafa"},
    {"x": 480, "y": 470, "w": 440, "h": 110, "label": "cross-service workflow", "fill": "#fafafa"},
    {"x": 20, "y": 600, "w": 900, "h": 80, "label": "observability", "fill": "#fff8ef"},
]

nodes = [
    {"x": 50, "y": 50, "w": 840, "h": 50,
     "lines": ["OpenAPI + AsyncAPI + CloudEvents schema — one source of truth"], "style": "accent"},

    {"x": 50, "y": 170, "w": 180, "h": 60, "lines": ["booking-api", "Quarkus REST + Panache"], "style": "box"},
    {"x": 250, "y": 170, "w": 180, "h": 60, "lines": ["routing-api", "Quarkus gRPC"], "style": "box"},
    {"x": 50, "y": 240, "w": 380, "h": 40, "lines": ["GraphQL CQRS read model"], "style": "sub"},

    {"x": 500, "y": 170, "w": 180, "h": 60, "lines": ["tracking-api", "FastAPI REST"], "style": "box"},
    {"x": 700, "y": 170, "w": 200, "h": 60, "lines": ["manifest export", "NDJSON streaming"], "style": "box"},
    {"x": 500, "y": 240, "w": 400, "h": 40, "lines": ["keyset pagination + HATEOAS + media-type versioning"], "style": "sub"},

    {"x": 50, "y": 345, "w": 180, "h": 60, "lines": ["POST /bookings", "202 Accepted"], "style": "user"},
    {"x": 260, "y": 345, "w": 180, "h": 60, "lines": ["GET /bookings/{id}", "poll job status"], "style": "user"},
    {"x": 470, "y": 345, "w": 180, "h": 60, "lines": ["303 See Other", "-> booking resource"], "style": "accent"},
    {"x": 680, "y": 345, "w": 200, "h": 60, "lines": ["soft-delete + purge", "lifecycle on the resource"], "style": "box"},

    {"x": 50, "y": 505, "w": 160, "h": 55, "lines": ["BookingEvent", "CloudEvents envelope"], "style": "accent"},
    {"x": 240, "y": 505, "w": 100, "h": 55, "lines": ["Kafka"], "style": "sub"},
    {"x": 370, "y": 505, "w": 70, "h": 55, "lines": ["consumers"], "style": "sub"},

    {"x": 510, "y": 505, "w": 120, "h": 55, "lines": ["Arazzo", "workflow doc"], "style": "accent"},
    {"x": 650, "y": 505, "w": 90, "h": 25, "lines": ["booking"], "style": "sub"},
    {"x": 650, "y": 535, "w": 90, "h": 25, "lines": ["routing"], "style": "sub"},
    {"x": 760, "y": 505, "w": 90, "h": 25, "lines": ["tracking"], "style": "sub"},

    {"x": 50, "y": 630, "w": 840, "h": 40,
     "lines": ["OTLP traces from every request, across both stacks, into the LGTM stack"], "style": "accent"},
]

edges = [
    {"x1": 470, "y1": 100, "x2": 240, "y2": 170, "dashed": True},
    {"x1": 470, "y1": 100, "x2": 700, "y2": 170, "dashed": True},

    {"x1": 230, "y1": 375, "x2": 260, "y2": 375, "label": "job id"},
    {"x1": 440, "y1": 375, "x2": 470, "y2": 375, "label": "done", "amber": True},
    {"x1": 650, "y1": 375, "x2": 680, "y2": 375},

    {"x1": 210, "y1": 532, "x2": 240, "y2": 532, "amber": True},
    {"x1": 340, "y1": 532, "x2": 370, "y2": 532, "amber": True},

    {"x1": 630, "y1": 517, "x2": 650, "y2": 517},
    {"x1": 630, "y1": 547, "x2": 650, "y2": 547},
    {"x1": 630, "y1": 517, "x2": 760, "y2": 517},

    {"x1": 140, "y1": 405, "x2": 140, "y2": 505, "dashed": True},
    {"x1": 595, "y1": 405, "x2": 595, "y2": 505, "dashed": True},

    {"x1": 440, "y1": 600, "x2": 440, "y2": 630, "amber": True},
]

notes = [
    {"x": W / 2, "y": 710, "size": 12, "color": "#1d1d1d", "anchor": "middle",
     "text": "Every capability built across Parts 1-10 — pagination, HATEOAS, versioning, soft-delete, streaming manifests — lands in this one project, on both stacks, against the same contract."},
    {"x": W / 2, "y": 740, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
     "text": "One contract, one lifecycle, one event stream, one workflow, one trace — the whole book in a single, both-stack system."},
]

generate_diagram.emit("27-complete-project", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
