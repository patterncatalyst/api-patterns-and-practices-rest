#!/usr/bin/env python3
"""Fig 10 — Ch10: the async 202 → poll → 303 lifecycle. A client kicks off a
long-running confirmation, polls the operation resource while it runs, and is
redirected to the real resource once it lands; a cancel branch shows the
operation can be aborted while still pending."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 960, 780

nodes = [
    {"x": 350, "y": 20, "w": 260, "h": 70,
     "lines": ["Client", "POST /bookings/{id}/confirmation"], "style": "user"},
    {"x": 350, "y": 130, "w": 260, "h": 90,
     "lines": ["Server", "202 Accepted", "Location: /operations/{opId}"], "style": "accent"},
    {"x": 350, "y": 270, "w": 260, "h": 70,
     "lines": ["Client", "GET /operations/{opId}"], "style": "user"},
    {"x": 350, "y": 380, "w": 260, "h": 70,
     "lines": ["200 OK", "status: RUNNING"], "style": "box"},
    {"x": 350, "y": 490, "w": 260, "h": 90,
     "lines": ["303 See Other", "Location: /bookings/{id}", "operation status: SUCCEEDED"], "style": "accent"},
    {"x": 350, "y": 630, "w": 260, "h": 70,
     "lines": ["Confirmed booking", "GET /bookings/{id} → 200 CONFIRMED"], "style": "ink"},

    {"x": 40, "y": 270, "w": 260, "h": 70,
     "lines": ["Client", "DELETE /operations/{opId}"], "style": "user"},
    {"x": 40, "y": 380, "w": 260, "h": 70,
     "lines": ["204 No Content", "operation status: CANCELLED"], "style": "box"},
]

edges = [
    {"x1": 480, "y1": 90, "x2": 480, "y2": 130, "label": "start async op"},
    {"x1": 480, "y1": 220, "x2": 480, "y2": 270, "label": "poll"},
    {"x1": 480, "y1": 340, "x2": 480, "y2": 380, "label": "GET"},
    {"x1": 615, "y1": 405, "x2": 615, "y2": 300, "label": "poll again (Retry-After)", "lx": 0, "ly": 0, "dashed": True},
    {"x1": 480, "y1": 450, "x2": 480, "y2": 490, "label": "terminal state"},
    {"x1": 480, "y1": 580, "x2": 480, "y2": 630, "label": "303 + Location"},

    {"x1": 350, "y1": 190, "x2": 300, "y2": 275, "label": "cancel instead", "amber": True, "dashed": True},
    {"x1": 170, "y1": 340, "x2": 170, "y2": 380, "label": "DELETE"},
]

notes = [
    {"x": 480, "y": 745, "text": "The operation resource is a progress marker, not the booking itself — the final 303 redirects the client to the real resource.",
     "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True},
]

generate_diagram.emit("10-async-lifecycle", W, H, nodes=nodes, edges=edges, notes=notes)
