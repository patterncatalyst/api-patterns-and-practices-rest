#!/usr/bin/env bash
# examples/20-openapi-depth/verify.sh
#
# Ch20 OpenAPI-in-depth anchor. For EACH stack (Quarkus, FastAPI) this
# asserts:
#
#   1. The stack's OpenAPI document is served (200, valid JSON) at its
#      native path — Quarkus /q/openapi?format=json, Python /openapi.json.
#   2. The document contains a modern/OpenAPI-3.1 construct: a JSON-Schema
#      `type` array nullable (or OAS-3.0 `nullable: true`), AND a non-empty
#      top-level `webhooks` section.
#   3. DRIFT CHECK: the document's own Booking schema declares the SAME SET
#      of required property names as #/$defs/Booking in the shared contract
#      (contracts/schemas/shipping.schema.json) — normalized, not
#      byte-equal. See check_openapi.py.
#   4. A live POST -> GET booking round trip returns 200/201 with a body
#      that schema-validates against #/$defs/Booking.
#
# See README.md for the "drift probe" — how to deliberately break each
# assertion and watch this script fail.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch20-openapi"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"
CHECK_OPENAPI_PY="$SCRIPT_DIR/check_openapi.py"
CONTRACT_SCHEMA="$REPO_ROOT/contracts/schemas/shipping.schema.json"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

fail() {
  echo "lib.sh: FAIL — $*" >&2
  return 1
}

# ---------------------------------------------------------------------------
# Step 1: prove the validation gate has teeth before trusting it for
# anything below.
# ---------------------------------------------------------------------------

ensure_verify_venv

echo "=== Step 1: validate_response.py --selftest ==="
"$LGTM_VERIFY_VENV_DIR/bin/python" -I "$VALIDATE_RESPONSE_PY" --selftest

# ---------------------------------------------------------------------------
# Step 2: bring the stack up.
# ---------------------------------------------------------------------------

echo
echo "=== Step 2: docker compose up ==="
compose_up "$COMPOSE_FILE" "$PROJECT"

wait_for_http "http://localhost:8100/q/health" 90
wait_for_http "http://localhost:8020/health" 60

# ---------------------------------------------------------------------------
# Step 3: for EACH stack — fetch the OpenAPI doc, run the structural checks,
# then drive a live create -> read booking round trip.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2" openapi_url="$3"
  local openapi_file="$TMP_DIR/${stack}-openapi.json"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- OpenAPI document served, 200, valid JSON ---------------------------
  local status
  status="$(curl -sS -o "$openapi_file" -w '%{http_code}' "$openapi_url")"
  assert_status 200 "$status" "$stack GET $openapi_url"
  python3 -I -c "import json,sys; json.load(open(sys.argv[1]))" "$openapi_file" \
    || fail "$stack OpenAPI document at $openapi_url is not valid JSON"
  echo "lib.sh: ok — $stack OpenAPI document parses as JSON"

  # -- Structural checks: nullable construct, webhooks, required-set drift
  python3 -I "$CHECK_OPENAPI_PY" "$stack" "$openapi_file" "$CONTRACT_SCHEMA"

  # -- POST /bookings -> 201, Location, Booking ---------------------------
  local create_payload
  create_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  assert_header Location "$headers_file" "$stack POST /bookings"
  validate_body Booking "$body_file"

  local location
  location="$(grep -i '^Location:' "$headers_file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n')"
  case "$location" in
    http://*|https://*) : ;;
    *) location="${base}${location}" ;;
  esac

  # -- GET the Location -> 200, Booking ------------------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$location")"
  assert_status 200 "$status" "$stack GET Location"
  validate_body Booking "$body_file"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8100" "http://localhost:8100/q/openapi?format=json"
run_stack_tests "python" "http://localhost:8020" "http://localhost:8020/openapi.json"

echo
echo "PASS — Ch20 OpenAPI-in-depth anchor: both Quarkus and FastAPI serve an" \
     "OpenAPI document containing a JSON-Schema nullable construct and a" \
     "non-empty top-level webhooks section, that document's Booking schema" \
     "required-field set matches contracts/schemas/shipping.schema.json," \
     "and a live create->read booking round trip validates against" \
     "#/\$defs/Booking on both stacks."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
