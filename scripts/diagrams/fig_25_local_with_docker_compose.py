#!/usr/bin/env python3
"""Fig 25 — Ch25: the Docker/Podman Compose topology for local development —
both apps (Quarkus + FastAPI), Postgres, and the single-container otel-lgtm
(Grafana + Tempo + Loki + Mimir + an OTel Collector) — with one request
traced end to end: a client hits an app, the app exports OTLP spans to the
collector, Tempo stores the trace, and Grafana reads it back from Tempo."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 640

bands = [
    {"x": 20, "y": 20, "w": 900, "h": 230, "label": "docker compose / podman compose", "fill": "#fafafa"},
    {"x": 20, "y": 270, "w": 900, "h": 300, "label": "otel-lgtm (single container)", "fill": "#fff8ef"},
]

nodes = [
    {"x": 50, "y": 60, "w": 140, "h": 60, "lines": ["Client"], "style": "user"},

    {"x": 250, "y": 50, "w": 230, "h": 80,
     "lines": ["booking-api (Quarkus)", "REST + gRPC + GraphQL"], "style": "box"},
    {"x": 520, "y": 50, "w": 230, "h": 80,
     "lines": ["tracking-api (FastAPI)", "REST"], "style": "box"},

    {"x": 250, "y": 170, "w": 230, "h": 60, "lines": ["Postgres", "booking + tracking schemas"], "style": "sub"},
    {"x": 520, "y": 170, "w": 230, "h": 60, "lines": ["Postgres", "shared instance"], "style": "sub"},

    {"x": 800, "y": 60, "w": 110, "h": 60, "lines": ["Kafka", "(optional)"], "style": "sub"},

    # otel-lgtm internals
    {"x": 50, "y": 310, "w": 190, "h": 70, "lines": ["OTel Collector", "receives OTLP"], "style": "accent"},
    {"x": 300, "y": 310, "w": 190, "h": 70, "lines": ["Tempo", "trace storage"], "style": "accent"},
    {"x": 550, "y": 310, "w": 150, "h": 70, "lines": ["Loki", "log storage"], "style": "box"},
    {"x": 740, "y": 310, "w": 150, "h": 70, "lines": ["Mimir", "metric storage"], "style": "box"},

    {"x": 300, "y": 460, "w": 190, "h": 70, "lines": ["Grafana", "dashboards + trace view"], "style": "accent"},
]

edges = [
    {"x1": 190, "y1": 90, "x2": 250, "y2": 90, "label": "1. HTTP request"},
    {"x1": 480, "y1": 90, "x2": 520, "y2": 90, "label": "or"},

    {"x1": 365, "y1": 130, "x2": 365, "y2": 170},
    {"x1": 635, "y1": 130, "x2": 635, "y2": 170},

    {"x1": 365, "y1": 130, "x2": 800, "y2": 90, "dashed": True},

    {"x1": 365, "y1": 130, "x2": 145, "y2": 310, "label": "2. OTLP spans", "amber": True},
    {"x1": 145, "y1": 380, "x2": 395, "y2": 380, "label": "3. export", "amber": True},
    {"x1": 395, "y1": 460, "x2": 395, "y2": 380, "label": "4. query trace", "amber": True},

    {"x1": 145, "y1": 380, "x2": 625, "y2": 380, "dashed": True},
    {"x1": 145, "y1": 380, "x2": 815, "y2": 380, "dashed": True},
]

notes = [
    {"x": W / 2, "y": 580, "size": 12, "color": "#1d1d1d", "anchor": "middle",
     "text": "Logs and metrics ride the same OTLP pipeline into Loki and Mimir, but the trace path is what this chapter follows."},
    {"x": W / 2, "y": 615, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
     "text": "One request, one trace: the app's OTLP exporter hands spans to the collector, the collector forwards them to Tempo, and Grafana renders the stored trace back to you."},
]

generate_diagram.emit("25-local-with-docker-compose", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
