#!/usr/bin/env python3
"""Fig Appendix A — OpenShift Local (CRC) topology: a Route with edge TLS
terminating at the Service in front of the app pods; an in-cluster S2I
BuildConfig producing the image into the internal registry, driving a
DeploymentConfig/Deployment. A small note contrasts Route (OpenShift) with
Ingress (vanilla Kubernetes)."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 600

bands = [
    {"x": 20, "y": 20, "w": 900, "h": 460, "label": "OpenShift Local (CRC)", "fill": "#fafafa"},
]

nodes = [
    {"x": 50, "y": 70, "w": 120, "h": 50, "lines": ["Client"], "style": "user"},

    {"x": 230, "y": 60, "w": 220, "h": 70,
     "lines": ["Route", "edge TLS termination"], "style": "accent"},
    {"x": 510, "y": 60, "w": 200, "h": 70,
     "lines": ["Service", "booking-api"], "style": "box"},

    {"x": 560, "y": 170, "w": 130, "h": 60, "lines": ["pod"], "style": "sub"},
    {"x": 710, "y": 170, "w": 130, "h": 60, "lines": ["pod"], "style": "sub"},

    {"x": 510, "y": 270, "w": 200, "h": 70,
     "lines": ["DeploymentConfig", "/ Deployment"], "style": "accent"},

    {"x": 50, "y": 270, "w": 200, "h": 70,
     "lines": ["BuildConfig", "S2I source-to-image"], "style": "box"},
    {"x": 50, "y": 380, "w": 200, "h": 70,
     "lines": ["git source", "booking-api repo"], "style": "sub"},
    {"x": 280, "y": 380, "w": 220, "h": 70,
     "lines": ["internal image registry", "image-registry.openshift-image-registry.svc"], "style": "box"},
]

edges = [
    {"x1": 170, "y1": 95, "x2": 230, "y2": 95, "label": "HTTPS"},
    {"x1": 450, "y1": 95, "x2": 510, "y2": 95, "label": "TLS terminated here", "amber": True},

    {"x1": 610, "y1": 130, "x2": 625, "y2": 170},
    {"x1": 610, "y1": 130, "x2": 775, "y2": 170},

    {"x1": 610, "y1": 270, "x2": 610, "y2": 230, "label": "manages", "amber": True},

    {"x1": 150, "y1": 380, "x2": 150, "y2": 340, "label": "triggers build"},
    {"x1": 250, "y1": 415, "x2": 280, "y2": 415, "label": "pushes image"},
    {"x1": 390, "y1": 380, "x2": 610, "y2": 340, "label": "deploys", "amber": True},
]

notes = [
    {"x": W / 2, "y": 520, "size": 12, "color": "#1d1d1d", "anchor": "middle",
     "text": "Route vs. Ingress: a Route is OpenShift's own resource (host + TLS edge/passthrough/reencrypt on the Router); vanilla Kubernetes uses an Ingress against an Ingress controller instead — the two aren't interchangeable."},
    {"x": W / 2, "y": 560, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
     "text": "The cluster builds its own image from source via S2I and deploys it — no external registry or CI push required to run on CRC."},
]

generate_diagram.emit("appendix-a-openshift-crc", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
