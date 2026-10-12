#!/usr/bin/env python3
"""Fig 21 — Ch21: one microservice, many contracts, one shared schema. A
shared JSON Schema $defs block is $ref'd by both the OpenAPI doc (sync REST
path) and the AsyncAPI doc (event path). The REST path and the CloudEvents/
Kafka event path both flow out of the same service. An Arazzo workflow spans
booking -> routing -> tracking. A visually set-apart governance tier
(local-only, out of CI) holds Apicurio Registry and OpenMetadata."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 760

bands, nodes, edges, notes = [], [], [], []

# --- shared schema at the top, center ---------------------------------------
y0 = 25
bands.append({"x": 20, "y": y0, "w": 900, "h": 90, "label": "single source of truth", "fill": "#fff8ef"})
nodes.append({"x": 340, "y": y0 + 30, "w": 260, "h": 50, "lines": ["contracts/schemas/*.json", "shared JSON Schema $defs"], "style": "accent"})

# --- sync REST path (left) and async event path (right) ---------------------
y1 = y0 + 90 + 25
bands.append({"x": 20, "y": y1, "w": 430, "h": 190, "label": "sync REST path — $ref'd by OpenAPI", "fill": "#fafafa"})
nodes += [
    {"x": 40, "y": y1 + 40, "w": 150, "h": 50, "lines": ["REST client"], "style": "user"},
    {"x": 230, "y": y1 + 40, "w": 190, "h": 50, "lines": ["OpenAPI / REST", "endpoint"], "style": "box"},
    {"x": 230, "y": y1 + 120, "w": 190, "h": 50, "lines": ["Service"], "style": "box"},
]
edges.append({"x1": 190, "y1": y1 + 65, "x2": 230, "y2": y1 + 65})
edges.append({"x1": 325, "y1": y1 + 90, "x2": 325, "y2": y1 + 120})

bands.append({"x": 490, "y": y1, "w": 430, "h": 190, "label": "event path — $ref'd by AsyncAPI", "fill": "#fafafa"})
nodes += [
    {"x": 510, "y": y1 + 120, "w": 190, "h": 50, "lines": ["CloudEvents envelope", "BookingEvent"], "style": "box"},
    {"x": 730, "y": y1 + 120, "w": 170, "h": 50, "lines": ["Kafka (KRaft)"], "style": "box"},
    {"x": 730, "y": y1 + 40, "w": 170, "h": 50, "lines": ["Consumer"], "style": "user"},
]
# service feeds both paths from the schema
edges.append({"x1": 470, "y1": y0 + 75, "x2": 325, "y2": y1 + 40, "dashed": True})
edges.append({"x1": 470, "y1": y0 + 75, "x2": 605, "y2": y1 + 120, "dashed": True})
edges.append({"x1": 420, "y1": y1 + 145, "x2": 510, "y2": y1 + 145, "amber": True, "label": "emits"})
edges.append({"x1": 700, "y1": y1 + 145, "x2": 730, "y2": y1 + 145})
edges.append({"x1": 815, "y1": y1 + 120, "x2": 815, "y2": y1 + 90})

# --- Arazzo workflow spanning booking -> routing -> tracking -----------------
y2 = y1 + 190 + 25
bands.append({"x": 20, "y": y2, "w": 900, "h": 110, "label": "Arazzo workflow — spans multiple services as one business process", "fill": "#fafafa"})
nodes += [
    {"x": 60, "y": y2 + 40, "w": 240, "h": 50, "lines": ["booking"], "style": "box"},
    {"x": 350, "y": y2 + 40, "w": 240, "h": 50, "lines": ["routing"], "style": "box"},
    {"x": 640, "y": y2 + 40, "w": 240, "h": 50, "lines": ["tracking"], "style": "box"},
]
edges.append({"x1": 300, "y1": y2 + 65, "x2": 350, "y2": y2 + 65, "amber": True})
edges.append({"x1": 590, "y1": y2 + 65, "x2": 640, "y2": y2 + 65, "amber": True})

# --- governance tier: local-only, out of CI ----------------------------------
y3 = y2 + 110 + 25
bands.append({"x": 20, "y": y3, "w": 900, "h": 160, "label": "governance tier — local-only, tier-gated OUT of CI", "fill": "#fff3e0"})
nodes += [
    {"x": 100, "y": y3 + 45, "w": 320, "h": 90, "lines": ["Apicurio Registry", "schema/artifact registry", "xRegistry touchpoint"], "style": "accent"},
    {"x": 520, "y": y3 + 45, "w": 320, "h": 90, "lines": ["OpenMetadata", "data catalog", "tracks schema/version history over time", "(not an xRegistry impl)"], "style": "accent"},
]
edges.append({"x1": 325, "y1": y2 + 110, "x2": 260, "y2": y3 + 45, "dashed": True})
edges.append({"x1": 815, "y1": y2 + 110, "x2": 680, "y2": y3 + 45, "dashed": True})

notes.append({"x": W / 2, "y": H - 12, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
              "text": "The schema is the single source of truth for both the sync (OpenAPI) and async (AsyncAPI) contracts. The governance tier runs locally only; it is deliberately excluded from the CI gate."})

generate_diagram.emit("21-multi-protocol-contracts", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
