#!/usr/bin/env python3
"""Fig 17 — Ch17: REST/SSE vs WebSockets vs webhooks vs gRPC compared by
direction, connection model, and best-fit use case for moving data —
especially streaming — between client and server."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 980, 480

COL_PROTO = {"x": 30, "w": 170}
COL_DIR = {"x": 210, "w": 200}
COL_CONN = {"x": 420, "w": 260}
COL_FIT = {"x": 690, "w": 260}
HEADER_Y, HEADER_H = 30, 50
ROW_H = 70
ROW_GAP = 8
FIRST_ROW_Y = 100

ROWS = [
    ("REST / SSE", "client-pull (REST)\nserver-push (SSE)",
     "request/response, or one long-lived HTTP connection for SSE",
     "CRUD over resources; SSE for one-way live updates to a browser",
     "accent"),
    ("WebSockets", "bidirectional", "one persistent socket, full-duplex after the handshake",
     "chat, collaborative editing, low-latency two-way streams", "box"),
    ("Webhooks", "server-push (inverted)", "no open connection — provider POSTs to a client-registered URL",
     "async event notification when the receiver can't poll or stay connected", "box"),
    ("gRPC", "client-pull, server-push, or bidirectional streaming",
     "one HTTP/2 connection, multiplexed streams, binary Protobuf framing",
     "internal service-to-service calls and high-throughput streaming RPCs", "box"),
]

nodes = [
    {"x": COL_PROTO["x"], "y": HEADER_Y, "w": COL_PROTO["w"], "h": HEADER_H, "lines": ["Protocol"], "style": "ink"},
    {"x": COL_DIR["x"], "y": HEADER_Y, "w": COL_DIR["w"], "h": HEADER_H, "lines": ["Direction"], "style": "ink"},
    {"x": COL_CONN["x"], "y": HEADER_Y, "w": COL_CONN["w"], "h": HEADER_H, "lines": ["Connection model"], "style": "ink"},
    {"x": COL_FIT["x"], "y": HEADER_Y, "w": COL_FIT["w"], "h": HEADER_H, "lines": ["Best-fit use case"], "style": "ink"},
]

for i, (name, direction, conn, fit, style) in enumerate(ROWS):
    y = FIRST_ROW_Y + i * (ROW_H + ROW_GAP)
    nodes.append({"x": COL_PROTO["x"], "y": y, "w": COL_PROTO["w"], "h": ROW_H, "lines": [name], "style": style})
    nodes.append({"x": COL_DIR["x"], "y": y, "w": COL_DIR["w"], "h": ROW_H, "lines": direction.split("\n"), "style": "sub"})
    nodes.append({"x": COL_CONN["x"], "y": y, "w": COL_CONN["w"], "h": ROW_H, "lines": [conn], "style": "sub"})
    nodes.append({"x": COL_FIT["x"], "y": y, "w": COL_FIT["w"], "h": ROW_H, "lines": [fit], "style": "sub"})

TABLE_BOTTOM = FIRST_ROW_Y + len(ROWS) * (ROW_H + ROW_GAP)

notes = [
    {"x": W / 2, "y": TABLE_BOTTOM + 30, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
     "text": "REST/SSE stays the default: simplest connection model, works through ordinary HTTP infrastructure. Reach for WebSockets, webhooks, or gRPC only when the direction or throughput REST can't express is the actual requirement."},
]

generate_diagram.emit("17-cross-protocol", W, H, nodes=nodes, notes=notes)
