#!/usr/bin/env python3
"""Fig 22 — Ch22: the Quarkus REST request pipeline, build-time-optimized.
Build-time annotation processing generates metadata (zero reflection) that
feeds a runtime pipeline: Vert.x event loop -> zero-reflection
@RestHeader/@RestQuery binding -> handler -> reactive streaming of
NDJSON/large JSON back out. Contrasted with traditional reflective
frameworks doing this work at request time."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 560

bands, nodes, edges, notes = [], [], [], []

# --- BUILD TIME lane ----------------------------------------------------------
y0 = 25
bands.append({"x": 20, "y": y0, "w": 900, "h": 150, "label": "BUILD TIME — once, ahead of deployment", "fill": "#fff8ef"})
nodes += [
    {"x": 50, "y": y0 + 50, "w": 190, "h": 60, "lines": ["source", "@Path / @GET / @RestQuery"], "style": "box"},
    {"x": 300, "y": y0 + 50, "w": 220, "h": 60, "lines": ["Quarkus annotation processor", "resolves bindings at compile time"], "style": "accent"},
    {"x": 590, "y": y0 + 50, "w": 290, "h": 60, "lines": ["generated metadata", "zero reflection at runtime"], "style": "accent"},
]
edges.append({"x1": 240, "y1": y0 + 80, "x2": 300, "y2": y0 + 80})
edges.append({"x1": 520, "y1": y0 + 80, "x2": 590, "y2": y0 + 80, "amber": True})

# --- RUNTIME lane ---------------------------------------------------------
y1 = y0 + 150 + 30
bands.append({"x": 20, "y": y1, "w": 900, "h": 230, "label": "RUNTIME — per request", "fill": "#fafafa"})
nodes += [
    {"x": 40, "y": y1 + 40, "w": 150, "h": 55, "lines": ["HTTP client"], "style": "user"},
    {"x": 230, "y": y1 + 40, "w": 170, "h": 55, "lines": ["Vert.x", "event loop"], "style": "box"},
    {"x": 440, "y": y1 + 40, "w": 220, "h": 55, "lines": ["zero-reflection binding", "@RestHeader / @RestQuery"], "style": "box"},
    {"x": 700, "y": y1 + 40, "w": 180, "h": 55, "lines": ["handler", "business logic"], "style": "box"},
    {"x": 440, "y": y1 + 140, "w": 440, "h": 55, "lines": ["reactive streaming response", "NDJSON / large JSON back to the client"], "style": "accent"},
]
edges.append({"x1": 190, "y1": y1 + 67, "x2": 230, "y2": y1 + 67})
edges.append({"x1": 400, "y1": y1 + 67, "x2": 440, "y2": y1 + 67, "amber": True})
edges.append({"x1": 660, "y1": y1 + 67, "x2": 700, "y2": y1 + 67})
edges.append({"x1": 790, "y1": y1 + 95, "x2": 660, "y2": y1 + 140, "amber": True})
edges.append({"x1": 440, "y1": y1 + 167, "x2": 115, "y2": y1 + 95, "amber": True, "label": "streamed back"})
# build-time metadata feeds runtime binding
edges.append({"x1": 735, "y1": y0 + 110, "x2": 550, "y2": y1 + 40, "dashed": True})

notes.append({"x": W / 2, "y": H - 12, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
              "text": "Traditional reflective frameworks resolve this binding on every request at runtime; Quarkus resolves it once at build time, so the event loop never pays a reflection tax."})

generate_diagram.emit("22-quarkus-rest-in-depth", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
