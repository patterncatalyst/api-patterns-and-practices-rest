#!/usr/bin/env python3
"""Fig 00 — Ch0 lab topology: both stacks against one contract, CI validates live
responses, observability is optional in CI."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 960, 600

nodes = [
    {"x": 370, "y": 30, "w": 220, "h": 50,
     "lines": ["CI pipeline"], "style": "ink"},
    {"x": 50, "y": 140, "w": 220, "h": 70,
     "lines": ["Quarkus service", "/bookings API"], "style": "box"},
    {"x": 690, "y": 140, "w": 220, "h": 70,
     "lines": ["FastAPI service", "/bookings API"], "style": "box"},
    {"x": 370, "y": 250, "w": 220, "h": 70,
     "lines": ["OpenAPI 3.1 contract", "shipping/cargo booking"], "style": "accent"},
    {"x": 370, "y": 370, "w": 220, "h": 60,
     "lines": ["PostgreSQL", "bookings · cargo · locations"], "style": "box"},
    {"x": 40, "y": 470, "w": 880, "h": 90,
     "lines": ["Observability (LGTM)", "Grafana · Loki · Tempo · Mimir", "optional in CI"],
     "style": "ghost"},
]

edges = [
    # CI validates both stacks' live responses against the contract
    {"x1": 430, "y1": 80, "x2": 170, "y2": 140, "amber": True, "dashed": True,
     "label": "CI schema-validates live responses", "lx": -40, "ly": -10},
    {"x1": 530, "y1": 80, "x2": 790, "y2": 140, "amber": True, "dashed": True},
    # both stacks implement the one contract
    {"x1": 170, "y1": 210, "x2": 410, "y2": 255, "label": "implements"},
    {"x1": 790, "y1": 210, "x2": 550, "y2": 255, "label": "implements"},
    # both stacks read/write the same database
    {"x1": 160, "y1": 210, "x2": 370, "y2": 395, "label": "reads/writes", "lx": -30, "ly": 10},
    {"x1": 800, "y1": 210, "x2": 590, "y2": 395, "label": "reads/writes", "lx": 30, "ly": 10},
    # both stacks emit telemetry (optional lane)
    {"x1": 50, "y1": 175, "x2": 50, "y2": 470, "dashed": True},
    {"x1": 910, "y1": 175, "x2": 910, "y2": 470, "dashed": True},
]

generate_diagram.emit("00-lab-topology", W, H, nodes=nodes, edges=edges)
