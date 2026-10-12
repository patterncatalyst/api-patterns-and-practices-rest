#!/usr/bin/env bash
# examples/07-partial-updates/verify.sh
#
# Ch7 partial updates — extends the Ch4 contract-first anchor's Booking +
# Cargo resource model (contracts/openapi/shipping-api.yaml,
# contracts/schemas/shipping.schema.json) with BOTH partial-update media
# types on PATCH /bookings/{id}: RFC 7396 JSON Merge Patch
# (application/merge-patch+json) and RFC 6902 JSON Patch
# (application/json-patch+json). This drives both, contrasts their
# semantics, and schema-validates every response body against BOTH the
# Quarkus and the FastAPI stack. See README.md for the merge-patch vs
# json-patch comparison and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch07-patch"
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

wait_for_http "http://localhost:8087/q/health" 90
wait_for_http "http://localhost:8007/health" 60

# ---------------------------------------------------------------------------
# Step 3: drive create -> merge-patch (change) -> merge-patch (null removes
# a field) -> json-patch (replace) -> json-patch (failing test -> 409/422)
# -> PATCH with an unsupported Content-Type (-> 415) against EACH stack,
# schema-validating every response body.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- POST /bookings -> 201, Booking -------------------------------------
  local create_payload
  create_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
  local status
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  assert_header Location "$headers_file" "$stack POST /bookings"
  validate_body Booking "$body_file"

  local booking_id origin_before
  booking_id="$(jq -r '.id' "$body_file")"
  origin_before="$(jq -c '.origin' "$body_file")"

  # -- Merge Patch (application/merge-patch+json): change a field --------
  # requestedPickup moves from 2026-02-01 to 2026-03-01; origin (untouched
  # by the patch document) must be byte-identical afterwards.
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PATCH -H 'Content-Type: application/merge-patch+json' \
    -d '{"requestedPickup":"2026-03-01"}' "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack PATCH (merge-patch, change field)"
  validate_body Booking "$body_file"
  local patched_pickup origin_after
  patched_pickup="$(jq -r '.requestedPickup' "$body_file")"
  origin_after="$(jq -c '.origin' "$body_file")"
  [[ "$patched_pickup" == "2026-03-01" ]] || fail "$stack merge-patch did not apply (got requestedPickup=$patched_pickup)"
  [[ "$origin_after" == "$origin_before" ]] || fail "$stack merge-patch touched 'origin' it was never given (before=$origin_before after=$origin_after)"
  echo "lib.sh: ok — $stack merge-patch changed requestedPickup and left origin untouched"

  # -- Merge Patch: a field set to null DELETES it (RFC 7396) -------------
  # requestedPickup is optional/nullable-by-absence in the schema, so
  # setting it to JSON null must remove the key entirely from the response.
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PATCH -H 'Content-Type: application/merge-patch+json' \
    -d '{"requestedPickup":null}' "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack PATCH (merge-patch, null removes field)"
  validate_body Booking "$body_file"
  if jq -e 'has("requestedPickup")' "$body_file" >/dev/null; then
    fail "$stack merge-patch with requestedPickup:null did not remove the field"
  fi
  echo "lib.sh: ok — $stack merge-patch null removed requestedPickup"

  # -- JSON Patch (application/json-patch+json): replace op ---------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PATCH -H 'Content-Type: application/json-patch+json' \
    -d '[{"op":"replace","path":"/cargo/0/description","value":"Re-palletized electronics"}]' \
    "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack PATCH (json-patch, replace)"
  validate_body Booking "$body_file"
  local patched_description
  patched_description="$(jq -r '.cargo[0].description' "$body_file")"
  [[ "$patched_description" == "Re-palletized electronics" ]] \
    || fail "$stack json-patch replace did not apply (got cargo[0].description=$patched_description)"
  echo "lib.sh: ok — $stack json-patch replace changed cargo[0].description"

  # -- JSON Patch: a failing `test` op -> 409 (or 422), Problem ------------
  # The booking's status is still PENDING (nothing above touched it), so
  # asserting it's CONFIRMED must fail the `test` precondition.
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PATCH -H 'Content-Type: application/json-patch+json' \
    -d '[{"op":"test","path":"/status","value":"CONFIRMED"}]' \
    "$base/bookings/$booking_id")"
  if [[ "$status" != "409" && "$status" != "422" ]]; then
    fail "$stack json-patch failing test op: expected HTTP 409 or 422, got $status"
  fi
  echo "lib.sh: ok — $stack json-patch failing test op: HTTP $status"
  validate_body Problem "$body_file"

  # -- PATCH with an unsupported Content-Type -> 415, Problem --------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PATCH -H 'Content-Type: text/plain' -d 'not a patch document' \
    "$base/bookings/$booking_id")"
  assert_status 415 "$status" "$stack PATCH (unsupported content-type: text/plain)"
  validate_body Problem "$body_file"

  # -- And the same 415 for the "obvious" wrong guess, application/json ----
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PATCH -H 'Content-Type: application/json' -d '{"requestedPickup":"2026-04-01"}' \
    "$base/bookings/$booking_id")"
  assert_status 415 "$status" "$stack PATCH (unsupported content-type: application/json)"
  validate_body Problem "$body_file"

  # -- GET the booking one more time: still schema-conforming after all ---
  #    four PATCH calls above (two of which errored and must not have
  #    mutated state). --------------------------------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_id")"
  assert_status 200 "$status" "$stack GET /bookings/{id} (final state)"
  validate_body Booking "$body_file"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8087"
run_stack_tests "python" "http://localhost:8007"

echo
echo "PASS — Ch7 partial updates: Quarkus and FastAPI both implement RFC" \
     "7396 JSON Merge Patch and RFC 6902 JSON Patch on PATCH" \
     "/bookings/{id}, reject every other Content-Type with 415, and turn a" \
     "failed JSON Patch 'test' op into a Problem."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
