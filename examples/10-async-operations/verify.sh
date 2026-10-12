#!/usr/bin/env bash
# examples/10-async-operations/verify.sh
#
# Ch10 async/long-running-operations example — the reference both-stack
# implementation of the 202 Accepted -> poll -> 303 See Other protocol:
# POST /bookings/{id}/confirmation starts an async confirmation, GET
# /operations/{id} polls it (200 while running, 303 once SUCCEEDED), DELETE
# /operations/{id} cancels a still-running one. Every response body from
# BOTH the Quarkus and the FastAPI stack is schema-validated against the
# shared contract (contracts/schemas/shipping.schema.json), not just
# checked for an HTTP status code. See README.md for the lifecycle and a
# documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch10-async"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

# Syntactically valid but never-issued ids (26 zeros — the Crockford
# alphabet includes '0', so this is a legal ULID shape).
NONEXISTENT_BOOKING_ID="bkg_$(printf '0%.0s' $(seq 1 26))"
NONEXISTENT_OPERATION_ID="op_$(printf '0%.0s' $(seq 1 26))"

# How long to poll GET /operations/{id} before giving up on ever seeing a
# 303. The worker completes after OperationStore.CONFIRMATION_DELAY_MS /
# operations.CONFIRMATION_DELAY_SECONDS (~2s); 10s gives generous headroom
# without letting a genuinely broken stack hang CI.
POLL_TIMEOUT_SECONDS=10
POLL_INTERVAL_SECONDS=1

# ---------------------------------------------------------------------------
# Header helpers (lib.sh's assert_header only checks presence; the test
# sequence below also needs the VALUE to chase the Location it got back).
# ---------------------------------------------------------------------------

extract_header() {
  local name="$1" file="$2"
  grep -i "^${name}:" "$file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n'
}

# Resolve a Location header value against a base URL. Accepts either a
# relative path ("/operations/xyz") or an absolute URL, so this test
# doesn't care which shape a given stack's HTTP runtime happens to emit.
resolve_location() {
  local base="$1" location="$2"
  case "$location" in
    http://*|https://*) echo "$location" ;;
    *) echo "${base}${location}" ;;
  esac
}

fail() {
  echo "lib.sh: FAIL — $*" >&2
  return 1
}

create_pending_booking() {
  local base="$1" body_file="$2"
  local payload
  payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
  curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$payload" "$base/bookings"
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

wait_for_http "http://localhost:8090/q/health" 90
wait_for_http "http://localhost:8010/health" 60

# ---------------------------------------------------------------------------
# Step 3: drive the 202 -> poll -> 303 confirmation lifecycle, AND the
# cancel path, against EACH stack, schema-validating every response body.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- POST /bookings -> 201 (a fresh PENDING booking to confirm) ----------
  local status booking_id
  status="$(create_pending_booking "$base" "$body_file")"
  assert_status 201 "$status" "$stack POST /bookings"
  validate_body Booking "$body_file"
  booking_id="$(jq -r '.id' "$body_file")"

  # -- POST /bookings/{id}/confirmation -> 202, Location, Operation --------
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST "$base/bookings/$booking_id/confirmation")"
  assert_status 202 "$status" "$stack POST /bookings/{id}/confirmation"
  assert_header Location "$headers_file" "$stack POST /bookings/{id}/confirmation"
  validate_body Operation "$body_file"

  local op_location op_id
  op_location="$(extract_header Location "$headers_file")"
  op_id="$(jq -r '.id' "$body_file")"

  # -- Booking must NOT be CONFIRMED yet (the operation is RUNNING) --------
  local booking_status
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack GET /bookings/{id} (pre-completion)"
  validate_body Booking "$body_file"
  booking_status="$(jq -r '.status' "$body_file")"
  [[ "$booking_status" == "PENDING" ]] || fail "$stack booking $booking_id was CONFIRMED before the operation completed"

  # -- POST confirmation again on an already-pending-confirmation booking:
  #    still PENDING, so this is still a VALID confirm request, not a 409
  #    in itself — but confirming an already-CONFIRMED booking below IS a
  #    409 (tested after the lifecycle completes).

  # -- Immediately GET the operation -> 200, Operation, RUNNING/PENDING ---
  status="$(curl -sS --max-redirs 0 -o "$body_file" -w '%{http_code}' \
    "$(resolve_location "$base" "$op_location")")"
  assert_status 200 "$status" "$stack GET /operations/{id} (immediately after 202)"
  validate_body Operation "$body_file"
  local op_status
  op_status="$(jq -r '.status' "$body_file")"
  [[ "$op_status" == "RUNNING" || "$op_status" == "PENDING" ]] \
    || fail "$stack operation $op_id: expected RUNNING or PENDING immediately after 202, got $op_status"
  echo "lib.sh: ok — $stack operation $op_id is $op_status immediately after 202"

  # -- Poll GET /operations/{id} until it returns 303 ----------------------
  local waited=0 op_final_status=""
  while (( waited < POLL_TIMEOUT_SECONDS )); do
    status="$(curl -sS --max-redirs 0 -D "$headers_file" -o "$body_file" -w '%{http_code}' \
      "$(resolve_location "$base" "$op_location")")"
    if [[ "$status" == "303" ]]; then
      op_final_status="303"
      break
    fi
    assert_status 200 "$status" "$stack GET /operations/{id} (polling)"
    sleep "$POLL_INTERVAL_SECONDS"
    waited=$(( waited + POLL_INTERVAL_SECONDS ))
  done
  [[ "$op_final_status" == "303" ]] \
    || fail "$stack operation $op_id never returned 303 within ${POLL_TIMEOUT_SECONDS}s"
  echo "lib.sh: ok — $stack operation $op_id reached 303 within ${waited}s"

  # -- 303's Location must point at the confirmed booking ------------------
  assert_header Location "$headers_file" "$stack GET /operations/{id} (303)"
  local booking_location
  booking_location="$(extract_header Location "$headers_file")"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$(resolve_location "$base" "$booking_location")")"
  assert_status 200 "$status" "$stack GET 303 Location (booking)"
  validate_body Booking "$body_file"
  booking_status="$(jq -r '.status' "$body_file")"
  [[ "$booking_status" == "CONFIRMED" ]] \
    || fail "$stack booking $booking_id: expected CONFIRMED after the 303, got $booking_status"
  echo "lib.sh: ok — $stack booking $booking_id is CONFIRMED after following the 303"

  # -- GET /operations/{id} again -> still 303 (terminal, not re-run) ------
  status="$(curl -sS --max-redirs 0 -o /dev/null -w '%{http_code}' "$(resolve_location "$base" "$op_location")")"
  assert_status 303 "$status" "$stack GET /operations/{id} (post-completion, repeat)"

  # -- POST confirmation on the now-CONFIRMED booking -> 409, Problem ------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST "$base/bookings/$booking_id/confirmation")"
  assert_status 409 "$status" "$stack POST confirmation on non-PENDING booking"
  validate_body Problem "$body_file"

  # -- POST confirmation on an unknown booking -> 404, Problem -------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST "$base/bookings/$NONEXISTENT_BOOKING_ID/confirmation")"
  assert_status 404 "$status" "$stack POST confirmation on unknown booking"
  validate_body Problem "$body_file"

  # -- GET an unknown operation -> 404, Problem -----------------------------
  status="$(curl -sS --max-redirs 0 -o "$body_file" -w '%{http_code}' \
    "$base/operations/$NONEXISTENT_OPERATION_ID")"
  assert_status 404 "$status" "$stack GET unknown operation"
  validate_body Problem "$body_file"

  # -- DELETE an unknown operation -> 404, Problem --------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X DELETE "$base/operations/$NONEXISTENT_OPERATION_ID")"
  assert_status 404 "$status" "$stack DELETE unknown operation"
  validate_body Problem "$body_file"

  # -------------------------------------------------------------------------
  # Cancel path: start a SECOND confirmation and cancel it before the
  # worker completes. The booking must stay PENDING.
  # -------------------------------------------------------------------------

  local booking2_id op2_location op2_id
  status="$(create_pending_booking "$base" "$body_file")"
  assert_status 201 "$status" "$stack POST /bookings (cancel path)"
  validate_body Booking "$body_file"
  booking2_id="$(jq -r '.id' "$body_file")"

  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST "$base/bookings/$booking2_id/confirmation")"
  assert_status 202 "$status" "$stack POST confirmation (cancel path)"
  assert_header Location "$headers_file" "$stack POST confirmation (cancel path)"
  validate_body Operation "$body_file"
  op2_location="$(extract_header Location "$headers_file")"
  op2_id="$(jq -r '.id' "$body_file")"

  # DELETE immediately — well inside the ~2s completion delay.
  status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -X DELETE "$(resolve_location "$base" "$op2_location")")"
  assert_status 204 "$status" "$stack DELETE /operations/{id} (cancel)"

  # The cancelled operation must report FAILED, not SUCCEEDED/303.
  status="$(curl -sS --max-redirs 0 -o "$body_file" -w '%{http_code}' \
    "$(resolve_location "$base" "$op2_location")")"
  assert_status 200 "$status" "$stack GET cancelled operation"
  validate_body Operation "$body_file"
  local op2_status
  op2_status="$(jq -r '.status' "$body_file")"
  [[ "$op2_status" == "FAILED" ]] || fail "$stack cancelled operation $op2_id: expected FAILED, got $op2_status"

  # Even after waiting past the completion delay, the booking must stay
  # PENDING — the worker's cancelled-check must have won the race.
  sleep "$POLL_INTERVAL_SECONDS"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking2_id")"
  assert_status 200 "$status" "$stack GET cancelled booking"
  validate_body Booking "$body_file"
  local booking2_status
  booking2_status="$(jq -r '.status' "$body_file")"
  [[ "$booking2_status" == "PENDING" ]] \
    || fail "$stack booking $booking2_id: expected PENDING after cancel, got $booking2_status"
  echo "lib.sh: ok — $stack cancelled operation $op2_id left booking $booking2_id PENDING"

  # -- DELETE the (already-terminal) cancelled operation again -> still 204
  status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -X DELETE "$(resolve_location "$base" "$op2_location")")"
  assert_status 204 "$status" "$stack DELETE /operations/{id} (repeat cancel, idempotent)"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8090"
run_stack_tests "python" "http://localhost:8010"

echo
echo "PASS — Ch10 async/long-running-operations example: Quarkus and FastAPI" \
     "both produce schema-conforming Operation/Booking/Problem bodies for" \
     "the full 202 -> poll -> 303 confirmation lifecycle, including a" \
     "cancel that leaves the booking PENDING."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
