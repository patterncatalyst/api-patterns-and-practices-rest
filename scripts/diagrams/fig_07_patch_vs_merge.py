#!/usr/bin/env python3
"""Fig 07 — Ch7: JSON Patch (RFC 6902) vs JSON Merge Patch (RFC 7396) applied
to the same Booking — an ordered array of operations vs a partial object
where null deletes a field — and the distinct media types each requires."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 900, 560

nodes = [
    {"x": 320, "y": 20, "w": 260, "h": 80,
     "lines": ["Booking (current state)", "status: pending", "notes: \"call on arrival\""],
     "style": "accent"},

    {"x": 60, "y": 150, "w": 360, "h": 70,
     "lines": ["JSON Patch — RFC 6902", "Content-Type: application/json-patch+json"],
     "style": "ink"},
    {"x": 60, "y": 240, "w": 360, "h": 120,
     "lines": ["array of operations", "{\"op\":\"replace\",\"path\":\"/status\",\"value\":\"confirmed\"}",
               "{\"op\":\"remove\",\"path\":\"/notes\"}"],
     "style": "box"},

    {"x": 480, "y": 150, "w": 360, "h": 70,
     "lines": ["JSON Merge Patch — RFC 7396", "Content-Type: application/merge-patch+json"],
     "style": "ink"},
    {"x": 480, "y": 240, "w": 360, "h": 120,
     "lines": ["partial object", "{\"status\":\"confirmed\",\"notes\":null}",
               "null means \"delete this field\""],
     "style": "box"},

    {"x": 320, "y": 420, "w": 260, "h": 80,
     "lines": ["Booking (updated)", "status: confirmed", "notes: removed"],
     "style": "accent"},
]

edges = [
    {"x1": 400, "y1": 100, "x2": 240, "y2": 150, "label": "PATCH (op list)"},
    {"x1": 500, "y1": 100, "x2": 660, "y2": 150, "label": "PATCH (partial obj)"},
    {"x1": 240, "y1": 360, "x2": 400, "y2": 420, "label": "apply ops in order"},
    {"x1": 660, "y1": 360, "x2": 500, "y2": 420, "label": "shallow-merge; null deletes"},
]

notes = [
    {"x": 450, "y": 525, "text": "JSON Patch: explicit, ordered operations — can target array elements and move/test fields.",
     "size": 11, "color": "#1a1a1a", "anchor": "middle"},
    {"x": 450, "y": 543, "text": "JSON Merge Patch: object-merge semantics only — simpler, but no array-element ops.",
     "size": 11, "color": "#b8650a", "anchor": "middle"},
]

generate_diagram.emit("07-patch-vs-merge", W, H, nodes=nodes, edges=edges, notes=notes)
