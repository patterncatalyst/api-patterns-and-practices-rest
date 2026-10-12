#!/usr/bin/env bash
# examples/06-content-negotiation/verify.sh
#
# Ch6 content negotiation & status codes — extends the Ch4 contract-first
# anchor's Booking resource with explicit Accept/Content-Type negotiation
# (406 Not Acceptable / 415 Unsupported Media Type) and a full status-code
# discipline pass across the booking operations: 200/201/204/400/404/409.
# See README.md for the status-code table and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch06-neg"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

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

wait_for_http "http://localhost:8086/q/health" 90
wait_for_http "http://localhost:8006/health" 60

# ---------------------------------------------------------------------------
# Step 3: drive the content-negotiation + status-code assertions against
# EACH stack, schema-validating every response body.
# ---------------------------------------------------------------------------

CREATE_PAYLOAD='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

run_stack_tests() {
  local stack="$1" base="$2"
  local body="$TMP_DIR/${stack}-body.json"
  local status

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- (1) POST valid booking, Content-Type: application/json -> 201 + Location, Booking body --
  status="$(curl -sS -o "$body" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -H 'Accept: application/json' \
    -d "$CREATE_PAYLOAD" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings (valid, application/json)"
  validate_body Booking "$body"
  local id
  id="$(jq -r '.id' "$body")"
  echo "lib.sh: ok — $stack POST /bookings minted $id"

  local headers_file="$TMP_DIR/${stack}-headers.txt"
  curl -sS -D "$headers_file" -o /dev/null \
    -X POST -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD" "$base/bookings" >/dev/null
  assert_header Location "$headers_file" "$stack POST /bookings Location header"

  # -- (2) POST with a Content-Type the endpoint doesn't accept -> 415, Problem body --
  status="$(curl -sS -o "$body" -w '%{http_code}' \
    -X POST -H 'Content-Type: text/plain' -d "$CREATE_PAYLOAD" "$base/bookings")"
  assert_status 415 "$status" "$stack POST /bookings (Content-Type: text/plain)"
  validate_body Problem "$body"
  echo "lib.sh: ok — $stack POST /bookings with an unsupported Content-Type -> 415 Problem"

  # -- (3) GET a booking with an Accept the endpoint can't satisfy -> 406, Problem body --
  status="$(curl -sS -o "$body" -w '%{http_code}' \
    -H 'Accept: application/xml' "$base/bookings/$id")"
  assert_status 406 "$status" "$stack GET /bookings/{id} (Accept: application/xml)"
  validate_body Problem "$body"
  echo "lib.sh: ok — $stack GET /bookings/{id} with an unsatisfiable Accept -> 406 Problem"

  # -- (4) GET the same booking with Accept: application/json -> 200, Booking body --
  status="$(curl -sS -o "$body" -w '%{http_code}' \
    -H 'Accept: application/json' "$base/bookings/$id")"
  assert_status 200 "$status" "$stack GET /bookings/{id} (Accept: application/json)"
  validate_body Booking "$body"
  echo "lib.sh: ok — $stack GET /bookings/{id} with Accept: application/json -> 200 Booking"

  # -- (5) GET a missing booking -> 404, Problem body --
  status="$(curl -sS -o "$body" -w '%{http_code}' "$base/bookings/bkg_00000000000000000000000000")"
  assert_status 404 "$status" "$stack GET /bookings/{id} (missing)"
  validate_body Problem "$body"
  echo "lib.sh: ok — $stack GET /bookings/{id} (missing) -> 404 Problem"

  # -- (6) 400: malformed booking request (missing required fields) --
  status="$(curl -sS -o "$body" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d '{}' "$base/bookings")"
  assert_status 400 "$status" "$stack POST /bookings (malformed body)"
  validate_body Problem "$body"
  echo "lib.sh: ok — $stack POST /bookings with a malformed body -> 400 Problem"

  # -- (7) 409: confirming a booking is only valid from PENDING — confirm
  #        once (200), confirm again (409 — already CONFIRMED) ------------
  status="$(curl -sS -o "$body" -w '%{http_code}' -X POST "$base/bookings/$id/confirm")"
  assert_status 200 "$status" "$stack POST /bookings/{id}/confirm (1st, from PENDING)"
  validate_body Booking "$body"

  status="$(curl -sS -o "$body" -w '%{http_code}' -X POST "$base/bookings/$id/confirm")"
  assert_status 409 "$status" "$stack POST /bookings/{id}/confirm (2nd, already CONFIRMED)"
  validate_body Problem "$body"
  echo "lib.sh: ok — $stack confirm is 200 from PENDING, 409 on an already-confirmed booking"

  # -- (8) 404 on confirming a booking that doesn't exist -------------------
  status="$(curl -sS -o "$body" -w '%{http_code}' -X POST "$base/bookings/bkg_00000000000000000000000000/confirm")"
  assert_status 404 "$status" "$stack POST /bookings/{id}/confirm (missing)"
  validate_body Problem "$body"

  # -- (9) 204 on DELETE ------------------------------------------------------
  status="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "$base/bookings/$id")"
  assert_status 204 "$status" "$stack DELETE /bookings/{id}"
  echo "lib.sh: ok — $stack DELETE /bookings/{id} -> 204"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8086"
run_stack_tests "python" "http://localhost:8006"

echo
echo "PASS — Ch6 content negotiation & status codes: Quarkus and FastAPI both" \
     "honor Accept (406 when unsatisfiable) and Content-Type (415 when" \
     "unsupported), and agree on the status-code discipline across the" \
     "booking operations: 200/201/204/400/404/409, errors always" \
     "application/problem+json."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
