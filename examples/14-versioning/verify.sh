#!/usr/bin/env bash
# examples/14-versioning/verify.sh
#
# Ch14 versioning — TWO versioning strategies serving the SAME stored
# booking: URI versioning (/v1/bookings/{id}, /v2/bookings/{id}) and
# media-type/content-negotiation versioning (/bookings/{id} +
# Accept: application/vnd.shipping.v{1,2}+json). v2 is the current Booking
# shape (quote + cargo[], contracts/schemas/shipping.schema.json); v1 is
# the frozen BookingV1 shape (price + cargoDescription,
# contracts/openapi/shipping-api-v1.yaml). v1 is NOT in the shared schema's
# $defs, so this script asserts its fields by hand with jq instead of
# validate_body. See README.md for the strategy comparison, the v1<->v2
# shape diff, and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch14-version"
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

# extract_header <name> <headers-file> -> value, case-insensitive, no CRLF.
extract_header() {
  local name="$1" file="$2"
  grep -i "^${name}:" "$file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n'
}

# assert_contains <haystack> <needle> <context>
assert_contains() {
  local haystack="$1" needle="$2" context="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    fail "$context: expected '$haystack' to contain '$needle'"
  fi
  echo "lib.sh: ok — $context: '$haystack' contains '$needle'" >&2
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

wait_for_http "http://localhost:8094/q/health" 90
wait_for_http "http://localhost:8014/health" 60

# ---------------------------------------------------------------------------
# Step 3: create ONE booking (v2 shape) against each stack, then read it
# back through BOTH versioning strategies and BOTH versions, asserting the
# exact shape (and, for media-type negotiation, Content-Type/Vary) each
# time.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- POST /bookings (v2 shape) -> 201 ------------------------------------
  local status booking_id
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  validate_body Booking "$body_file"
  booking_id="$(jq -r '.id' "$body_file")"

  # -- URI versioning: GET /v2/bookings/{id} -> Booking (quote + cargo[]) -
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/v2/bookings/$booking_id")"
  assert_status 200 "$status" "$stack GET /v2/bookings/{id}"
  validate_body Booking "$body_file"
  jq -e '(.quote != null) and (.cargo | type == "array")' "$body_file" >/dev/null \
    || fail "$stack GET /v2/bookings/{id}: expected quote + cargo[], got $(cat "$body_file")"
  echo "lib.sh: ok — $stack GET /v2/bookings/{id}: quote + cargo[] present" >&2

  # -- URI versioning: GET /v1/bookings/{id} -> BookingV1 (price +
  #    cargoDescription, NO quote/cargo). v1 isn't in the shared schema's
  #    $defs, so assert its fields by hand instead of validate_body. -------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/v1/bookings/$booking_id")"
  assert_status 200 "$status" "$stack GET /v1/bookings/{id}"
  jq -e '
      (has("price")) and (has("cargoDescription"))
      and (.price != null) and (.cargoDescription | type == "string")
      and (has("quote") | not) and (has("cargo") | not)
    ' "$body_file" >/dev/null \
    || fail "$stack GET /v1/bookings/{id}: expected price + cargoDescription and NO quote/cargo, got $(cat "$body_file")"
  echo "lib.sh: ok — $stack GET /v1/bookings/{id}: price + cargoDescription present, quote/cargo absent" >&2

  # -- Media-type versioning: GET /bookings/{id}, Accept: v1 vendor type --
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -H 'Accept: application/vnd.shipping.v1+json' "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack GET /bookings/{id} (Accept: v1)"
  local content_type vary
  content_type="$(extract_header Content-Type "$headers_file")"
  assert_contains "$content_type" "vnd.shipping.v1" "$stack GET /bookings/{id} (Accept: v1) Content-Type"
  vary="$(extract_header Vary "$headers_file")"
  assert_contains "$vary" "Accept" "$stack GET /bookings/{id} (Accept: v1) Vary"
  jq -e '(has("price")) and (has("cargoDescription")) and (has("quote") | not) and (has("cargo") | not)' "$body_file" >/dev/null \
    || fail "$stack GET /bookings/{id} (Accept: v1): expected price + cargoDescription, got $(cat "$body_file")"
  echo "lib.sh: ok — $stack GET /bookings/{id} (Accept: v1): negotiated v1 body + headers" >&2

  # -- Media-type versioning: GET /bookings/{id}, Accept: v2 vendor type --
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -H 'Accept: application/vnd.shipping.v2+json' "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack GET /bookings/{id} (Accept: v2)"
  content_type="$(extract_header Content-Type "$headers_file")"
  assert_contains "$content_type" "vnd.shipping.v2" "$stack GET /bookings/{id} (Accept: v2) Content-Type"
  vary="$(extract_header Vary "$headers_file")"
  assert_contains "$vary" "Accept" "$stack GET /bookings/{id} (Accept: v2) Vary"
  validate_body Booking "$body_file"
  echo "lib.sh: ok — $stack GET /bookings/{id} (Accept: v2): negotiated v2 body + headers" >&2

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8094"
run_stack_tests "python" "http://localhost:8014"

echo
echo "PASS — Ch14 versioning: Quarkus and FastAPI both serve the frozen v1" \
     "(price + cargoDescription) and current v2 (quote + cargo[])" \
     "representations of the SAME booking, via both URI versioning" \
     "(/v1,/v2) and media-type content negotiation (Accept + Vary), on" \
     "both stacks."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
