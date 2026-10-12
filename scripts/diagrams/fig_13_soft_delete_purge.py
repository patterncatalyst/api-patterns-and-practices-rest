#!/usr/bin/env python3
"""Fig 13 — Ch13: soft delete vs purge. DELETE sets CANCELLED, writes an
audit record, and hides the booking from default queries while it stays
addressable by id; a separate, retention-governed purge job later performs
the actual hard delete."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 980, 760

bands = [
    {"x": 20, "y": 255, "w": 940, "h": 110, "label": "Soft delete — hidden by default, still addressable", "fill": "#fafafa"},
    {"x": 290, "y": 385, "w": 440, "h": 335, "label": "Purge — hard delete under retention rule", "fill": "#fff3e0"},
]

nodes = [
    {"x": 360, "y": 20, "w": 260, "h": 70,
     "lines": ["Client", "DELETE /bookings/{id}"], "style": "user"},
    {"x": 330, "y": 130, "w": 320, "h": 100,
     "lines": ["Soft delete (DELETE handler)", "status → CANCELLED",
               "write audit record", "excluded from default list queries"], "style": "accent"},

    {"x": 60, "y": 270, "w": 280, "h": 80,
     "lines": ["GET /bookings (default)", "200 OK, not in results"], "style": "box"},
    {"x": 400, "y": 270, "w": 280, "h": 80,
     "lines": ["GET /bookings/{id}", "200 OK, status: CANCELLED", "still addressable for audit"], "style": "box"},
    {"x": 700, "y": 270, "w": 260, "h": 80,
     "lines": ["GET /bookings?includeCancelled=true", "200 OK, appears in results"], "style": "box"},

    {"x": 330, "y": 410, "w": 320, "h": 90,
     "lines": ["Purge job (scheduled)", "runs under retention/compliance rule",
               "e.g. CANCELLED > 90 days"], "style": "ink"},
    {"x": 360, "y": 540, "w": 260, "h": 80,
     "lines": ["Hard delete", "row removed from storage"], "style": "box"},
    {"x": 360, "y": 660, "w": 260, "h": 70,
     "lines": ["GET /bookings/{id}", "404 Not Found"], "style": "accent"},
]

edges = [
    {"x1": 490, "y1": 90, "x2": 490, "y2": 130, "label": "DELETE"},
    {"x1": 400, "y1": 230, "x2": 200, "y2": 270, "label": "excluded from results"},
    {"x1": 490, "y1": 230, "x2": 540, "y2": 270, "label": "still 200 (audit)"},
    {"x1": 580, "y1": 230, "x2": 830, "y2": 270, "label": "visible if asked"},

    {"x1": 540, "y1": 350, "x2": 490, "y2": 410, "label": "retention window elapses", "amber": True, "dashed": True},
    {"x1": 490, "y1": 500, "x2": 490, "y2": 540, "label": "executes"},
    {"x1": 490, "y1": 620, "x2": 490, "y2": 660, "label": "row gone"},
]

notes = [
    {"x": 490, "y": 745, "text": "Soft delete preserves the audit trail and default-query hygiene; purge is the only step that actually removes data, and only under a retention rule.",
     "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True},
]

generate_diagram.emit("13-soft-delete-purge", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
