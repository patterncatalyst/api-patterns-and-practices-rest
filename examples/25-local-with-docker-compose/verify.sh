#!/usr/bin/env bash
# examples/25-local-with-docker-compose/verify.sh
#
# Ch25 local-with-docker-compose anchor — proves a single request is traced
# END TO END through the local LGTM stack, on BOTH implementations. This is
# the chapter's risk gate: the trace assertion must be DETERMINISTIC
# (a fixed, known trace id — never "search and hope") and BOUNDED (a short
# poll with a hard timeout, so a missing trace FAILS FAST instead of
# hanging CI).
#
#   1. validate_response.py --selftest       — the contract gate has teeth.
#   2. docker compose up                     — both apps, postgres, lgtm.
#      wait_for_http both apps' health AND Tempo's query API (/ready).
#   3. For EACH stack: POST /bookings with a FIXED W3C `traceparent` header
#      (a distinct fixed trace id per stack) -> 201 + Location, body
#      validates against #/$defs/Booking.
#   4. Poll Tempo's `GET /api/traces/<fixed-trace-id>` (bounded, sleep-poll,
#      hard timeout) until the trace appears, then assert the trace JSON
#      contains a span whose resource carries that stack's service.name
#      AND a span tagged with the booking POST's HTTP route/method.
#   5. Print PASS, tear the stack down.
#
# See README.md for the full LGTM/Grafana walkthrough and the drift probe
# (point the exporter at a dead endpoint and watch Step 4 fail at timeout).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch25-compose"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

QUARKUS_BASE="http://localhost:8105"
PYTHON_BASE="http://localhost:8024"
TEMPO_BASE="http://localhost:3200"

# Fixed, distinct 32-hex-char W3C trace ids — one per stack. Picked by hand
# (not random) so every run looks up the EXACT SAME trace id it just POSTed
# with: a deterministic, repeatable assertion rather than "find whatever
# trace id the app happened to generate."
QUARKUS_TRACE_ID="1111111111111111aaaaaaaaaaaaaaaa"
QUARKUS_PARENT_SPAN_ID="fedcba9876543210"
PYTHON_TRACE_ID="2222222222222222bbbbbbbbbbbbbbbb"
PYTHON_PARENT_SPAN_ID="0123456789abcdef"

# Bounded poll for the Tempo trace lookup (Step 4): the BatchSpanProcessor
# on both stacks flushes on a ~5s schedule, so give it a few cycles — but
# cap it hard. A missing trace must FAIL FAST here, not hang the suite.
TRACE_POLL_TIMEOUT=30
TRACE_POLL_INTERVAL=2

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

fail() {
  echo "verify.sh: FAIL — $*" >&2
  return 1
}

# ---------------------------------------------------------------------------
# Step 1: prove the contract-validation gate has teeth before trusting it.
# ---------------------------------------------------------------------------

ensure_verify_venv

echo "=== Step 1: validate_response.py --selftest ==="
"$LGTM_VERIFY_VENV_DIR/bin/python" -I "$VALIDATE_RESPONSE_PY" --selftest

# ---------------------------------------------------------------------------
# Step 2: bring the stack up — both apps, postgres, lgtm (lgtm is a
# DEFAULT service for this chapter, not profile-gated). Health-gate on
# BOTH apps' health endpoints AND Tempo's query API before sending traffic.
# ---------------------------------------------------------------------------

echo
echo "=== Step 2: docker compose up ==="
compose_up "$COMPOSE_FILE" "$PROJECT"

wait_for_http "$QUARKUS_BASE/q/health" 90
wait_for_http "$PYTHON_BASE/health" 60
wait_for_http "$TEMPO_BASE/ready" 60

# ---------------------------------------------------------------------------
# Step 3 + 4: per-stack — POST with a fixed traceparent, assert the
# response, then poll Tempo for that EXACT trace id (bounded).
# ---------------------------------------------------------------------------

CREATE_PAYLOAD='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

# poll_for_trace <trace-id> <out-file>
#
# Bounded sleep-poll of Tempo's trace-by-id endpoint. Returns 0 and leaves
# the trace JSON in <out-file> once Tempo returns 200; returns 1 (FAIL
# FAST, no infinite loop) once TRACE_POLL_TIMEOUT elapses with no 200.
poll_for_trace() {
  local trace_id="$1" out_file="$2"
  local waited=0 code

  echo "verify.sh: polling Tempo for trace $trace_id (timeout ${TRACE_POLL_TIMEOUT}s) ..." >&2
  while (( waited < TRACE_POLL_TIMEOUT )); do
    code="$(curl -sS -o "$out_file" -w '%{http_code}' \
      -H 'Accept: application/json' \
      "$TEMPO_BASE/api/traces/$trace_id" || echo "000")"
    if [[ "$code" == "200" ]]; then
      echo "verify.sh: ok — Tempo returned trace $trace_id after ${waited}s" >&2
      return 0
    fi
    sleep "$TRACE_POLL_INTERVAL"
    waited=$(( waited + TRACE_POLL_INTERVAL ))
  done

  echo "verify.sh: FAIL — Tempo never returned trace $trace_id within ${TRACE_POLL_TIMEOUT}s (last HTTP code: ${code:-none})" >&2
  return 1
}

# assert_trace_has_service_and_route <trace-file> <service-name> <context>
#
# Structural checks against the Tempo trace JSON (resilient to whether the
# payload nests spans under "batches" or "resourceSpans" — walks the whole
# document with jq's `..` rather than assuming one shape):
#   - some RESOURCE attribute: key=="service.name", value==<service-name>
#   - some SPAN attribute: key in {http.route,url.path,http.target},
#     value=="/bookings"
#   - some SPAN attribute: key in {http.request.method,http.method},
#     value=="POST"
assert_trace_has_service_and_route() {
  local trace_file="$1" service_name="$2" context="$3"
  local has_service has_route has_method

  has_service="$(jq --arg svc "$service_name" '
    [.. | objects | select(has("key") and has("value"))
        | select(.key == "service.name") | .value.stringValue]
    | any(. == $svc)
  ' "$trace_file")"

  has_route="$(jq '
    [.. | objects | select(has("key") and has("value"))
        | select(.key == "http.route" or .key == "url.path" or .key == "http.target")
        | .value.stringValue]
    | any(. == "/bookings")
  ' "$trace_file")"

  has_method="$(jq '
    [.. | objects | select(has("key") and has("value"))
        | select(.key == "http.request.method" or .key == "http.method")
        | .value.stringValue]
    | any(. == "POST")
  ' "$trace_file")"

  if [[ "$has_service" != "true" ]]; then
    echo "verify.sh: FAIL — $context: no resource with service.name=$service_name in the Tempo trace" >&2
    return 1
  fi
  if [[ "$has_route" != "true" ]]; then
    echo "verify.sh: FAIL — $context: no span tagged with HTTP route /bookings in the Tempo trace" >&2
    return 1
  fi
  if [[ "$has_method" != "true" ]]; then
    echo "verify.sh: FAIL — $context: no span tagged with HTTP method POST in the Tempo trace" >&2
    return 1
  fi
  echo "verify.sh: ok — $context: Tempo trace has service.name=$service_name, POST /bookings span" >&2
}

run_traced_booking() {
  local stack="$1" base="$2" trace_id="$3" parent_span_id="$4" service_name="$5"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"
  local trace_file="$TMP_DIR/${stack}-trace.json"
  local traceparent="00-${trace_id}-${parent_span_id}-01"

  echo
  echo "=== Step 3: traced POST /bookings — '$stack' at $base (trace $trace_id) ==="

  local status
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -H "traceparent: $traceparent" \
    -d "$CREATE_PAYLOAD" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  assert_header Location "$headers_file" "$stack POST /bookings"
  validate_body Booking "$body_file"

  echo
  echo "=== Step 4: Tempo trace lookup — '$stack' (trace $trace_id) ==="
  poll_for_trace "$trace_id" "$trace_file"
  assert_trace_has_service_and_route "$trace_file" "$service_name" "$stack trace"
}

run_traced_booking "quarkus" "$QUARKUS_BASE" "$QUARKUS_TRACE_ID" "$QUARKUS_PARENT_SPAN_ID" "shipping-quarkus"
run_traced_booking "python" "$PYTHON_BASE" "$PYTHON_TRACE_ID" "$PYTHON_PARENT_SPAN_ID" "shipping-python"

# ---------------------------------------------------------------------------
# Step 5: PASS, then explicit teardown (belt-and-suspenders with lib.sh's
# EXIT trap — compose_down is idempotent/safe to call twice).
# ---------------------------------------------------------------------------

echo
echo "PASS — Ch25 local-with-docker-compose anchor: both stacks' bookings" \
     "validate against #/\$defs/Booking, and a real exported trace was" \
     "found in Tempo for each (fixed trace id, correct service.name," \
     "POST /bookings span)."

compose_down "$COMPOSE_FILE" "$PROJECT"
