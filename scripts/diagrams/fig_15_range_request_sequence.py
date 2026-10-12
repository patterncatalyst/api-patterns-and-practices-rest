#!/usr/bin/env python3
"""Fig 15 — Ch15: Range requests against a large binary manifest resource. A
client probes with HEAD to learn size and range support, then pulls the first
chunk with a Range request (206 Partial Content), and a final attempt with an
out-of-bounds range is rejected with 416."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 900, 580

CLIENT = {"x": 40, "w": 290}
SERVER = {"x": 570, "w": 290}

nodes = [
    {"x": CLIENT["x"], "y": 20, "w": CLIENT["w"], "h": 50, "lines": ["Client"], "style": "user"},
    {"x": SERVER["x"], "y": 20, "w": SERVER["w"], "h": 50, "lines": ["Server", "GET /manifests/{id}"], "style": "accent"},

    {"x": CLIENT["x"], "y": 110, "w": CLIENT["w"], "h": 60,
     "lines": ["HEAD /manifests/{id}"], "style": "user"},
    {"x": SERVER["x"], "y": 110, "w": SERVER["w"], "h": 90,
     "lines": ["200 OK", "Accept-Ranges: bytes", "Content-Length: 5242880"], "style": "box"},

    {"x": CLIENT["x"], "y": 260, "w": CLIENT["w"], "h": 70,
     "lines": ["GET /manifests/{id}", "Range: bytes=0-1048575"], "style": "user"},
    {"x": SERVER["x"], "y": 260, "w": SERVER["w"], "h": 100,
     "lines": ["206 Partial Content", "Content-Range:", "bytes 0-1048575/5242880"], "style": "accent"},

    {"x": CLIENT["x"], "y": 420, "w": CLIENT["w"], "h": 70,
     "lines": ["GET /manifests/{id}", "Range: bytes=9000000-9999999"], "style": "user"},
    {"x": SERVER["x"], "y": 420, "w": SERVER["w"], "h": 100,
     "lines": ["416 Range Not Satisfiable", "Content-Range:", "bytes */5242880"], "style": "ghost"},
]

edges = [
    {"x1": CLIENT["x"] + CLIENT["w"], "y1": 128, "x2": SERVER["x"], "y2": 128, "label": "probe size & range support"},
    {"x1": SERVER["x"], "y1": 155, "x2": CLIENT["x"] + CLIENT["w"], "y2": 155,
     "label": "Accept-Ranges: bytes", "amber": True, "lx": 0, "ly": 14},

    {"x1": CLIENT["x"] + CLIENT["w"], "y1": 278, "x2": SERVER["x"], "y2": 278, "label": "first 1 MiB chunk"},
    {"x1": SERVER["x"], "y1": 305, "x2": CLIENT["x"] + CLIENT["w"], "y2": 305,
     "label": "206 + Content-Range", "amber": True, "lx": 0, "ly": 14},

    {"x1": CLIENT["x"] + CLIENT["w"], "y1": 438, "x2": SERVER["x"], "y2": 438, "label": "range past end of file"},
    {"x1": SERVER["x"], "y1": 460, "x2": CLIENT["x"] + CLIENT["w"], "y2": 460,
     "label": "416 unsatisfiable", "dashed": True, "lx": 0, "ly": 14},
]

notes = [
    {"x": 450, "y": 555, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
     "text": "Accept-Ranges from the HEAD tells the client resuming/partial fetches are safe; the server must still validate every Range against the current Content-Length before honoring it."},
]

generate_diagram.emit("15-range-request-sequence", W, H, nodes=nodes, edges=edges, notes=notes)
