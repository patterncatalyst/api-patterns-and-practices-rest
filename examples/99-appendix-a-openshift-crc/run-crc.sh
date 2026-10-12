#!/usr/bin/env bash
# examples/99-appendix-a-openshift-crc/run-crc.sh
#
# Local runner for Appendix A's OpenShift Local (CRC) tier — NOT a
# verify.sh. This directory is a CLUSTER-TIER example
# (scripts/validate.py's CLUSTER_TIER_DIRS): it needs a real, running
# OpenShift cluster, which the clusterless CI examples matrix can't
# provide, so there is deliberately no verify.sh here for that matrix to
# auto-discover and fail on. The repo's only CI coverage for this
# directory is the static `k8s-manifests` job
# (.github/workflows/contracts.yml): `helm lint` +
# `helm template | kubeconform -ignore-missing-schemas`. This script is how
# a reader actually brings it up, by hand, on their own machine.
#
# Deploys the SAME two booking services as
# examples/25-local-with-docker-compose/{quarkus,python} (same
# Containerfiles, same source — no third copy of the app), built IN the
# cluster by the chart's BuildConfig/ImageStream pair and exposed over
# edge-TLS Routes — see README.md for the full contrast with Ch26's
# minikube Ingress.
#
# Usage:
#   bash run-crc.sh                      # full sequence: build, deploy, wait, print Routes
#   bash run-crc.sh --skip-build         # redeploy only (images already built)
#   CRC_PROJECT=my-project bash run-crc.sh
#
# Prerequisites: crc, oc, helm on PATH; CRC set up and sized per
# references/prerequisites-and-sizing.md in the lgtm-crc skill (this
# appendix only needs the "core" sizing — two small stateless services, no
# Postgres/Kafka): `crc config set cpus 6; crc config set memory 20480;
# crc config set disk-size 80` while CRC is stopped, then `crc setup`.
#
# Teardown (not run automatically — this script leaves the cluster up so
# you can poke at it):
#   oc delete project appendix-a-booking
#   crc stop

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CH25_DIR="$REPO_ROOT/examples/25-local-with-docker-compose"
CHART_DIR="$SCRIPT_DIR/helm"

PROJECT="${CRC_PROJECT:-appendix-a-booking}"
RELEASE="appendix-a"
IMAGE_TAG="v1"
OCP_CONTEXT="${OCP_CONTEXT:-crc-admin}"
SKIP_BUILD=false

for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    *) echo "run-crc.sh: unknown argument '$arg'" >&2; exit 1 ;;
  esac
done

log() { echo "run-crc.sh: $*" >&2; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$1" >&2; }
fail() { printf '\nrun-crc.sh: FAIL — %s\n' "$1" >&2; exit 1; }

for bin in crc oc helm; do
  command -v "$bin" >/dev/null 2>&1 || fail "required binary '$bin' not found on PATH"
done

if [[ ! -d "$CH25_DIR/quarkus" || ! -d "$CH25_DIR/python" ]]; then
  fail "expected Ch25 app sources at $CH25_DIR/{quarkus,python}"
fi

# ---------------------------------------------------------------------------
# Step 1: CRC up, talking only to OpenShift Local. require_crc-style guard
# (see the lgtm-crc skill's templates/openshift/lib.sh): switch to the
# crc-admin kubeconfig context crc start writes and refuse any API server
# that isn't api.crc.testing. No password is ever read, typed or printed —
# if the web console login is needed, the user runs `crc console
# --credentials` themselves.
# ---------------------------------------------------------------------------
step "Step 1: OpenShift Local (CRC)"
if ! crc status 2>/dev/null | grep -q 'OpenShift:.*Running'; then
  log "CRC is not running — starting it (this can take 10-15 min on first start)."
  log "If this is the first run, make sure you've sized the VM while it was"
  log "stopped (crc config set cpus/memory/disk-size) and have a pull secret:"
  log "  crc start --pull-secret-file <path-to-pull-secret.txt>"
  crc start || fail "crc start failed — see 'crc start' output above"
fi
eval "$(crc oc-env)"
oc config use-context "$OCP_CONTEXT" >/dev/null 2>&1 \
  || fail "kubeconfig context $OCP_CONTEXT not found (crc start writes it)"
api="$(oc whoami --show-server 2>/dev/null)" || fail "cannot reach the OpenShift API"
[[ "$api" == *api.crc.testing* ]] || fail "context $OCP_CONTEXT points at $api, not OpenShift Local"
log "talking to $api as $(oc whoami)"

# ---------------------------------------------------------------------------
# Step 2: project + chart skeleton (BuildConfig/ImageStream need to exist
# before oc start-build can target them).
# ---------------------------------------------------------------------------
step "Step 2: project + chart (Routes/BuildConfigs/ImageStreams/ConfigMap/Secret)"
oc get project "$PROJECT" >/dev/null 2>&1 || oc new-project "$PROJECT" >/dev/null
helm upgrade --install "$RELEASE" "$CHART_DIR" --namespace "$PROJECT" \
  --set "image.tag=$IMAGE_TAG"

# ---------------------------------------------------------------------------
# Step 3: in-cluster build — Docker strategy, binary input, the Ch25
# Containerfiles unmodified. No podman/docker push, no registry
# credentials: `oc start-build --from-dir` streams the source tree to the
# cluster and the build pod does the rest.
# ---------------------------------------------------------------------------
if [[ "$SKIP_BUILD" == true ]]; then
  log "Step 3: skipped (--skip-build)"
else
  step "Step 3: in-cluster builds (Docker-strategy BuildConfig, binary input)"
  log "building quarkus-booking from $CH25_DIR/quarkus ..."
  oc start-build quarkus-booking -n "$PROJECT" --from-dir="$CH25_DIR/quarkus" --follow \
    || fail "quarkus-booking build failed (oc get builds -n $PROJECT; oc logs -f bc/quarkus-booking -n $PROJECT)"

  log "building python-booking from $CH25_DIR/python ..."
  oc start-build python-booking -n "$PROJECT" --from-dir="$CH25_DIR/python" --follow \
    || fail "python-booking build failed (oc get builds -n $PROJECT; oc logs -f bc/python-booking -n $PROJECT)"

  for svc in quarkus-booking python-booking; do
    ref="$(oc get istag "$svc:$IMAGE_TAG" -n "$PROJECT" -o jsonpath='{.image.dockerImageReference}' 2>/dev/null)" \
      || fail "no ImageStream tag $svc:$IMAGE_TAG after build"
    log "$svc:$IMAGE_TAG -> ${ref##*@}"
  done
fi

# ---------------------------------------------------------------------------
# Step 4: roll the Deployments to pick up whatever the build just pushed
# (imagePullPolicy: Always means a restart is enough — no tag bump needed).
# ---------------------------------------------------------------------------
step "Step 4: rollout"
oc rollout restart deployment/quarkus-booking deployment/python-booking -n "$PROJECT"
oc rollout status deployment/quarkus-booking -n "$PROJECT" --timeout=240s
oc rollout status deployment/python-booking -n "$PROJECT" --timeout=180s

# ---------------------------------------------------------------------------
# Step 5: print both Route URLs + a sample curl.
# ---------------------------------------------------------------------------
step "Step 5: ready"
oc get pods -n "$PROJECT"

QUARKUS_HOST="$(oc get route quarkus-booking -n "$PROJECT" -o jsonpath='{.spec.host}')"
PYTHON_HOST="$(oc get route python-booking -n "$PROJECT" -o jsonpath='{.spec.host}')"

log ""
log "Routes (edge TLS; plain HTTP redirects to HTTPS):"
log "  quarkus-booking: https://$QUARKUS_HOST"
log "  python-booking:  https://$PYTHON_HOST"
log ""
log "Sample booking request through the Quarkus Route (self-signed router"
log "cert on CRC — curl -k skips verification for this local demo only):"
cat >&2 <<EOF
  curl -sSk -D - -X POST "https://$QUARKUS_HOST/bookings" \\
    -H 'Content-Type: application/json' \\
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

  # same request, the Python backend's own Route:
  curl -sSk -D - -X POST "https://$PYTHON_HOST/bookings" \\
    -H 'Content-Type: application/json' \\
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
EOF
log ""
log "Teardown when done:"
log "  oc delete project $PROJECT"
log "  crc stop"
