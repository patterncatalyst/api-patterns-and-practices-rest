#!/usr/bin/env bash
# examples/26-minikube/run-minikube.sh
#
# Local runner for the Ch26 minikube deployment tier — NOT a verify.sh.
# This directory is a CLUSTER-TIER example (scripts/validate.py's
# CLUSTER_TIER_DIRS): it requires a real, running cluster, which the
# clusterless CI examples matrix can't provide, so there is deliberately no
# verify.sh here for that matrix to auto-discover and fail on. The repo's
# only CI coverage for this directory is the static `k8s-manifests` job
# (.github/workflows/contracts.yml): `kubectl kustomize examples/26-minikube/
# k8s | kubeconform -strict`. This script is how a reader actually BRINGS
# IT UP, by hand, on their own machine.
#
# Deploys the SAME two booking services as
# examples/25-local-with-docker-compose/{quarkus,python} (same Containerfiles,
# same source) onto a local minikube cluster — so the compose vs k8s
# contrast (README.md) is apples to apples: identical images, different
# deployment tier.
#
# Usage:
#   bash run-minikube.sh                    # driver=docker (default)
#   MINIKUBE_DRIVER=podman bash run-minikube.sh
#   MINIKUBE_PROFILE=my-profile bash run-minikube.sh
#
# Teardown (not run automatically — this script leaves the cluster up so
# you can poke at it):
#   minikube delete -p "${MINIKUBE_PROFILE:-ch26-booking}"
#
# Idempotent-ish: `minikube start` reuses an existing profile, `minikube
# image build` just rebuilds, `kubectl apply -k` reconciles — safe to
# re-run after a code change in examples/25-local-with-docker-compose.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CH25_DIR="$REPO_ROOT/examples/25-local-with-docker-compose"
K8S_DIR="$SCRIPT_DIR/k8s"

PROFILE="${MINIKUBE_PROFILE:-ch26-booking}"
DRIVER="${MINIKUBE_DRIVER:-docker}"
# This machine's ~/.minikube/config/config.json pins rootless:true (set for
# a podman-driver profile elsewhere) — the docker driver needs a rootless
# Docker context to honor that, which this host's Docker Engine isn't
# running under. MINIKUBE_ROOTLESS lets a caller override the on-disk
# default per invocation instead of this script silently fighting it;
# default here is "false" to match a normal (non-rootless) Docker Engine.
ROOTLESS="${MINIKUBE_ROOTLESS:-false}"
NAMESPACE="ch26-booking"
QUARKUS_IMAGE="booking/quarkus:1.0"
PYTHON_IMAGE="booking/python:1.0"
INGRESS_HOST="booking.ch26.local"

log() { echo "run-minikube.sh: $*" >&2; }

for bin in minikube kubectl; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    log "FAIL — required binary '$bin' not found on PATH"
    exit 1
  fi
done

if [[ ! -d "$CH25_DIR/quarkus" || ! -d "$CH25_DIR/python" ]]; then
  log "FAIL — expected Ch25 app sources at $CH25_DIR/{quarkus,python}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: cluster up.
# ---------------------------------------------------------------------------
log "=== Step 1: minikube start (profile=$PROFILE, driver=$DRIVER, rootless=$ROOTLESS) ==="
minikube start -p "$PROFILE" --driver="$DRIVER" --rootless="$ROOTLESS"

log "=== Step 2: enable ingress + metrics-server addons ==="
minikube addons enable ingress -p "$PROFILE"
minikube addons enable metrics-server -p "$PROFILE"

# ---------------------------------------------------------------------------
# Step 3: build the SAME Ch25 images straight into the cluster's image
# store. `minikube image build` is driver-agnostic (works the same for
# docker/podman/kvm2 drivers) and needs no `eval $(minikube docker-env)` /
# `minikube image load` round-trip — the image lands where the kubelet can
# see it with imagePullPolicy: IfNotPresent, no registry involved.
# ---------------------------------------------------------------------------
log "=== Step 3: build images into minikube (profile=$PROFILE) ==="
log "building $QUARKUS_IMAGE from $CH25_DIR/quarkus ..."
minikube image build -p "$PROFILE" -t "$QUARKUS_IMAGE" -f Containerfile "$CH25_DIR/quarkus"

log "building $PYTHON_IMAGE from $CH25_DIR/python ..."
minikube image build -p "$PROFILE" -t "$PYTHON_IMAGE" -f Containerfile "$CH25_DIR/python"

# ---------------------------------------------------------------------------
# Step 4: apply manifests, wait for rollout.
# ---------------------------------------------------------------------------
log "=== Step 4: kubectl apply -k ==="
kubectl --context "$PROFILE" apply -k "$K8S_DIR"

log "waiting for rollout ..."
kubectl --context "$PROFILE" -n "$NAMESPACE" rollout status deployment/quarkus-booking --timeout=240s
kubectl --context "$PROFILE" -n "$NAMESPACE" rollout status deployment/python-booking --timeout=180s

# ---------------------------------------------------------------------------
# Step 5: print the ingress URL + a sample curl.
# ---------------------------------------------------------------------------
MINIKUBE_IP="$(minikube ip -p "$PROFILE")"

log "=== Step 5: ready ==="
log "pods:"
kubectl --context "$PROFILE" -n "$NAMESPACE" get pods
log ""
log "ingress host '$INGRESS_HOST' resolves to the ingress-nginx controller at $MINIKUBE_IP:80."
log "No DNS entry needed — pass the Host header explicitly, or add a /etc/hosts line:"
log "  echo '$MINIKUBE_IP $INGRESS_HOST' | sudo tee -a /etc/hosts"
log ""
log "Sample booking request through the Ingress (path-routed to the Quarkus backend):"
cat >&2 <<EOF
  curl -sS -D - -X POST "http://$MINIKUBE_IP/quarkus/bookings" \\
    -H "Host: $INGRESS_HOST" \\
    -H 'Content-Type: application/json' \\
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

  # same request, routed to the Python backend instead — same Ingress, same
  # host, different path prefix:
  curl -sS -D - -X POST "http://$MINIKUBE_IP/python/bookings" \\
    -H "Host: $INGRESS_HOST" \\
    -H 'Content-Type: application/json' \\
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
EOF
log ""
log "HPA:"
kubectl --context "$PROFILE" -n "$NAMESPACE" get hpa
log ""
log "Teardown when done:"
log "  minikube delete -p $PROFILE"
