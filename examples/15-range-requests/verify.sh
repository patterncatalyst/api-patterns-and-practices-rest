#!/usr/bin/env bash
# examples/15-range-requests/verify.sh
#
# Ch15 large binary resources & Range — both stacks serve
# /bookings/{bookingId}/manifest, a deterministic, fixed-size, in-memory
# binary resource, with HTTP Range support (RFC 9110 §14): HEAD for
# size/capability, a plain GET for the full body, a bounded Range for a
# 206 Partial Content slice, an open-ended Range, and an unsatisfiable
# Range for 416. See README.md for the Range/206/Content-Range/416
# explainer and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch15-range"
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
# sequence below also needs header VALUES — Content-Length, Content-Range).
# ---------------------------------------------------------------------------

extract_header() {
  local name="$1" file="$2"
  grep -i "^${name}:" "$file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n'
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

wait_for_http "http://localhost:8095/q/health" 90
wait_for_http "http://localhost:8015/health" 60

# ---------------------------------------------------------------------------
# Step 3: for EACH stack — create a booking (to have an id), then drive the
# HEAD / full-GET / bounded-Range / open-Range / unsatisfiable-Range /
# unknown-booking sequence against its manifest.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.bin"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- POST /bookings -> 201, Booking (just to mint an id) -----------------
  local create_payload
  create_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
  local status
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  validate_body Booking "$body_file"

  local booking_id
  booking_id="$(jq -r '.id' "$body_file")"
  echo "lib.sh: ok — $stack booking $booking_id created"

  # -- HEAD /bookings/{id}/manifest -> 200, Accept-Ranges, Content-Length ---
  # `curl -I`/`--head`, NOT `-X HEAD`: libcurl only suppresses its
  # "wait for a body matching Content-Length" logic when it KNOWS the
  # request is a HEAD via -I/--head. `-X HEAD` just swaps the method
  # string on an otherwise ordinary GET-shaped request, so curl still
  # expects (and hangs forever waiting for) the Content-Length bytes a
  # correct HEAD response never sends.
  status="$(curl -sS -D "$headers_file" -o /dev/null -w '%{http_code}' \
    --head "$base/bookings/$booking_id/manifest")"
  assert_status 200 "$status" "$stack HEAD manifest"
  assert_header Accept-Ranges "$headers_file" "$stack HEAD manifest"

  local total
  total="$(extract_header Content-Length "$headers_file")"
  [[ "$total" =~ ^[0-9]+$ ]] || fail "$stack HEAD manifest: missing/invalid Content-Length (got '$total')"
  echo "lib.sh: ok — $stack manifest TOTAL size = $total bytes"

  # -- GET /bookings/{id}/manifest (no Range) -> 200, full body -------------
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    "$base/bookings/$booking_id/manifest")"
  assert_status 200 "$status" "$stack GET manifest (full)"
  assert_header Accept-Ranges "$headers_file" "$stack GET manifest (full)"

  local full_len
  full_len="$(wc -c < "$body_file" | tr -d ' ')"
  [[ "$full_len" == "$total" ]] || fail "$stack GET manifest (full): expected $total bytes, got $full_len"
  echo "lib.sh: ok — $stack GET manifest (full) returned $full_len bytes"

  # -- GET with Range: bytes=0-1023 -> 206, Content-Range, 1024 bytes ------
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -H 'Range: bytes=0-1023' "$base/bookings/$booking_id/manifest")"
  assert_status 206 "$status" "$stack GET manifest (Range 0-1023)"

  local content_range range_len
  content_range="$(extract_header Content-Range "$headers_file")"
  [[ "$content_range" == "bytes 0-1023/$total" ]] \
    || fail "$stack GET manifest (Range 0-1023): expected Content-Range 'bytes 0-1023/$total', got '$content_range'"
  range_len="$(wc -c < "$body_file" | tr -d ' ')"
  [[ "$range_len" == "1024" ]] || fail "$stack GET manifest (Range 0-1023): expected 1024 bytes, got $range_len"
  echo "lib.sh: ok — $stack bounded Range 0-1023 -> 206, Content-Range '$content_range', 1024 bytes"

  # -- GET with Range: bytes=1024- (open) -> 206, Content-Range to TOTAL-1 -
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -H 'Range: bytes=1024-' "$base/bookings/$booking_id/manifest")"
  assert_status 206 "$status" "$stack GET manifest (Range 1024-, open)"

  local expected_end expected_len
  expected_end=$((total - 1))
  expected_len=$((total - 1024))
  content_range="$(extract_header Content-Range "$headers_file")"
  [[ "$content_range" == "bytes 1024-$expected_end/$total" ]] \
    || fail "$stack GET manifest (open Range): expected Content-Range 'bytes 1024-$expected_end/$total', got '$content_range'"
  range_len="$(wc -c < "$body_file" | tr -d ' ')"
  [[ "$range_len" == "$expected_len" ]] \
    || fail "$stack GET manifest (open Range): expected $expected_len bytes, got $range_len"
  echo "lib.sh: ok — $stack open Range 1024- -> 206, Content-Range '$content_range', $range_len bytes"

  # -- GET with an unsatisfiable Range (start past EOF) -> 416 -------------
  local bad_start bad_end
  bad_start=$((total + 100))
  bad_end=$((total + 200))
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -H "Range: bytes=${bad_start}-${bad_end}" "$base/bookings/$booking_id/manifest")"
  assert_status 416 "$status" "$stack GET manifest (unsatisfiable Range)"

  content_range="$(extract_header Content-Range "$headers_file")"
  [[ "$content_range" == "bytes */$total" ]] \
    || fail "$stack GET manifest (unsatisfiable Range): expected Content-Range 'bytes */$total', got '$content_range'"
  echo "lib.sh: ok — $stack unsatisfiable Range -> 416, Content-Range '$content_range'"

  # -- HEAD/GET manifest for an UNKNOWN booking -> 404, Problem ------------
  # A 404 has no Content-Length surprise either way, but --head stays
  # consistent with the HEAD call above.
  status="$(curl -sS -o /dev/null -w '%{http_code}' \
    --head "$base/bookings/$NONEXISTENT_ID/manifest")"
  assert_status 404 "$status" "$stack HEAD manifest (unknown booking)"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    "$base/bookings/$NONEXISTENT_ID/manifest")"
  assert_status 404 "$status" "$stack GET manifest (unknown booking)"
  validate_body Problem "$body_file"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8095"
run_stack_tests "python" "http://localhost:8015"

echo
echo "PASS — Ch15 large binary resources & Range: Quarkus and FastAPI both" \
     "serve a known-size manifest with correct HEAD metadata, full-body GET," \
     "bounded and open-ended 206 Partial Content Ranges, a 416 for an" \
     "unsatisfiable Range, and a 404 Problem for an unknown booking."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
