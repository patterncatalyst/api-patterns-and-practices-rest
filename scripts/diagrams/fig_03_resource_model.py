#!/usr/bin/env python3
"""Fig 03 — Ch3: the Booking→Cargo aggregate, and collection vs item vs
sub-resource URLs. Resources are nouns, not a mirror of the DB schema."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 900, 460

nodes = [
    {"x": 120, "y": 40, "w": 260, "h": 90,
     "lines": ["Booking", "aggregate root", "origin → destination"], "style": "accent"},
    {"x": 500, "y": 40, "w": 260, "h": 90,
     "lines": ["Cargo", "1..n per booking", "weight, volume, hazmat"], "style": "box"},

    {"x": 60, "y": 220, "w": 240, "h": 90,
     "lines": ["Collection", "GET/POST /bookings", "list & create"], "style": "box"},
    {"x": 340, "y": 220, "w": 240, "h": 90,
     "lines": ["Item", "GET/PUT/DELETE", "/bookings/{id}"], "style": "box"},
    {"x": 620, "y": 220, "w": 240, "h": 90,
     "lines": ["Sub-resource", "GET/POST", "/bookings/{id}/cargo"], "style": "box"},
]

edges = [
    {"x1": 380, "y1": 85, "x2": 500, "y2": 85, "label": "1..n"},
    {"x1": 250, "y1": 130, "x2": 180, "y2": 220, "label": "exposed as"},
    {"x1": 250, "y1": 130, "x2": 460, "y2": 220, "label": "exposed as"},
    {"x1": 630, "y1": 130, "x2": 740, "y2": 220, "label": "exposed as"},
    {"x1": 580, "y1": 265, "x2": 620, "y2": 265},
]

notes = [
    {"x": 450, "y": 420, "text": "Resources are nouns, not verbs —", "size": 12,
     "color": "#1a1a1a", "anchor": "middle", "bold": True},
    {"x": 450, "y": 438, "text": "and must not mirror the database tables underneath them.",
     "size": 11, "color": "#b8650a", "anchor": "middle"},
]

generate_diagram.emit("03-resource-model", W, H, nodes=nodes, edges=edges, notes=notes)
