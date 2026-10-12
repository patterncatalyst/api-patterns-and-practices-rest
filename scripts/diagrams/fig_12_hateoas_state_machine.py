#!/usr/bin/env python3
"""Fig 12 — Ch12: the booking response as a finite state machine. Each state
exposes only the `_links` that are valid transitions from there — the state
machine lives in the payload, not in client-side logic."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 980, 600

nodes = [
    {"x": 40, "y": 120, "w": 180, "h": 90,
     "lines": ["PENDING", "_links: self, confirm,", "cancel"], "style": "accent"},
    {"x": 280, "y": 120, "w": 180, "h": 90,
     "lines": ["CONFIRMED", "_links: self, cancel"], "style": "box"},
    {"x": 520, "y": 120, "w": 180, "h": 90,
     "lines": ["IN_TRANSIT", "_links: self"], "style": "box"},
    {"x": 760, "y": 120, "w": 180, "h": 90,
     "lines": ["DELIVERED", "_links: self only", "(terminal)"], "style": "ink"},

    {"x": 160, "y": 280, "w": 180, "h": 90,
     "lines": ["CANCELLED", "_links: self only", "(terminal)"], "style": "ghost"},

    {"x": 460, "y": 420, "w": 480, "h": 150,
     "lines": ["Sample response (PENDING)",
               "{ \"status\": \"PENDING\",",
               "  \"_links\": {",
               "    \"self\":    { \"href\": \"/bookings/42\" },",
               "    \"confirm\": { \"href\": \".../confirmation\", \"method\": \"POST\" },",
               "    \"cancel\":  { \"href\": \"/bookings/42\", \"method\": \"DELETE\" } } }"],
     "style": "sub"},
]

edges = [
    {"x1": 220, "y1": 165, "x2": 280, "y2": 165, "label": "confirm"},
    {"x1": 460, "y1": 165, "x2": 520, "y2": 165, "label": "dispatch"},
    {"x1": 700, "y1": 165, "x2": 760, "y2": 165, "label": "deliver"},
    {"x1": 140, "y1": 210, "x2": 200, "y2": 280, "label": "cancel", "amber": True, "dashed": True},
    {"x1": 360, "y1": 210, "x2": 300, "y2": 280, "label": "cancel", "amber": True, "dashed": True},
]

notes = [
    {"x": 490, "y": 60, "text": "HATEOAS: the response's _links enumerate only the transitions valid from the current state — the state machine lives in the payload.",
     "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True},
]

generate_diagram.emit("12-hateoas-state-machine", W, H, nodes=nodes, edges=edges, notes=notes)
