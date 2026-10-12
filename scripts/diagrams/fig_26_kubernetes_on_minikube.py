#!/usr/bin/env python3
"""Fig 26 — Ch26: mapping the Compose stack onto Kubernetes on minikube. A
left "Compose" lane and a right "minikube" lane show compose service ->
Deployment+Service, compose networking -> Ingress, plus the K8s-only
concepts this chapter adds: liveness/readiness probes, ConfigMap + Secret,
and an HPA autoscaling the app pods. An Ingress routes to the app pods."""
import sys
sys.path.insert(0, "scripts")
import generate_diagram
generate_diagram.OUT = "assets/diagrams"

W, H = 940, 660

LANE_COMPOSE = {"x": 30, "w": 390}
LANE_K8S = {"x": 500, "w": 410}

bands = [
    {"x": LANE_COMPOSE["x"] - 10, "y": 20, "w": LANE_COMPOSE["w"] + 20, "h": 600, "label": "docker compose", "fill": "#fafafa"},
    {"x": LANE_K8S["x"] - 10, "y": 20, "w": LANE_K8S["w"] + 20, "h": 600, "label": "minikube", "fill": "#fff8ef"},
]

nodes = [
    # Compose lane
    {"x": LANE_COMPOSE["x"], "y": 60, "w": LANE_COMPOSE["w"], "h": 60,
     "lines": ["service: booking-api", "image + ports + env"], "style": "box"},
    {"x": LANE_COMPOSE["x"], "y": 150, "w": LANE_COMPOSE["w"], "h": 60,
     "lines": ["compose networking", "published ports, service DNS"], "style": "box"},
    {"x": LANE_COMPOSE["x"], "y": 240, "w": LANE_COMPOSE["w"], "h": 60,
     "lines": ["environment:", "inline env vars"], "style": "box"},
    {"x": LANE_COMPOSE["x"], "y": 330, "w": LANE_COMPOSE["w"], "h": 60,
     "lines": ["restart: unless-stopped"], "style": "box"},
    {"x": LANE_COMPOSE["x"], "y": 420, "w": LANE_COMPOSE["w"], "h": 60,
     "lines": ["fixed replica count", "no autoscaling"], "style": "box"},

    # K8s lane
    {"x": LANE_K8S["x"], "y": 60, "w": LANE_K8S["w"], "h": 70,
     "lines": ["Deployment + Service", "booking-api"], "style": "accent"},
    {"x": LANE_K8S["x"], "y": 150, "w": LANE_K8S["w"], "h": 70,
     "lines": ["Ingress", "routes external traffic to the Service"], "style": "accent"},
    {"x": LANE_K8S["x"], "y": 250, "w": LANE_K8S["w"], "h": 70,
     "lines": ["ConfigMap + Secret", "mounted env / files"], "style": "accent"},
    {"x": LANE_K8S["x"], "y": 340, "w": LANE_K8S["w"], "h": 70,
     "lines": ["liveness + readiness probes", "restart vs. remove-from-Service"], "style": "accent"},
    {"x": LANE_K8S["x"], "y": 430, "w": LANE_K8S["w"], "h": 70,
     "lines": ["HorizontalPodAutoscaler", "scales replicas on CPU/metrics"], "style": "accent"},

    # pods under the deployment, routed by ingress
    {"x": LANE_K8S["x"] + 20, "y": 540, "w": 150, "h": 60, "lines": ["pod", "booking-api"], "style": "sub"},
    {"x": LANE_K8S["x"] + 220, "y": 540, "w": 150, "h": 60, "lines": ["pod", "booking-api"], "style": "sub"},

    {"x": 170, "y": 540, "w": 120, "h": 50, "lines": ["Client"], "style": "user"},
]

edges = [
    {"x1": LANE_COMPOSE["x"] + LANE_COMPOSE["w"], "y1": 90, "x2": LANE_K8S["x"], "y2": 95, "label": "maps to"},
    {"x1": LANE_COMPOSE["x"] + LANE_COMPOSE["w"], "y1": 180, "x2": LANE_K8S["x"], "y2": 185, "label": "maps to"},
    {"x1": LANE_COMPOSE["x"] + LANE_COMPOSE["w"], "y1": 270, "x2": LANE_K8S["x"], "y2": 285, "label": "maps to"},
    {"x1": LANE_COMPOSE["x"] + LANE_COMPOSE["w"], "y1": 360, "x2": LANE_K8S["x"], "y2": 375, "label": "maps to"},
    {"x1": LANE_COMPOSE["x"] + LANE_COMPOSE["w"], "y1": 450, "x2": LANE_K8S["x"], "y2": 465, "label": "new in K8s"},

    {"x1": 230, "y1": 540, "x2": 230, "y2": 220, "dashed": True},
    {"x1": LANE_K8S["x"] + 95, "y1": 220, "x2": LANE_K8S["x"] + 95, "y2": 570, "label": "routes to", "amber": True},
    {"x1": LANE_K8S["x"] + 95, "y1": 570, "x2": LANE_K8S["x"] + 295, "y2": 570, "amber": True},
]

notes = [
    {"x": W / 2, "y": 630, "size": 12, "color": "#b8650a", "anchor": "middle", "bold": True,
     "text": "Each Compose concept has a direct Kubernetes counterpart; probes, ConfigMap/Secret, and the HPA are capabilities Compose doesn't have at all."},
]

generate_diagram.emit("26-kubernetes-on-minikube", W, H, bands=bands, nodes=nodes, edges=edges, notes=notes)
