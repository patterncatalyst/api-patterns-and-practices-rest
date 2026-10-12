#!/usr/bin/env python3
"""Fig 09 — Ch9: when to nest a sub-resource (real ownership, e.g.
/bookings/{id}/cargo) vs when not to (shared reference data, e.g. locations
reused across bookings), plus the redundant-endpoint pitfall: one resource
reachable at two URL shapes that drift apart."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 960, 660

bands = [
    {"x": 10, "y": 10, "w": 440, "h": 300, "label": "Nest it — real ownership", "fill": "#fafafa"},
    {"x": 470, "y": 10, "w": 480, "h": 300, "label": "Don't nest — shared reference data", "fill": "#fafafa"},
    {"x": 10, "y": 330, "w": 940, "h": 300, "label": "Redundant-endpoint pitfall", "fill": "#fafafa"},
]

nodes = [
    # left: ownership case
    {"x": 50, "y": 70, "w": 220, "h": 70,
     "lines": ["Booking", "/bookings/{id}"], "style": "box"},
    {"x": 50, "y": 190, "w": 220, "h": 90,
     "lines": ["Cargo", "owned by exactly one booking", "/bookings/{id}/cargo"], "style": "accent"},

    # right: shared reference data case
    {"x": 500, "y": 50, "w": 170, "h": 60,
     "lines": ["Booking A", "/bookings/101"], "style": "box"},
    {"x": 500, "y": 140, "w": 170, "h": 60,
     "lines": ["Booking B", "/bookings/204"], "style": "box"},
    {"x": 740, "y": 95, "w": 180, "h": 90,
     "lines": ["Location", "shared reference data", "/locations/{id}"], "style": "accent"},
    {"x": 500, "y": 240, "w": 420, "h": 55,
     "lines": ["✗ /bookings/{id}/locations/{locId} — don't nest; duplicates data per booking"],
     "style": "ghost"},

    # bottom: redundant endpoint pitfall
    {"x": 380, "y": 400, "w": 200, "h": 70,
     "lines": ["Cargo item", "single row in the DB"], "style": "ink"},
    {"x": 100, "y": 530, "w": 300, "h": 70,
     "lines": ["/bookings/{id}/cargo/{cargoId}", "validation fixed here..."], "style": "box"},
    {"x": 560, "y": 530, "w": 300, "h": 70,
     "lines": ["/cargo/{cargoId}", "...but not here"], "style": "box"},
]

edges = [
    {"x1": 160, "y1": 140, "x2": 160, "y2": 190, "label": "nest — real ownership"},

    {"x1": 670, "y1": 80, "x2": 740, "y2": 120, "label": "originLocationId"},
    {"x1": 670, "y1": 170, "x2": 740, "y2": 160, "label": "destLocationId"},

    {"x1": 480, "y1": 435, "x2": 250, "y2": 530, "label": "reachable at", "amber": True, "dashed": True},
    {"x1": 480, "y1": 435, "x2": 710, "y2": 530, "label": "also reachable at", "amber": True, "dashed": True},
]

notes = [
    {"x": 480, "y": 625, "text": "Two routes to one resource means two places to keep a bug fix in sync.",
     "size": 12, "color": "#1a1a1a", "anchor": "middle", "bold": True},
    {"x": 480, "y": 643, "text": "Prefer a single canonical shape; alias or redirect the other only if truly needed.",
     "size": 11, "color": "#b8650a", "anchor": "middle"},
]

generate_diagram.emit("09-sub-resources", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
