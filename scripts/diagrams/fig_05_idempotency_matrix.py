#!/usr/bin/env python3
"""Fig 05 — Ch5: HTTP method x {safe, idempotent} grid, with the booking
operations placed against each method."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 980, 500

COL_METHOD = {"x": 40, "w": 140}
COL_SAFE = {"x": 200, "w": 150}
COL_IDEMP = {"x": 370, "w": 150}
COL_EXAMPLE = {"x": 540, "w": 400}
HEADER_Y, HEADER_H = 30, 50
ROW_H = 55
ROW_GAP = 5
FIRST_ROW_Y = 100

ROWS = [
    # method, safe, idempotent, booking example
    ("GET", True, True, "GET /bookings — safe, cacheable"),
    ("HEAD", True, True, "HEAD /bookings/{id}"),
    ("PUT", False, True, "PUT /bookings/{id} — idempotent"),
    ("DELETE", False, True, "DELETE /bookings/{id} — idempotent"),
    ("POST", False, False, "POST /bookings — creates, not idempotent"),
    ("PATCH", False, False, "PATCH /bookings/{id} — not idempotent (Ch7)"),
]

nodes = [
    {"x": COL_METHOD["x"], "y": HEADER_Y, "w": COL_METHOD["w"], "h": HEADER_H,
     "lines": ["Method"], "style": "ink"},
    {"x": COL_SAFE["x"], "y": HEADER_Y, "w": COL_SAFE["w"], "h": HEADER_H,
     "lines": ["Safe"], "style": "ink"},
    {"x": COL_IDEMP["x"], "y": HEADER_Y, "w": COL_IDEMP["w"], "h": HEADER_H,
     "lines": ["Idempotent"], "style": "ink"},
    {"x": COL_EXAMPLE["x"], "y": HEADER_Y, "w": COL_EXAMPLE["w"], "h": HEADER_H,
     "lines": ["Booking operation"], "style": "ink"},
]

for i, (method, safe, idemp, example) in enumerate(ROWS):
    y = FIRST_ROW_Y + i * (ROW_H + ROW_GAP)
    nodes.append({"x": COL_METHOD["x"], "y": y, "w": COL_METHOD["w"], "h": ROW_H,
                   "lines": [method], "style": "box"})
    nodes.append({"x": COL_SAFE["x"], "y": y, "w": COL_SAFE["w"], "h": ROW_H,
                   "lines": ["Yes" if safe else "No"], "style": "accent" if safe else "box"})
    nodes.append({"x": COL_IDEMP["x"], "y": y, "w": COL_IDEMP["w"], "h": ROW_H,
                   "lines": ["Yes" if idemp else "No"], "style": "accent" if idemp else "box"})
    nodes.append({"x": COL_EXAMPLE["x"], "y": y, "w": COL_EXAMPLE["w"], "h": ROW_H,
                   "lines": [example], "style": "sub"})

generate_diagram.emit("05-idempotency-matrix", W, H, nodes=nodes)
