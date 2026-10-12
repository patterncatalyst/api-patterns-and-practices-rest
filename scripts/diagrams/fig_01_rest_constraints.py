#!/usr/bin/env python3
"""Fig 01 — Ch1: RPC/verb-oriented vs Web API/resource-oriented, plus the five
REST constraints with uniform interface emphasized."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 920, 420

nodes = [
    {"x": 60, "y": 40, "w": 360, "h": 100,
     "lines": ["RPC / verb-oriented", "POST /getBooking", "POST /cancelBooking",
               "verbs in the URL"], "style": "ghost"},
    {"x": 500, "y": 40, "w": 360, "h": 100,
     "lines": ["Web API / resource-oriented", "GET /bookings/{id}",
               "DELETE /bookings/{id}", "nouns + HTTP methods"], "style": "box"},

    {"x": 35, "y": 230, "w": 150, "h": 120,
     "lines": ["Client–server", "UI decoupled from", "data storage"], "style": "box"},
    {"x": 210, "y": 230, "w": 150, "h": 120,
     "lines": ["Stateless", "no client session", "kept on the server"], "style": "box"},
    {"x": 385, "y": 230, "w": 150, "h": 120,
     "lines": ["Cacheable", "responses declare", "their own freshness"], "style": "box"},
    {"x": 560, "y": 230, "w": 150, "h": 120,
     "lines": ["Uniform interface", "resources named,", "verbs standardized"], "style": "accent"},
    {"x": 735, "y": 230, "w": 150, "h": 120,
     "lines": ["Layered system", "gateways & caches", "stay transparent"], "style": "box"},
]

edges = [
    {"x1": 680, "y1": 140, "x2": 635, "y2": 230, "amber": True,
     "label": "REST constraints (Fielding)", "lx": 10, "ly": -10},
]

notes = [
    {"x": 480, "y": 95, "text": "vs", "size": 13, "color": "#555555", "anchor": "middle", "bold": True},
    {"x": 635, "y": 375, "text": "Most REST APIs are built on client-server + stateless,",
     "size": 11, "color": "#555555", "anchor": "middle"},
    {"x": 635, "y": 390, "text": "but violate the uniform interface — the constraint that matters most.",
     "size": 11, "color": "#b8650a", "anchor": "middle"},
]

generate_diagram.emit("01-rest-constraints", W, H, nodes=nodes, edges=edges, notes=notes)
