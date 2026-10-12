#!/usr/bin/env python3
"""Fig 16 — Ch16: three streaming modes over one long-lived connection —
chunked transfer encoding, Server-Sent Events, and NDJSON — each delivering
pieces incrementally over time rather than one buffered body, plus the
use case each one fits best."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 980, 640

BAND_X, BAND_W = 20, 940
ROW_H = 155
ROW_GAP = 20
FIRST_Y = 30

SERVER = {"x": 40, "w": 240, "h": 70}
CLIENT = {"x": 810, "w": 130, "h": 70}
PIECE_W, PIECE_H = 100, 54
PIECE_XS = [305, 435, 565, 695]

ROWS = [
    ("Chunked transfer encoding", ["Transfer-Encoding:", "chunked"],
     [["chunk 1"], ["chunk 2"], ["chunk 3"], ["chunk 0", "(end)"]],
     "progressive download — client renders/saves bytes as they land, total size unknown up front"),
    ("Server-Sent Events", ["Content-Type:", "text/event-stream"],
     [["event: status"], ["event: status"], ["event: status"], ["id: 104", "(resume pt)"]],
     "live updates pushed to a browser — one-way, auto-reconnects via Last-Event-ID"),
    ("NDJSON", ["Content-Type:", "application/x-ndjson"],
     [['{"id":1}'], ['{"id":2}'], ['{"id":3}'], ['{"id":4}']],
     "bulk export of many records — each line is a complete, independently parseable JSON object"),
]

bands, nodes, edges, notes = [], [], [], []

for i, (title, header_lines, pieces, fit) in enumerate(ROWS):
    y = FIRST_Y + i * (ROW_H + ROW_GAP)
    bands.append({"x": BAND_X, "y": y, "w": BAND_W, "h": ROW_H, "label": title, "fill": "#fafafa"})

    srv_y = y + 45
    nodes.append({"x": SERVER["x"], "y": srv_y, "w": SERVER["w"], "h": SERVER["h"],
                  "lines": ["Server"] + header_lines, "style": "accent"})
    nodes.append({"x": CLIENT["x"], "y": srv_y, "w": CLIENT["w"], "h": CLIENT["h"],
                  "lines": ["Client", "one connection"], "style": "user"})

    mid_y = srv_y + SERVER["h"] / 2
    prev_x = SERVER["x"] + SERVER["w"]
    for j, (px, piece_lines) in enumerate(zip(PIECE_XS, pieces)):
        py = srv_y + (SERVER["h"] - PIECE_H) / 2
        nodes.append({"x": px, "y": py, "w": PIECE_W, "h": PIECE_H,
                      "lines": piece_lines, "style": "box"})
        edges.append({"x1": prev_x, "y1": mid_y, "x2": px, "y2": py + PIECE_H / 2,
                      "amber": (j == 0)})
        prev_x = px + PIECE_W
    edges.append({"x1": prev_x, "y1": mid_y, "x2": CLIENT["x"], "y2": mid_y, "label": "time →"})

    notes.append({"x": BAND_X + 12, "y": y + ROW_H - 10, "size": 11, "color": "#555555",
                  "text": f"best fit: {fit}"})

TABLE_BOTTOM = FIRST_Y + len(ROWS) * (ROW_H + ROW_GAP)

notes.append({"x": W / 2, "y": TABLE_BOTTOM + 15, "size": 12, "color": "#b8650a",
              "anchor": "middle", "bold": True,
              "text": "All three keep one connection open and deliver pieces as they're produced — they differ in framing, direction, and what a piece means to the client."})

generate_diagram.emit("16-streaming-modes", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
