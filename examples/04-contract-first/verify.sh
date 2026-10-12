#!/usr/bin/env bash
# examples/04-contract-first/verify.sh
#
# Ch4 contract-first anchor — the reference both-stack implementation of
# the shipping/cargo Booking + Cargo resource model
# (contracts/openapi/shipping-api.yaml,
# contracts/schemas/shipping.schema.json). This is the load-bearing
# correctness step: every response body from BOTH the Quarkus and the
# FastAPI stack is schema-validated against the shared contract, not just
# checked for an HTTP status code. See README.md for the quote formula and
# a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch04-contract"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

# A syntactically valid but never-issued booking id (26 zeros — the
# Crockford alphabet includes '0', so this is a legal ULID shape).
NONEXISTENT_ID="bkg_$(printf '0%.0s' $(seq 1 26))"

# ---------------------------------------------------------------------------
# Header helpers (lib.sh's assert_header only checks presence; the test
# sequence below also needs the VALUE to chase the Location it got back).
# ---------------------------------------------------------------------------

extract_header() {
  local name="$1" file="$2"
  grep -i "^${name}:" "$file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n'
}

# Resolve a Location header value against a base URL. Accepts either a
# relative path ("/bookings/xyz") or an absolute URL, so this test doesn't
# care which shape a given stack's HTTP runtime happens to emit.
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

wait_for_http "http://localhost:8080/q/health" 90
wait_for_http "http://localhost:8000/health" 60

# ---------------------------------------------------------------------------
# Step 3: drive the identical create -> read -> list -> cargo -> replace ->
# patch -> delete sequence against EACH stack, schema-validating every
# response body.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- POST /bookings -> 201, Location, Booking ---------------------------
  local create_payload
  create_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
  local status
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  assert_header Location "$headers_file" "$stack POST /bookings"
  validate_body Booking "$body_file"

  local location booking_id quote_amount
  location="$(extract_header Location "$headers_file")"
  booking_id="$(jq -r '.id' "$body_file")"
  quote_amount="$(jq -r '.quote.amount' "$body_file")"
  [[ "$quote_amount" == "3001.25" ]] || fail "$stack quote.amount: expected 3001.25 (1200.5kg * 2.50), got $quote_amount"
  echo "lib.sh: ok — $stack quote formula produced $quote_amount"

  # -- GET the Location -> 200, Booking ------------------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$(resolve_location "$base" "$location")")"
  assert_status 200 "$status" "$stack GET Location"
  validate_body Booking "$body_file"

  # -- GET /bookings -> 200, BookingCollection -----------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings")"
  assert_status 200 "$status" "$stack GET /bookings"
  validate_body BookingCollection "$body_file"

  # -- POST /bookings/{id}/cargo -> 201, Location, Cargo -------------------
  local cargo_payload='{"description":"Spare parts","type":"GENERAL","dimensions":{"weightKg":500,"volumeM3":1.0},"hazardous":false}'
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$cargo_payload" "$base/bookings/$booking_id/cargo")"
  assert_status 201 "$status" "$stack POST /bookings/{id}/cargo"
  assert_header Location "$headers_file" "$stack POST /bookings/{id}/cargo"
  validate_body Cargo "$body_file"

  # -- PUT /bookings/{id} -> 200, Booking (full, idempotent replace) ------
  local put_payload
  put_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"SGSIN","name":"Singapore","country":"SG"},"cargo":[{"description":"Replacement manifest","type":"GENERAL","dimensions":{"weightKg":800,"volumeM3":2.0},"hazardous":false}]}'
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PUT -H 'Content-Type: application/json' -d "$put_payload" "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack PUT /bookings/{id}"
  validate_body Booking "$body_file"
  local put_destination
  put_destination="$(jq -r '.destination.unLocode' "$body_file")"
  [[ "$put_destination" == "SGSIN" ]] || fail "$stack PUT did not replace destination (got $put_destination)"

  # -- PATCH /bookings/{id} with application/merge-patch+json -> 200 ------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PATCH -H 'Content-Type: application/merge-patch+json' -d '{"requestedPickup":"2026-03-01"}' \
    "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack PATCH /bookings/{id} (merge-patch)"
  validate_body Booking "$body_file"
  local patched_pickup
  patched_pickup="$(jq -r '.requestedPickup' "$body_file")"
  [[ "$patched_pickup" == "2026-03-01" ]] || fail "$stack merge-patch did not apply (got requestedPickup=$patched_pickup)"

  # -- PATCH with an unsupported content-type -> 415, Problem --------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PATCH -H 'Content-Type: application/json' -d '{"requestedPickup":"2026-04-01"}' \
    "$base/bookings/$booking_id")"
  assert_status 415 "$status" "$stack PATCH /bookings/{id} (unsupported content-type)"
  validate_body Problem "$body_file"

  # -- GET /bookings/{nonexistent} -> 404, Problem -------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$NONEXISTENT_ID")"
  assert_status 404 "$status" "$stack GET /bookings/{nonexistent}"
  validate_body Problem "$body_file"

  # -- DELETE /bookings/{id} -> 204 (soft-delete) --------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X DELETE "$base/bookings/$booking_id")"
  assert_status 204 "$status" "$stack DELETE /bookings/{id}"

  # -- GET /bookings -> cancelled booking hidden from default list ---------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings")"
  assert_status 200 "$status" "$stack GET /bookings (post-delete)"
  validate_body BookingCollection "$body_file"
  if jq -e --arg id "$booking_id" '.items[] | select(.id == $id)' "$body_file" >/dev/null; then
    fail "$stack cancelled booking $booking_id is still visible in the default GET /bookings list"
  fi
  echo "lib.sh: ok — $stack cancelled booking hidden from default collection"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8080"
run_stack_tests "python" "http://localhost:8000"

echo
echo "PASS — Ch4 contract-first anchor: Quarkus and FastAPI both produce" \
     "schema-conforming Booking/Cargo/BookingCollection/Problem bodies for" \
     "the full create/read/list/cargo/replace/patch/delete sequence."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
