#!/usr/bin/env python3
"""Fig 08 — Ch8: three pagination strategies compared — offset/limit,
keyset/cursor, and seek/after_id — with a DoS-guard note that `limit` is
always capped server-side regardless of strategy."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 440

COL_STRATEGY = {"x": 30, "w": 160}
COL_REQUEST = {"x": 200, "w": 290}
COL_RESPONSE = {"x": 500, "w": 250}
COL_NOTE = {"x": 760, "w": 150}
HEADER_Y, HEADER_H = 30, 50
ROW_H = 110
ROW_GAP = 8
FIRST_ROW_Y = 100

ROWS = [
    ("Offset / limit", False,
     ["GET /bookings", "?offset=40&limit=20"],
     ["{\"items\":[...],", "\"total\":538}"],
     "Simple; drifts under concurrent inserts/deletes"),
    ("Keyset / cursor", True,
     ["GET /bookings", "?cursor=eyJpZCI6NDJ9&limit=20"],
     ["{\"items\":[...],", "\"nextCursor\":\"...\"}"],
     "Stable under writes; cursor is opaque"),
    ("Seek / after_id", False,
     ["GET /bookings", "?after_id=42&limit=20"],
     ["{\"items\":[...],", "\"nextAfterId\":187}"],
     "Stable; needs a sortable unique key"),
]

nodes = [
    {"x": COL_STRATEGY["x"], "y": HEADER_Y, "w": COL_STRATEGY["w"], "h": HEADER_H,
     "lines": ["Strategy"], "style": "ink"},
    {"x": COL_REQUEST["x"], "y": HEADER_Y, "w": COL_REQUEST["w"], "h": HEADER_H,
     "lines": ["Request shape"], "style": "ink"},
    {"x": COL_RESPONSE["x"], "y": HEADER_Y, "w": COL_RESPONSE["w"], "h": HEADER_H,
     "lines": ["Response shape"], "style": "ink"},
    {"x": COL_NOTE["x"], "y": HEADER_Y, "w": COL_NOTE["w"], "h": HEADER_H,
     "lines": ["Behavior"], "style": "ink"},
]

for i, (name, recommended, req_lines, resp_lines, note) in enumerate(ROWS):
    y = FIRST_ROW_Y + i * (ROW_H + ROW_GAP)
    style = "accent" if recommended else "box"
    nodes.append({"x": COL_STRATEGY["x"], "y": y, "w": COL_STRATEGY["w"], "h": ROW_H,
                  "lines": [name], "style": style})
    nodes.append({"x": COL_REQUEST["x"], "y": y, "w": COL_REQUEST["w"], "h": ROW_H,
                  "lines": req_lines, "style": "sub"})
    nodes.append({"x": COL_RESPONSE["x"], "y": y, "w": COL_RESPONSE["w"], "h": ROW_H,
                  "lines": resp_lines, "style": "sub"})
    nodes.append({"x": COL_NOTE["x"], "y": y, "w": COL_NOTE["w"], "h": ROW_H,
                  "lines": [note], "style": "box"})

notes = [
    {"x": 470, "y": 410, "text": "`limit` is always capped server-side (e.g. max 100) — an unbounded limit is a DoS vector.",
     "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True},
]

generate_diagram.emit("08-pagination-strategies", W, H, nodes=nodes, notes=notes)
