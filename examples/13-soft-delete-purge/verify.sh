#!/usr/bin/env bash
# examples/13-soft-delete-purge/verify.sh
#
# Ch13 soft-delete & GDPR purge — extends the Ch4 contract-first anchor's
# Booking + Cargo resource model (contracts/openapi/shipping-api.yaml,
# contracts/schemas/shipping.schema.json) with a soft-delete + audit trail +
# GDPR hard-delete purge. Every Booking response body from BOTH the Quarkus
# and the FastAPI stack is schema-validated against the shared contract.
# See README.md for the soft-delete-vs-purge model and a documented drift
# probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch13-purge"
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

wait_for_http "http://localhost:8093/q/health" 90
wait_for_http "http://localhost:8013/health" 60

# ---------------------------------------------------------------------------
# Step 3: drive create -> soft-delete -> hide -> audit-view -> purge ->
# erase against EACH stack, schema-validating every Booking response body.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- POST /bookings -> 201, Booking --------------------------------------
  local create_payload
  create_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
  local status
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  validate_body Booking "$body_file"

  local booking_id
  booking_id="$(jq -r '.id' "$body_file")"

  # -- DELETE /bookings/{id} -> 204 (soft delete) --------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X DELETE "$base/bookings/$booking_id?reason=gdpr-test-cancellation")"
  assert_status 204 "$status" "$stack DELETE /bookings/{id} (soft delete)"

  # -- GET /bookings -> cancelled booking ABSENT from the default list -----
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings")"
  assert_status 200 "$status" "$stack GET /bookings (post-soft-delete)"
  validate_body BookingCollection "$body_file"
  if jq -e --arg id "$booking_id" '.items[] | select(.id == $id)' "$body_file" >/dev/null; then
    fail "$stack soft-deleted booking $booking_id is still visible in the default GET /bookings list"
  fi
  echo "lib.sh: ok — $stack soft-deleted booking hidden from default collection"

  # -- GET /bookings/{id} -> 404 (hidden by default) -----------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_id")"
  assert_status 404 "$status" "$stack GET /bookings/{id} (default, post-soft-delete)"
  validate_body Problem "$body_file"
  echo "lib.sh: ok — $stack soft-deleted booking 404s on the default single-resource GET"

  # -- GET /bookings/{id}?includeDeleted=true -> 200, Booking + audit ------
  local headers_file="$TMP_DIR/${stack}-audit-headers.txt"
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    "$base/bookings/$booking_id?includeDeleted=true")"
  assert_status 200 "$status" "$stack GET /bookings/{id}?includeDeleted=true (audit view)"
  validate_body Booking "$body_file"
  local audit_status
  audit_status="$(jq -r '.status' "$body_file")"
  [[ "$audit_status" == "CANCELLED" ]] || fail "$stack audit view: expected status CANCELLED, got $audit_status"
  assert_header X-Audit-Deleted-At "$headers_file" "$stack audit view deletion timestamp"
  assert_header X-Audit-Reason "$headers_file" "$stack audit view deletion reason"
  local audit_reason
  audit_reason="$(grep -i '^X-Audit-Reason:' "$headers_file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n')"
  [[ "$audit_reason" == "gdpr-test-cancellation" ]] || fail "$stack audit reason: expected gdpr-test-cancellation, got $audit_reason"
  echo "lib.sh: ok — $stack audit view shows CANCELLED booking + X-Audit-* trail (record still exists in the store)"

  # -- DELETE /bookings/{id}/purge -> 204 (GDPR hard delete) ---------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X DELETE "$base/bookings/$booking_id/purge")"
  assert_status 204 "$status" "$stack DELETE /bookings/{id}/purge"

  # -- audit view now -> 404 (fully erased, audit trail gone too) ----------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    "$base/bookings/$booking_id?includeDeleted=true")"
  assert_status 404 "$status" "$stack GET /bookings/{id}?includeDeleted=true (post-purge)"
  validate_body Problem "$body_file"
  echo "lib.sh: ok — $stack purge erased the booking AND its audit trail"

  # -- purge again -> 404 (nothing left to erase) --------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X DELETE "$base/bookings/$booking_id/purge")"
  assert_status 404 "$status" "$stack DELETE /bookings/{id}/purge (2nd, already purged)"
  validate_body Problem "$body_file"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8093"
run_stack_tests "python" "http://localhost:8013"

echo
echo "PASS — Ch13 soft-delete & GDPR purge: Quarkus and FastAPI both hide a" \
     "cancelled booking from default reads while keeping it (and its audit" \
     "trail) addressable via includeDeleted=true, and both fully erase" \
     "booking + audit trail on purge."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
