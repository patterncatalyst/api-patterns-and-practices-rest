#!/usr/bin/env python3
"""Fig 19 — Ch19: HTTP/1.1 vs HTTP/2 vs HTTP/3 — serial requests with
head-of-line blocking, multiplexed streams over one TCP connection (still
TCP-HOL-blocked), and independent streams over QUIC/UDP with connection
migration and 0-RTT. HTTP/3 is tier-gated in CI."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 640

BAND_X, BAND_W = 20, 900
ROW_H = 170
ROW_GAP = 20
FIRST_Y = 30

CLIENT = {"x": 40, "w": 140}
SERVER = {"x": 760, "w": 140}

bands, nodes, edges, notes = [], [], [], []

# --- HTTP/1.1 : serial requests, head-of-line blocking ---------------------
y0 = FIRST_Y
bands.append({"x": BAND_X, "y": y0, "w": BAND_W, "h": ROW_H, "label": "HTTP/1.1 — serial, head-of-line blocked", "fill": "#fafafa"})
nodes += [
    {"x": CLIENT["x"], "y": y0 + 60, "w": CLIENT["w"], "h": 50, "lines": ["Client"], "style": "user"},
    {"x": SERVER["x"], "y": y0 + 60, "w": SERVER["w"], "h": 50, "lines": ["Server"], "style": "box"},
]
for i, sx in enumerate([250, 400, 550]):
    sy = y0 + 20 + i * 42
    nodes.append({"x": sx, "y": sy, "w": 230, "h": 34, "lines": [f"request {i+1} — waits its turn"], "style": "sub"})
    edges.append({"x1": CLIENT["x"] + CLIENT["w"], "y1": y0 + 85, "x2": sx, "y2": sy + 17, "dashed": (i > 0)})
    edges.append({"x1": sx + 230, "y1": sy + 17, "x2": SERVER["x"], "y2": y0 + 85, "dashed": (i > 0)})

# --- HTTP/2 : multiplexed streams, one TCP connection, TCP HOL blocking ----
y1 = FIRST_Y + (ROW_H + ROW_GAP)
bands.append({"x": BAND_X, "y": y1, "w": BAND_W, "h": ROW_H, "label": "HTTP/2 — multiplexed streams, HPACK, over one TCP connection", "fill": "#fafafa"})
nodes += [
    {"x": CLIENT["x"], "y": y1 + 60, "w": CLIENT["w"], "h": 50, "lines": ["Client"], "style": "user"},
    {"x": SERVER["x"], "y": y1 + 60, "w": SERVER["w"], "h": 50, "lines": ["Server"], "style": "box"},
    {"x": 250, "y": y1 + 15, "w": 500, "h": 24, "lines": ["one TCP connection"], "style": "sub"},
]
for i in range(3):
    sy = y1 + 50 + i * 36
    nodes.append({"x": 290, "y": sy, "w": 450, "h": 26, "lines": [f"stream {i+1} — independent, interleaved frames"], "style": "box"})
    edges.append({"x1": CLIENT["x"] + CLIENT["w"], "y1": y1 + 85, "x2": 290, "y2": sy + 13, "amber": True})
    edges.append({"x1": 740, "y1": sy + 13, "x2": SERVER["x"], "y2": y1 + 85, "amber": True})

# --- HTTP/3 : independent streams over QUIC/UDP -----------------------------
y2 = FIRST_Y + 2 * (ROW_H + ROW_GAP)
bands.append({"x": BAND_X, "y": y2, "w": BAND_W, "h": ROW_H, "label": "HTTP/3 — independent streams over QUIC/UDP, QPACK, 0-RTT, connection migration", "fill": "#fff8ef"})
nodes += [
    {"x": CLIENT["x"], "y": y2 + 60, "w": CLIENT["w"], "h": 50, "lines": ["Client", "roams networks"], "style": "user"},
    {"x": SERVER["x"], "y": y2 + 60, "w": SERVER["w"], "h": 50, "lines": ["Server"], "style": "accent"},
]
for i in range(3):
    sy = y2 + 30 + i * 36
    nodes.append({"x": 290, "y": sy, "w": 450, "h": 26,
                  "lines": [f"stream {i+1} — no TCP, a lost packet blocks only this stream"], "style": "accent"})
    edges.append({"x1": CLIENT["x"] + CLIENT["w"], "y1": y2 + 85, "x2": 290, "y2": sy + 13, "amber": True})
    edges.append({"x1": 740, "y1": sy + 13, "x2": SERVER["x"], "y2": y2 + 85, "amber": True})

notes.append({"x": W / 2, "y": H - 15, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
              "text": "HTTP/2 fixes application-level head-of-line blocking but one lost TCP segment still stalls every stream; HTTP/3's independent QUIC streams don't share that fate. HTTP/3 coverage is tier-gated in CI (skipped unless the runner has QUIC support)."})

generate_diagram.emit("19-http2-http3", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
