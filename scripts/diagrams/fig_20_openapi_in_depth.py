#!/usr/bin/env python3
"""Fig 20 — Ch20: OpenAPI as a living contract. A developer edits the
committed contract; both stacks generate/serve their own OpenAPI document at
runtime; a drift check diffs the live-generated spec against the committed
one; CI is green when they agree and red when they diverge. Deliberate
divergence is designed to fail CI."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 620

bands, nodes, edges, notes = [], [], [], []

# --- Lane 1: source of truth -------------------------------------------------
y0 = 25
bands.append({"x": 20, "y": y0, "w": 900, "h": 100, "label": "source of truth (committed to the repo)", "fill": "#fff8ef"})
nodes += [
    {"x": 60, "y": y0 + 35, "w": 160, "h": 50, "lines": ["Developer"], "style": "user"},
    {"x": 390, "y": y0 + 35, "w": 220, "h": 50, "lines": ["contracts/openapi.yaml", "edits the contract"], "style": "accent"},
]
edges.append({"x1": 220, "y1": y0 + 60, "x2": 390, "y2": y0 + 60})

# --- Lane 2: both stacks generate/serve their own OpenAPI doc at runtime ---
y1 = y0 + 100 + 25
bands.append({"x": 20, "y": y1, "w": 900, "h": 140, "label": "runtime generation — each stack derives its own OpenAPI document from code", "fill": "#fafafa"})
nodes += [
    {"x": 100, "y": y1 + 35, "w": 300, "h": 80, "lines": ["Quarkus app", "JAX-RS + SmallRye OpenAPI", "serves /q/openapi"], "style": "box"},
    {"x": 540, "y": y1 + 35, "w": 300, "h": 80, "lines": ["FastAPI app", "Pydantic models", "serves /openapi.json"], "style": "box"},
]
edges.append({"x1": 500, "y1": y0 + 85, "x2": 250, "y2": y1 + 35, "dashed": True})
edges.append({"x1": 500, "y1": y0 + 85, "x2": 690, "y2": y1 + 35, "dashed": True})

# --- Lane 3: drift check -----------------------------------------------------
y2 = y1 + 140 + 25
bands.append({"x": 20, "y": y2, "w": 900, "h": 140, "label": "CI drift check", "fill": "#fafafa"})
nodes += [
    {"x": 100, "y": y2 + 45, "w": 300, "h": 60, "lines": ["live-generated spec", "(from /q/openapi)"], "style": "sub"},
    {"x": 540, "y": y2 + 45, "w": 300, "h": 60, "lines": ["live-generated spec", "(from /openapi.json)"], "style": "sub"},
    {"x": 320, "y": y2 + 5, "w": 300, "h": 30, "lines": ["diff against contracts/openapi.yaml"], "style": "accent"},
]
edges.append({"x1": 250, "y1": y1 + 115, "x2": 250, "y2": y2 + 45, "amber": True})
edges.append({"x1": 690, "y1": y1 + 115, "x2": 690, "y2": y2 + 45, "amber": True})
edges.append({"x1": 250, "y1": y2 + 45, "x2": 420, "y2": y2 + 20, "amber": True})
edges.append({"x1": 690, "y1": y2 + 45, "x2": 620, "y2": y2 + 20, "amber": True})

# --- Lane 4: CI gate (green vs red) -----------------------------------------
y3 = y2 + 140 + 25
bands.append({"x": 20, "y": y3, "w": 900, "h": 120, "label": "CI gate", "fill": "#fff8ef"})
nodes += [
    {"x": 160, "y": y3 + 35, "w": 280, "h": 60, "lines": ["specs agree", "CI: GREEN — merge allowed"], "style": "accent"},
    {"x": 500, "y": y3 + 35, "w": 280, "h": 60, "lines": ["specs diverge", "CI: RED — build fails"], "style": "box"},
]
edges.append({"x1": 470, "y1": y2 + 35, "x2": 300, "y2": y3 + 35, "amber": True, "label": "match"})
edges.append({"x1": 470, "y1": y2 + 35, "x2": 640, "y2": y3 + 35, "label": "mismatch"})

notes.append({"x": W / 2, "y": H - 12, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
              "text": "The committed contract is the source of truth; code must match it exactly. A deliberate divergence test proves the drift check actually fails CI, not just that it runs."})

generate_diagram.emit("20-openapi-in-depth", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
