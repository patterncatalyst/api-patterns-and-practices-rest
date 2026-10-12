#!/usr/bin/env bash
# examples/12-hateoas/verify.sh
#
# Ch12 HATEOAS — the response IS the state machine. Every Booking response
# carries exactly the `_links` relations valid from its CURRENT `status`,
# per the booking lifecycle finite-state machine
# (PENDING -> CONFIRMED -> IN_TRANSIT -> DELIVERED, CANCELLED):
#
#   PENDING    -> self, confirm, cancel
#   CONFIRMED  -> self, cancel
#   IN_TRANSIT -> self
#   DELIVERED  -> self
#   CANCELLED  -> self
#
# This drives a booking through every state (via POST .../confirmation,
# .../transit, .../delivery, and DELETE for CANCELLED) and asserts the
# EXACT `_links` key set at each stop, for BOTH stacks. See README.md for
# the state -> links table and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch12-hateoas"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

NONEXISTENT_ID="bkg_$(printf '0%.0s' $(seq 1 26))"

fail() {
  echo "lib.sh: FAIL — $*" >&2
  return 1
}

# links_keys <body-file> -> sorted, comma-joined relation names, e.g. "cancel,confirm,self"
links_keys() {
  jq -r '._links | keys | sort | join(",")' "$1"
}

# assert_links <body-file> <expected-comma-joined-keys> <context>
assert_links() {
  local body_file="$1" expected="$2" context="$3"
  local actual
  actual="$(links_keys "$body_file")"
  if [[ "$actual" != "$expected" ]]; then
    fail "$context: expected _links keys [$expected], got [$actual]"
  fi
  echo "lib.sh: ok — $context: _links keys = [$actual]"
}

CREATE_PAYLOAD='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

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

wait_for_http "http://localhost:8092/q/health" 90
wait_for_http "http://localhost:8012/health" 60

# ---------------------------------------------------------------------------
# Step 3: drive ONE booking through PENDING -> CONFIRMED -> IN_TRANSIT ->
# DELIVERED and a SECOND booking through PENDING -> CANCELLED, asserting the
# exact `_links` key set at every stop, against EACH stack.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- Booking A: PENDING -> CONFIRMED -> IN_TRANSIT -> DELIVERED ---------

  local status booking_id
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings (A)"
  validate_body Booking "$body_file"
  booking_id="$(jq -r '.id' "$body_file")"
  local link_status
  link_status="$(jq -r '.status' "$body_file")"
  [[ "$link_status" == "PENDING" ]] || fail "$stack new booking status: expected PENDING, got $link_status"
  assert_links "$body_file" "cancel,confirm,self" "$stack PENDING (A, from POST)"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack GET /bookings/{id} (A, PENDING)"
  validate_body Booking "$body_file"
  assert_links "$body_file" "cancel,confirm,self" "$stack PENDING (A, from GET)"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X POST "$base/bookings/$booking_id/confirmation")"
  assert_status 200 "$status" "$stack POST /bookings/{id}/confirmation (A)"
  validate_body Booking "$body_file"
  link_status="$(jq -r '.status' "$body_file")"
  [[ "$link_status" == "CONFIRMED" ]] || fail "$stack confirmation did not confirm (got status=$link_status)"
  assert_links "$body_file" "cancel,self" "$stack CONFIRMED (A)"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X POST "$base/bookings/$booking_id/transit")"
  assert_status 200 "$status" "$stack POST /bookings/{id}/transit (A)"
  validate_body Booking "$body_file"
  link_status="$(jq -r '.status' "$body_file")"
  [[ "$link_status" == "IN_TRANSIT" ]] || fail "$stack transit did not move to IN_TRANSIT (got status=$link_status)"
  assert_links "$body_file" "self" "$stack IN_TRANSIT (A)"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X POST "$base/bookings/$booking_id/delivery")"
  assert_status 200 "$status" "$stack POST /bookings/{id}/delivery (A)"
  validate_body Booking "$body_file"
  link_status="$(jq -r '.status' "$body_file")"
  [[ "$link_status" == "DELIVERED" ]] || fail "$stack delivery did not move to DELIVERED (got status=$link_status)"
  assert_links "$body_file" "self" "$stack DELIVERED (A)"

  # A DELIVERED booking cannot be confirmed again (409, not re-confirmed).
  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X POST "$base/bookings/$booking_id/confirmation")"
  assert_status 409 "$status" "$stack POST .../confirmation on a DELIVERED booking (A)"
  validate_body Problem "$body_file"

  # -- Booking B: PENDING -> CANCELLED (via DELETE) -----------------------

  local booking_id_b
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings (B)"
  validate_body Booking "$body_file"
  booking_id_b="$(jq -r '.id' "$body_file")"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X DELETE "$base/bookings/$booking_id_b")"
  assert_status 204 "$status" "$stack DELETE /bookings/{id} (B)"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_id_b")"
  assert_status 200 "$status" "$stack GET /bookings/{id} (B, CANCELLED)"
  validate_body Booking "$body_file"
  link_status="$(jq -r '.status' "$body_file")"
  [[ "$link_status" == "CANCELLED" ]] || fail "$stack DELETE did not cancel (got status=$link_status)"
  assert_links "$body_file" "self" "$stack CANCELLED (B)"

  # -- 404 still comes back as Problem, with no _links assertion needed ---
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$NONEXISTENT_ID")"
  assert_status 404 "$status" "$stack GET /bookings/{nonexistent}"
  validate_body Problem "$body_file"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8092"
run_stack_tests "python" "http://localhost:8012"

echo
echo "PASS — Ch12 HATEOAS: Quarkus and FastAPI both expose exactly the" \
     "_links relations valid from the booking's current state" \
     "(PENDING/CONFIRMED/IN_TRANSIT/DELIVERED/CANCELLED), for the full" \
     "lifecycle, on both stacks."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
