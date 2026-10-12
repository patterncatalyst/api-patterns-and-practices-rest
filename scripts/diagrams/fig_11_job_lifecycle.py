#!/usr/bin/env python3
"""Fig 11 — Ch11: a rerunnable, server-owned job. The configure/enable step
(the schedule) is a separate resource from the run records it produces,
whether fired by the scheduler on an interval or triggered on demand; each
run moves through its own PENDING → RUNNING → SUCCEEDED/FAILED state."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 960, 660

nodes = [
    {"x": 40, "y": 20, "w": 260, "h": 80,
     "lines": ["Admin", "POST /jobs/manifest-reconcile", "{\"enabled\":true,\"intervalMinutes\":15}"], "style": "user"},
    {"x": 620, "y": 20, "w": 300, "h": 80,
     "lines": ["Caller", "POST /jobs/manifest-reconcile/runs", "run now (ad hoc)"], "style": "user"},

    {"x": 40, "y": 150, "w": 260, "h": 80,
     "lines": ["Job definition", "server-owned, singleton", "enabled=true, interval=15m"], "style": "accent"},
    {"x": 360, "y": 150, "w": 240, "h": 80,
     "lines": ["Scheduler", "fires every interval"], "style": "ink"},

    {"x": 360, "y": 280, "w": 240, "h": 70,
     "lines": ["Run record created", "jobId + runId, state: PENDING"], "style": "box"},

    {"x": 360, "y": 400, "w": 240, "h": 70,
     "lines": ["state: RUNNING", "executing reconcile"], "style": "ink"},

    {"x": 150, "y": 520, "w": 220, "h": 80,
     "lines": ["state: SUCCEEDED", "reconcile applied"], "style": "accent"},
    {"x": 560, "y": 520, "w": 220, "h": 80,
     "lines": ["state: FAILED", "error recorded, retry per policy"], "style": "box"},
]

edges = [
    {"x1": 170, "y1": 100, "x2": 170, "y2": 150, "label": "configure/enable"},
    {"x1": 300, "y1": 190, "x2": 360, "y2": 190, "label": "drives"},
    {"x1": 480, "y1": 230, "x2": 480, "y2": 280, "label": "new run (interval)"},
    {"x1": 770, "y1": 100, "x2": 600, "y2": 300, "label": "new run (ad hoc)", "amber": True, "dashed": True},

    {"x1": 480, "y1": 350, "x2": 480, "y2": 400, "label": "picked up"},
    {"x1": 440, "y1": 470, "x2": 270, "y2": 520, "label": "success"},
    {"x1": 530, "y1": 470, "x2": 670, "y2": 520, "label": "error", "amber": True, "dashed": True},
]

notes = [
    {"x": 480, "y": 630, "text": "The job definition (schedule) and a run record (execution) are separate resources — the schedule never changes state; each run does.",
     "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True},
]

generate_diagram.emit("11-job-lifecycle", W, H, nodes=nodes, edges=edges, notes=notes)
