#!/usr/bin/env python3
"""Fig 18 — Ch18: back-end I/O concurrency models — Quarkus blocking
(thread-per-request worker pool, exhaustion risk) vs reactive/virtual threads,
and Python's threadpool (GIL-bound) vs the asyncio event loop — all serving
requests against the same DB and file I/O behind the API without exhausting
threads."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 620

bands = [
    {"x": 20, "y": 30, "w": 430, "h": 360, "label": "Quarkus (JVM)", "fill": "#fafafa"},
    {"x": 490, "y": 30, "w": 430, "h": 360, "label": "Python", "fill": "#fafafa"},
]

nodes = [
    # Quarkus
    {"x": 50, "y": 70, "w": 370, "h": 50, "lines": ["Requests"], "style": "user"},
    {"x": 50, "y": 150, "w": 370, "h": 90,
     "lines": ["Blocking — worker pool", "thread-per-request, N worker threads",
               "risk: slow DB/file I/O exhausts the pool"], "style": "box"},
    {"x": 50, "y": 270, "w": 370, "h": 90,
     "lines": ["Reactive / virtual threads", "event loop dispatches to cheap virtual threads",
               "blocking-looking code, non-blocking under the hood"], "style": "accent"},

    # Python
    {"x": 520, "y": 70, "w": 370, "h": 50, "lines": ["Requests"], "style": "user"},
    {"x": 520, "y": 150, "w": 370, "h": 90,
     "lines": ["Threadpool executor", "GIL serializes CPU-bound work",
               "blocking I/O offloaded to worker threads"], "style": "box"},
    {"x": 520, "y": 270, "w": 370, "h": 90,
     "lines": ["asyncio event loop", "single thread, cooperative scheduling",
               "non-blocking I/O via async/await"], "style": "accent"},

    # shared backing I/O
    {"x": 200, "y": 450, "w": 230, "h": 70, "lines": ["Database", "connection pool"], "style": "sub"},
    {"x": 500, "y": 450, "w": 230, "h": 70, "lines": ["File I/O", "object storage / disk"], "style": "sub"},
]

edges = [
    {"x1": 235, "y1": 120, "x2": 235, "y2": 150},
    {"x1": 235, "y1": 240, "x2": 235, "y2": 270},
    {"x1": 705, "y1": 120, "x2": 705, "y2": 150},
    {"x1": 705, "y1": 240, "x2": 705, "y2": 270},

    {"x1": 180, "y1": 240, "x2": 290, "y2": 450, "label": "blocks a thread", "dashed": True},
    {"x1": 300, "y1": 360, "x2": 300, "y2": 450, "label": "non-blocking", "amber": True},

    {"x1": 650, "y1": 240, "x2": 580, "y2": 450, "label": "blocks a thread", "dashed": True, "lx": -40},
    {"x1": 650, "y1": 360, "x2": 650, "y2": 450, "label": "non-blocking", "amber": True, "lx": 40},

    {"x1": 430, "y1": 485, "x2": 500, "y2": 485, "label": "same back end", "lx": 0, "ly": -8},
]

notes = [
    {"x": W / 2, "y": 575, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
     "text": "Reactive/virtual threads and the asyncio event loop scale by never parking a real OS thread on I/O — blocking models scale only as far as the thread pool, then requests queue or fail."},
]

generate_diagram.emit("18-concurrency-model", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
