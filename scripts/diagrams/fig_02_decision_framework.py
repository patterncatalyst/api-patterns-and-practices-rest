#!/usr/bin/env python3
"""Fig 02 — Ch2 decision framework: the axes used to choose a pattern, style and
transport. Reused as the Decision box in later chapters, so keep this a clean
hub-and-spoke axis layout, not a narrative diagram."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 960, 700

nodes = [
    {"x": 40, "y": 30, "w": 240, "h": 100,
     "lines": ["Interaction shape", "request/response vs", "stream vs fire-and-forget"],
     "style": "box"},
    {"x": 660, "y": 30, "w": 240, "h": 100,
     "lines": ["Payload size", "small JSON vs large", "binary / bulk transfer"],
     "style": "box"},
    {"x": 0, "y": 300, "w": 220, "h": 100,
     "lines": ["Latency / real-time need", "sync call vs async", "job vs push/stream"],
     "style": "box"},
    {"x": 720, "y": 300, "w": 220, "h": 100,
     "lines": ["Cacheability", "can a shared cache", "safely store it?"],
     "style": "box"},
    {"x": 40, "y": 570, "w": 240, "h": 100,
     "lines": ["Client diversity", "browser, mobile, server,", "partner integrations"],
     "style": "box"},
    {"x": 660, "y": 570, "w": 240, "h": 100,
     "lines": ["Evolution needs", "how fields/versions", "change without breaking"],
     "style": "box"},

    {"x": 350, "y": 300, "w": 260, "h": 100,
     "lines": ["Pattern, style & transport", "(reused in later chapters'", "Decision boxes)"],
     "style": "accent"},
]

edges = [
    {"x1": 160, "y1": 130, "x2": 470, "y2": 320},
    {"x1": 780, "y1": 130, "x2": 610, "y2": 320},
    {"x1": 220, "y1": 350, "x2": 350, "y2": 350},
    {"x1": 720, "y1": 350, "x2": 610, "y2": 350},
    {"x1": 160, "y1": 570, "x2": 470, "y2": 380},
    {"x1": 780, "y1": 570, "x2": 610, "y2": 380},
]

notes = [
    {"x": 480, "y": 680, "text": "Decision axes — the same six criteria recur wherever the site compares options.",
     "size": 11, "color": "#555555", "anchor": "middle"},
]

generate_diagram.emit("02-decision-framework", W, H, nodes=nodes, edges=edges, notes=notes)
