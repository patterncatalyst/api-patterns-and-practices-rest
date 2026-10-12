#!/usr/bin/env python3
"""Fig 23 — Ch23: the FastAPI/ASGI request pipeline. An ASGI server
(Uvicorn/Hypercorn) drives one event loop. async def handlers run ON the
loop (ideal for awaitable I/O); def (sync) handlers are offloaded to a
threadpool so they don't block the loop. StreamingResponse/SSE streams out;
BackgroundTasks run after the response is sent. Includes a GIL / free-
threaded note."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 620

bands, nodes, edges, notes = [], [], [], []

# --- entry: ASGI server + event loop -----------------------------------------
y0 = 25
bands.append({"x": 20, "y": y0, "w": 900, "h": 110, "label": "ASGI server", "fill": "#fafafa"})
nodes += [
    {"x": 40, "y": y0 + 35, "w": 150, "h": 50, "lines": ["HTTP client"], "style": "user"},
    {"x": 240, "y": y0 + 35, "w": 220, "h": 50, "lines": ["Uvicorn / Hypercorn", "ASGI server"], "style": "box"},
    {"x": 520, "y": y0 + 35, "w": 200, "h": 50, "lines": ["single event loop"], "style": "accent"},
]
edges.append({"x1": 190, "y1": y0 + 60, "x2": 240, "y2": y0 + 60})
edges.append({"x1": 460, "y1": y0 + 60, "x2": 520, "y2": y0 + 60, "amber": True})

# --- the fork: async def vs def ----------------------------------------------
y1 = y0 + 110 + 25
bands.append({"x": 20, "y": y1, "w": 900, "h": 180, "label": "the key decision — where does the handler run?", "fill": "#fff8ef"})
nodes += [
    {"x": 80, "y": y1 + 40, "w": 340, "h": 70, "lines": ["async def handler", "runs ON the event loop", "ideal for awaitable I/O (DB, HTTP, Kafka)"], "style": "accent"},
    {"x": 500, "y": y1 + 40, "w": 340, "h": 70, "lines": ["def (sync) handler", "offloaded to a threadpool", "so it never blocks the loop"], "style": "box"},
    {"x": 500, "y": y1 + 125, "w": 340, "h": 40, "lines": ["threadpool executor"], "style": "sub"},
]
edges.append({"x1": 620, "y1": y0 + 85, "x2": 250, "y2": y1 + 40, "amber": True})
edges.append({"x1": 620, "y1": y0 + 85, "x2": 670, "y2": y1 + 40})
edges.append({"x1": 670, "y1": y1 + 110, "x2": 670, "y2": y1 + 125})

# --- outputs: streaming + background tasks -----------------------------------
y2 = y1 + 180 + 25
bands.append({"x": 20, "y": y2, "w": 900, "h": 150, "label": "response handling", "fill": "#fafafa"})
nodes += [
    {"x": 60, "y": y2 + 40, "w": 380, "h": 80, "lines": ["StreamingResponse / SSE", "streams chunks back on the event loop", "without buffering the whole payload"], "style": "accent"},
    {"x": 500, "y": y2 + 40, "w": 340, "h": 80, "lines": ["BackgroundTasks", "scheduled to run AFTER", "the response has been sent"], "style": "box"},
]
edges.append({"x1": 250, "y1": y1 + 110, "x2": 250, "y2": y2 + 40, "amber": True})
edges.append({"x1": 670, "y1": y1 + 165, "x2": 670, "y2": y2 + 40})

notes.append({"x": W / 2, "y": H - 12, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
              "text": "Under the GIL, threadpool-offloaded sync handlers still contend for the interpreter lock during CPU-bound work; only I/O-bound release points actually parallelize. Free-threaded (no-GIL) Python builds change this trade-off but are not yet the default."})

generate_diagram.emit("23-fastapi-in-depth", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
