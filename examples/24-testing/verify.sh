#!/usr/bin/env bash
# examples/24-testing/verify.sh
#
# Ch24 testing anchor — proves the test pyramid for a REST API, CI-critical
# layers only:
#
#   1. Contract tests    — every live response schema-validated against
#                           contracts/schemas/shipping.schema.json
#                           (validate_response.py, via lib.sh).
#   2. Integration tests — @QuarkusTest / pytest. REAL, included, runnable —
#                           but NOT run here. See README.md "What runs
#                           where": a Maven/JVM boot per CI matrix leg is
#                           too heavy for this script's bounded, fast path.
#   3. E2E API tests      — the vendored/adapted Newman collection
#                           (collections/shipping.postman_collection.json),
#                           run against BOTH live stacks. 0 failures
#                           required.
#   4. Load test          — the SAME collection's "Load" folder, run N=30
#                           iterations against one stack. Bounded and
#                           deterministic: asserts success/schema
#                           conformance on every iteration, never an
#                           absolute latency number.
#
# Vendored from cloud-native-design-patterns/examples/28-newman and adapted
# to this repo's booking create/read surface + shared-schema contract.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch24-testing"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

QUARKUS_BASE="http://localhost:8103"
PYTHON_BASE="http://localhost:8023"

LOAD_ITERATIONS=30

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

fail() {
  echo "verify.sh: FAIL — $*" >&2
  return 1
}

NEWMAN_CMD=(npx --yes newman@6)

# ---------------------------------------------------------------------------
# Step 1a: prove the contract-validation gate has teeth before trusting it.
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

wait_for_http "$QUARKUS_BASE/q/health" 90
wait_for_http "$PYTHON_BASE/health" 60

# ---------------------------------------------------------------------------
# Step 3: per-stack live contract checks (item 1 of the pyramid) — POST
# create -> 201 + Location + Booking schema, GET -> 200 + Booking schema, a
# negative case -> 404 + Problem schema.
# ---------------------------------------------------------------------------

run_contract_checks() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: live contract checks — '$stack' at $base ==="

  local create_payload
  create_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
  local status
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  assert_header Location "$headers_file" "$stack POST /bookings"
  validate_body Booking "$body_file"

  local booking_id
  booking_id="$(jq -r '.id' "$body_file")"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack GET /bookings/{id}"
  validate_body Booking "$body_file"

  local nonexistent="bkg_00000000000000000000000000"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$nonexistent")"
  assert_status 404 "$status" "$stack GET /bookings/{nonexistent}"
  validate_body Problem "$body_file"

  echo "verify.sh: ok — $stack live contract checks passed (POST/GET/404, all schema-valid)"
}

run_contract_checks "quarkus" "$QUARKUS_BASE"
run_contract_checks "python" "$PYTHON_BASE"

# ---------------------------------------------------------------------------
# Step 4: Newman functional run (item 3 of the pyramid) against BOTH stacks.
# 0 failures required on each.
# ---------------------------------------------------------------------------

run_newman_functional() {
  local stack="$1" base="$2"
  local output_file="$TMP_DIR/${stack}-newman-functional.txt"

  echo
  echo "=== Step 4: Newman functional run — '$stack' at $base ==="

  if "${NEWMAN_CMD[@]}" run "$SCRIPT_DIR/collections/shipping.postman_collection.json" \
      --folder Functional \
      --env-var "baseUrl=$base" \
      --reporters cli \
      --timeout-request 5000 \
      --color off | tee "$output_file"; then
    echo "verify.sh: ok — $stack Newman functional run passed (all assertions green)"
  else
    echo "verify.sh: FAIL — $stack Newman functional run failed" >&2
    tail -30 "$output_file" >&2
    return 1
  fi

  local assertion_line failed_assertions
  assertion_line="$(grep 'assertions' "$output_file" | head -1)"
  failed_assertions="$(echo "$assertion_line" | awk -F'│' '{gsub(/[^0-9]/,"",$4); print $4}')"
  if [[ "$failed_assertions" != "0" ]]; then
    fail "$stack Newman functional run: expected 0 failed assertions, parsed '$failed_assertions'"
  fi
}

run_newman_functional "quarkus" "$QUARKUS_BASE"
run_newman_functional "python" "$PYTHON_BASE"

# ---------------------------------------------------------------------------
# Step 5: bounded load run (item 4 of the pyramid) — tiny, deterministic.
# N=30 repeats of the "Load" folder's single create request against ONE
# stack (Quarkus). Asserts SUCCESS/SCHEMA CONFORMANCE on every iteration,
# not an absolute latency number, so this stays fast and non-flaky in CI.
# ---------------------------------------------------------------------------

echo
echo "=== Step 5: bounded Newman load run (n=$LOAD_ITERATIONS, quarkus) ==="

load_output_file="$TMP_DIR/quarkus-newman-load.txt"
if "${NEWMAN_CMD[@]}" run "$SCRIPT_DIR/collections/shipping.postman_collection.json" \
    --folder Load \
    -n "$LOAD_ITERATIONS" \
    --env-var "baseUrl=$QUARKUS_BASE" \
    --reporters cli \
    --timeout-request 5000 \
    --color off | tee "$load_output_file"; then
  echo "verify.sh: ok — load run completed $LOAD_ITERATIONS/$LOAD_ITERATIONS iterations"
else
  echo "verify.sh: FAIL — bounded load run failed" >&2
  tail -30 "$load_output_file" >&2
  exit 1
fi

load_assertion_line="$(grep 'assertions' "$load_output_file" | head -1)"
load_failed_assertions="$(echo "$load_assertion_line" | awk -F'│' '{gsub(/[^0-9]/,"",$4); print $4}')"
if [[ "$load_failed_assertions" != "0" ]]; then
  fail "load run: expected 0 failed assertions across $LOAD_ITERATIONS iterations, parsed '$load_failed_assertions'"
fi

echo
echo "PASS — Ch24 testing anchor: contract checks green on both stacks," \
     "Newman functional 0 failures on both stacks, bounded load run" \
     "($LOAD_ITERATIONS iterations) completed with 0 failures."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
