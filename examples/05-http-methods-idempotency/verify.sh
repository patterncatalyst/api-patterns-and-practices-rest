#!/usr/bin/env bash
# examples/05-http-methods-idempotency/verify.sh
#
# Ch5 HTTP methods & the idempotency matrix — extends the Ch4 contract-first
# anchor's Booking resource with the full method matrix on /bookings and
# /bookings/{id}, 405s for unsupported methods (with an Allow header and a
# Problem body), and the behaviors that make "idempotent" a load-bearing
# word rather than a vibe: PUT replaces the SAME resource state on every
# call, POST mints a NEW resource on every call, and DELETE reaches the
# SAME end state (gone) on every call even though its status code changes
# (204 then 404). See README.md for the full method x safe/idempotent
# matrix and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch05-methods"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

# ---------------------------------------------------------------------------
# Header helpers (lib.sh's assert_header only checks presence; several
# assertions below need the VALUE too).
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

wait_for_http "http://localhost:8080/q/health" 90
wait_for_http "http://localhost:8000/health" 60

# ---------------------------------------------------------------------------
# Step 3: drive the method matrix + idempotency sequence against EACH
# stack, schema-validating every response body.
# ---------------------------------------------------------------------------

CREATE_PAYLOAD='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
PUT_PAYLOAD='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"SGSIN","name":"Singapore","country":"SG"},"cargo":[{"description":"Replacement manifest","type":"GENERAL","dimensions":{"weightKg":800,"volumeM3":2.0},"hazardous":false}]}'

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_a="$TMP_DIR/${stack}-a.json"
  local body_b="$TMP_DIR/${stack}-b.json"
  local status

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- (1) POST /bookings twice -> 201, 201; distinct ids (non-idempotent) --
  status="$(curl -sS -o "$body_a" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings (1st)"
  validate_body Booking "$body_a"

  status="$(curl -sS -o "$body_b" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings (2nd)"
  validate_body Booking "$body_b"

  local id_1 id_2
  id_1="$(jq -r '.id' "$body_a")"
  id_2="$(jq -r '.id' "$body_b")"
  [[ "$id_1" != "$id_2" ]] || fail "$stack two identical POST /bookings calls produced the SAME id ($id_1) — POST must not be idempotent"
  echo "lib.sh: ok — $stack two POSTs minted distinct bookings ($id_1 != $id_2)"

  # -- (2) PUT /bookings/{id_1} with the SAME body twice -> identical state
  #        (idempotent), modulo the volatile updatedAt timestamp -----------
  local put_1="$TMP_DIR/${stack}-put1.json" put_2="$TMP_DIR/${stack}-put2.json"
  status="$(curl -sS -o "$put_1" -w '%{http_code}' \
    -X PUT -H 'Content-Type: application/json' -d "$PUT_PAYLOAD" "$base/bookings/$id_1")"
  assert_status 200 "$status" "$stack PUT /bookings/{id} (1st)"
  validate_body Booking "$put_1"

  status="$(curl -sS -o "$put_2" -w '%{http_code}' \
    -X PUT -H 'Content-Type: application/json' -d "$PUT_PAYLOAD" "$base/bookings/$id_1")"
  assert_status 200 "$status" "$stack PUT /bookings/{id} (2nd, same body)"
  validate_body Booking "$put_2"

  local put_1_stable put_2_stable
  put_1_stable="$TMP_DIR/${stack}-put1-stable.json"
  put_2_stable="$TMP_DIR/${stack}-put2-stable.json"
  jq -S 'del(.updatedAt)' "$put_1" > "$put_1_stable"
  jq -S 'del(.updatedAt)' "$put_2" > "$put_2_stable"
  if ! diff -u "$put_1_stable" "$put_2_stable" >/dev/null; then
    echo "lib.sh: PUT responses diverged (ignoring updatedAt):" >&2
    diff -u "$put_1_stable" "$put_2_stable" >&2 || true
    fail "$stack two identical PUT /bookings/{id} calls produced DIFFERENT resource state — PUT must be idempotent"
  fi
  echo "lib.sh: ok — $stack two identical PUTs produced byte-identical state (updatedAt excluded)"

  # -- (3) HEAD /bookings/{id} — safe, same headers as GET, no body --------
  status="$(curl -sS -I -o "$headers_file" -w '%{http_code}' "$base/bookings/$id_1")"
  assert_status 200 "$status" "$stack HEAD /bookings/{id}"

  # -- (4) 405 on methods the COLLECTION doesn't support (PUT) -------------
  status="$(curl -sS -D "$headers_file" -o "$body_a" -w '%{http_code}' \
    -X PUT -H 'Content-Type: application/json' -d "$PUT_PAYLOAD" "$base/bookings")"
  assert_status 405 "$status" "$stack PUT /bookings (unsupported on collection)"
  validate_body Problem "$body_a"
  assert_header Allow "$headers_file" "$stack PUT /bookings Allow header"
  local allow_collection
  allow_collection="$(extract_header Allow "$headers_file")"
  [[ "$allow_collection" == *GET* && "$allow_collection" == *POST* ]] \
    || fail "$stack PUT /bookings Allow header ('$allow_collection') does not list GET and POST"
  echo "lib.sh: ok — $stack PUT /bookings -> 405, Allow: $allow_collection"

  # -- (5) 405 on methods an ITEM doesn't support (POST) --------------------
  status="$(curl -sS -D "$headers_file" -o "$body_a" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD" "$base/bookings/$id_1")"
  assert_status 405 "$status" "$stack POST /bookings/{id} (unsupported on item)"
  validate_body Problem "$body_a"
  assert_header Allow "$headers_file" "$stack POST /bookings/{id} Allow header"
  local allow_item
  allow_item="$(extract_header Allow "$headers_file")"
  [[ "$allow_item" == *GET* && "$allow_item" == *PUT* && "$allow_item" == *DELETE* ]] \
    || fail "$stack POST /bookings/{id} Allow header ('$allow_item') does not list GET, PUT and DELETE"
  echo "lib.sh: ok — $stack POST /bookings/{id} -> 405, Allow: $allow_item"

  # -- (6) DELETE semantics: 204, then 404 on the same id, then GET 404 ----
  status="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "$base/bookings/$id_2")"
  assert_status 204 "$status" "$stack DELETE /bookings/{id} (1st)"

  status="$(curl -sS -o "$body_a" -w '%{http_code}' -X DELETE "$base/bookings/$id_2")"
  assert_status 404 "$status" "$stack DELETE /bookings/{id} (2nd, already gone)"
  validate_body Problem "$body_a"

  status="$(curl -sS -o "$body_a" -w '%{http_code}' "$base/bookings/$id_2")"
  assert_status 404 "$status" "$stack GET /bookings/{id} (after delete)"
  validate_body Problem "$body_a"
  echo "lib.sh: ok — $stack DELETE is idempotent in END STATE: 204 then 404, GET then 404"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8080"
run_stack_tests "python" "http://localhost:8000"

echo
echo "PASS — Ch5 HTTP methods & idempotency: Quarkus and FastAPI both" \
     "implement the full method matrix, reject unsupported methods with a" \
     "405 + Allow + Problem, and agree on what idempotent actually means:" \
     "PUT converges, POST mints, DELETE reaches the same end state twice."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
