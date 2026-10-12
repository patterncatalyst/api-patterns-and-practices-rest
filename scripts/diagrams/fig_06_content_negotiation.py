#!/usr/bin/env python3
"""Fig 06 — Ch6: content negotiation. A request's Accept/Content-Type headers
flow into the server's negotiation step, which branches to 200 (match), 406
(Accept unsatisfiable), or 415 (Content-Type unsupported); plus a map of the
key status codes used across the API."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 900, 620

nodes = [
    {"x": 310, "y": 20, "w": 280, "h": 100,
     "lines": ["Client request", "GET /bookings/42",
               "Accept: application/json", "Content-Type: application/json"],
     "style": "user"},

    {"x": 330, "y": 160, "w": 240, "h": 80,
     "lines": ["Server", "negotiate representation"], "style": "ink"},

    {"x": 40, "y": 290, "w": 250, "h": 110,
     "lines": ["Accept satisfiable", "200 OK",
               "Content-Type: negotiated media type", "body = representation"],
     "style": "accent"},
    {"x": 330, "y": 290, "w": 240, "h": 110,
     "lines": ["Accept not satisfiable", "406 Not Acceptable",
               "no representation the server offers matches"],
     "style": "box"},
    {"x": 610, "y": 290, "w": 250, "h": 110,
     "lines": ["Content-Type unsupported", "415 Unsupported Media Type",
               "server can't parse the request body"],
     "style": "box"},
]

edges = [
    {"x1": 450, "y1": 120, "x2": 450, "y2": 160, "label": "negotiate"},
    {"x1": 400, "y1": 240, "x2": 165, "y2": 290, "label": "match"},
    {"x1": 450, "y1": 240, "x2": 450, "y2": 290, "label": "no match", "amber": True, "dashed": True},
    {"x1": 500, "y1": 240, "x2": 735, "y2": 290, "label": "unsupported", "amber": True, "dashed": True},
]

bands = [
    {"x": 10, "y": 430, "w": 880, "h": 150, "label": "Key status codes", "fill": "#fafafa"},
]

CODES = [
    ("200 OK", "representation returned"),
    ("201 Created", "Location header; resource created"),
    ("204 No Content", "success, empty body"),
    ("400 Bad Request", "malformed request"),
    ("404 Not Found", "no such resource"),
    ("409 Conflict", "state conflict (e.g. version)"),
]

code_w, gap, start_x, y = 135, 8, 25, 470
for i, (code, detail) in enumerate(CODES):
    x = start_x + i * (code_w + gap)
    nodes.append({"x": x, "y": y, "w": code_w, "h": 100,
                  "lines": [code, detail], "style": "box"})

generate_diagram.emit("06-content-negotiation", W, H, bands=bands, nodes=nodes, edges=edges)
