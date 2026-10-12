#!/usr/bin/env python3
"""Fig 04 — Ch4: contract-first flow. One contract scaffolds both stacks; CI
schema-validates live responses; drift fails the build."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 960, 500

nodes = [
    {"x": 370, "y": 30, "w": 220, "h": 70,
     "lines": ["OpenAPI 3.1 contract", "shipping/cargo booking"], "style": "accent"},

    {"x": 80, "y": 150, "w": 260, "h": 80,
     "lines": ["Quarkus scaffold", "generated from contract"], "style": "box"},
    {"x": 620, "y": 150, "w": 260, "h": 80,
     "lines": ["FastAPI scaffold", "generated from contract"], "style": "box"},

    {"x": 370, "y": 270, "w": 220, "h": 70,
     "lines": ["CI", "schema-validates live responses"], "style": "ink"},

    {"x": 130, "y": 390, "w": 260, "h": 80,
     "lines": ["Contract match ✓", "merge allowed"], "style": "box"},
    {"x": 570, "y": 390, "w": 260, "h": 80,
     "lines": ["Drift detected ✗", "build fails"], "style": "accent"},
]

edges = [
    {"x1": 410, "y1": 100, "x2": 210, "y2": 150, "label": "scaffolds"},
    {"x1": 550, "y1": 100, "x2": 750, "y2": 150, "label": "scaffolds"},
    {"x1": 210, "y1": 230, "x2": 440, "y2": 270, "label": "live responses"},
    {"x1": 750, "y1": 230, "x2": 520, "y2": 270, "label": "live responses"},
    {"x1": 440, "y1": 340, "x2": 260, "y2": 390, "label": "match"},
    {"x1": 520, "y1": 340, "x2": 700, "y2": 390, "label": "drift", "amber": True, "dashed": True},
]

generate_diagram.emit("04-contract-first-flow", W, H, nodes=nodes, edges=edges)
