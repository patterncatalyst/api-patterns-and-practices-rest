#!/usr/bin/env python3
"""Fig 24 — Ch24: the REST test pyramid for this project, as stacked bands
bottom-to-top: (a) contract tests against OpenAPI + AsyncAPI/CloudEvents,
(b) integration tests (@QuarkusTest + pytest against a live app),
(c) end-to-end API tests via Newman (Postman collection against both live
stacks), (d) load tests (vendored CNDP harness, tiny/bounded)."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 620

bands, nodes, edges, notes = [], [], [], []

LAYER_W = [860, 680, 500, 320]
LAYER_X = [40, 130, 220, 310]
LAYER_Y = [430, 320, 210, 100]
LAYER_H = 90

labels = [
    (["contract tests", "validate against OpenAPI + AsyncAPI/CloudEvents contracts"], "box", "#fafafa"),
    (["integration tests", "@QuarkusTest + pytest against a live app"], "box", "#fafafa"),
    (["end-to-end API tests", "Newman (Postman collection) against both live stacks"], "accent", "#fff8ef"),
    (["load tests", "vendored CNDP harness — tiny, bounded"], "accent", "#fff3e0"),
]

for i, (lines, style, fill) in enumerate(labels):
    bx, by, bw = LAYER_X[i], LAYER_Y[i], LAYER_W[i]
    bands.append({"x": bx - 10, "y": by - 10, "w": bw + 20, "h": LAYER_H + 20, "label": "", "fill": fill})
    nodes.append({"x": bx, "y": by, "w": bw, "h": LAYER_H, "lines": lines, "style": style})

# connect layers with upward arrows (narrow set)
for i in range(3):
    cx_lo = LAYER_X[i] + LAYER_W[i] / 2
    cx_hi = LAYER_X[i + 1] + LAYER_W[i + 1] / 2
    edges.append({"x1": cx_lo, "y1": LAYER_Y[i] - 10, "x2": cx_hi, "y2": LAYER_Y[i + 1] + LAYER_H + 10, "amber": True})

nodes.append({"x": 40, "y": 20, "w": 860, "h": 50, "lines": ["more tests, faster feedback, cheaper to run"], "style": "sub"})
nodes.append({"x": 40, "y": 540, "w": 860, "h": 50, "lines": ["fewer tests, slower feedback, more expensive to run"], "style": "sub"})

notes.append({"x": W / 2, "y": H - 12, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
              "text": "Most coverage lives in fast contract and integration tests; Newman end-to-end runs confirm both stacks agree at the wire; the load-test layer stays intentionally small and bounded."})

generate_diagram.emit("24-testing-rest-apis", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
