#!/usr/bin/env bash
# examples/27-complete-project/verify.sh
#
# Ch27 complete-project anchor — the book's integrative, end-to-end check. For BOTH stacks,
# this script drives ONE booking service through the whole book's flow end
# to end:
#   1. validate_response.py --selftest (the gate has teeth)
#   2. static contract checks: shipping.schema.json $ref'd by BOTH the
#      OpenAPI and the AsyncAPI documents; the Arazzo bookAndConfirm
#      workflow is structurally sound
#   3. contract-first create/read (Ch4): POST/GET /bookings vs #/$defs/Booking
#   4. keyset pagination (Ch8): limit + cursor, asserting the cursor
#      actually advances to a DIFFERENT next page
#   5. HATEOAS (Ch12): state-dependent `_links` on the booking and the
#      collection
#   6. async confirmation (Ch10): POST .../confirmation -> 202 -> bounded
#      poll of /operations/{id} -> 303 See Other
#   7. media-type versioning (Ch14): Accept negotiates v1 (frozen) vs v2
#      (current) representations of the SAME booking
#   8. soft delete + GDPR purge (Ch13): DELETE hides it, includeDeleted=true
#      still finds it (+ audit headers), purge removes it for good
#   9. NDJSON manifest (Ch16-style streaming): GET .../manifest/export
#      delivers BookingEvent records INCREMENTALLY, proven by per-line
#      wall-clock timing, not status-code/Content-Type alone
#  10. background CloudEvents (Ch21): confirming a booking publishes a
#      CloudEvents-enveloped BookingEvent to Kafka, consumed bounded and
#      validated against #/$defs/BookingEvent
#
# Tracing (Ch25 already proves trace export in CI) and load testing
# (Newman) are documented as LOCAL-ONLY in README.md and deliberately kept
# OUT of this gate.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch27-complete"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"
TOPIC="shipping.bookings.lifecycle"

# Must match ManifestEventGenerator.java's / app/manifest.py's constants.
MANIFEST_LINE_COUNT=6
MANIFEST_INTERVAL_SECONDS=0.25
# Ideal spread is (MANIFEST_LINE_COUNT-1) * MANIFEST_INTERVAL_SECONDS = 1.25s.
# Threshold set well below that to absorb CI jitter, while staying far
# above the near-zero spread a buffered implementation would produce.
MANIFEST_MIN_SPREAD_SECONDS=0.7

# Bounded poll for the Ch10 async confirmation: up to 12 x 0.5s = 6s, well
# above OperationStore.CONFIRMATION_DELAY_MS / CONFIRMATION_DELAY_SECONDS.
POLL_MAX_ATTEMPTS=12
POLL_INTERVAL_SECONDS=0.5

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

fail() {
  echo "lib.sh: FAIL — $*" >&2
  return 1
}

extract_header() {
  local name="$1" file="$2"
  grep -i "^${name}:" "$file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n'
}

resolve_location() {
  local base="$1" location="$2"
  case "$location" in
    http://*|https://*) echo "$location" ;;
    *) echo "${base}${location}" ;;
  esac
}

awk_ge() {
  awk -v a="$1" -v b="$2" 'BEGIN { exit !(a >= b) }'
}

# ---------------------------------------------------------------------------
# Step 1: prove the validation gate has teeth before trusting it for
# anything below.
# ---------------------------------------------------------------------------

ensure_verify_venv

echo "=== Step 1: validate_response.py --selftest ==="
"$LGTM_VERIFY_VENV_DIR/bin/python" -I "$VALIDATE_RESPONSE_PY" --selftest

# ---------------------------------------------------------------------------
# Step 2: static contract checks — fast, no services needed.
# ---------------------------------------------------------------------------

echo
echo "=== Step 2: static schema-reuse + Arazzo structural checks ==="

OPENAPI_FILE="$REPO_ROOT/contracts/openapi/shipping-api.yaml"
ASYNCAPI_FILE="$REPO_ROOT/contracts/asyncapi/shipping-events.yaml"
ARAZZO_FILE="$REPO_ROOT/contracts/arazzo/booking-workflow.yaml"

grep -q "shipping.schema.json" "$OPENAPI_FILE" \
  || fail "contracts/openapi/shipping-api.yaml does not \$ref shipping.schema.json"
echo "lib.sh: ok — OpenAPI \$refs shipping.schema.json"

grep -q "shipping.schema.json" "$ASYNCAPI_FILE" \
  || fail "contracts/asyncapi/shipping-events.yaml does not \$ref shipping.schema.json"
echo "lib.sh: ok — AsyncAPI \$refs shipping.schema.json"

"$LGTM_VERIFY_VENV_DIR/bin/python" -I "$SCRIPT_DIR/check_arazzo.py" "$ARAZZO_FILE"

# ---------------------------------------------------------------------------
# Step 3: bring the stack up (kafka + quarkus + python only — the
# `observability` profile is NOT started by a plain `compose up`).
# ---------------------------------------------------------------------------

echo
echo "=== Step 3: docker compose up (kafka + quarkus + python) ==="
compose_up "$COMPOSE_FILE" "$PROJECT"

wait_for_http "http://localhost:8106/q/health" 90
wait_for_http "http://localhost:8025/health" 60

# ---------------------------------------------------------------------------
# Step 4: for each stack, drive the whole flow.
# ---------------------------------------------------------------------------

EVENTS_SO_FAR=0

check_cloud_event() {
  local stack="$1" booking_id="$2"
  EVENTS_SO_FAR=$((EVENTS_SO_FAR + 1))

  local group="ch27-verify-${stack}-$$"
  local out_file="$TMP_DIR/${stack}-kafka-events.ndjson"

  echo "lib.sh: consuming up to $EVENTS_SO_FAR message(s) from $TOPIC for $stack (bounded, 20s) ..." >&2
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T kafka \
    /opt/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic "$TOPIC" \
    --from-beginning \
    --max-messages "$EVENTS_SO_FAR" \
    --timeout-ms 20000 \
    --group "$group" \
    >"$out_file" 2>/dev/null || true

  # kafka-console-consumer exits 0 on a timeout with ZERO messages read —
  # an empty file must still fail loudly rather than silently pass.
  if [[ ! -s "$out_file" ]]; then
    fail "$stack: no messages observed on $TOPIC within the bounded 20s timeout"
  fi

  local matches_file="$TMP_DIR/${stack}-event-matches.ndjson"
  jq -c --arg bid "$booking_id" 'select(.subject == $bid)' "$out_file" > "$matches_file"

  local match_count
  match_count="$(wc -l < "$matches_file" | tr -d ' ')"
  [[ "$match_count" -ge 1 ]] \
    || fail "$stack: no CloudEvent with subject == $booking_id observed on $TOPIC"

  local event_file="$TMP_DIR/${stack}-event.json"
  head -1 "$matches_file" > "$event_file"

  for attr in specversion id source type; do
    jq -e "has(\"$attr\")" "$event_file" >/dev/null \
      || fail "$stack: CloudEvents envelope missing required attribute '$attr'"
  done
  echo "lib.sh: ok — $stack CloudEvents envelope has specversion/id/source/type"

  local data_file="$TMP_DIR/${stack}-event-data.json"
  jq -c '.data' "$event_file" > "$data_file"
  validate_body BookingEvent "$data_file"
  echo "lib.sh: ok — $stack BookingEvent data conforms to #/\$defs/BookingEvent"
}

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Verifying stack '$stack' at $base ==="

  # -------------------------------------------------------------------
  # 4a. Contract-first create/read (Ch4) + HATEOAS on create (Ch12).
  #     Booking A carries 3 cargo items and drives confirmation +
  #     versioning + soft-delete/purge below.
  # -------------------------------------------------------------------
  local create_payload_a
  create_payload_a='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false},{"description":"Spare parts","type":"GENERAL","dimensions":{"weightKg":300.0,"volumeM3":1.1},"hazardous":false},{"description":"Machine oil","type":"LIQUID_BULK","dimensions":{"weightKg":500.0,"volumeM3":0.6},"hazardous":true}],"requestedPickup":"2026-02-01"}'

  local status
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload_a" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings (A)"
  assert_header Location "$headers_file" "$stack POST /bookings (A)"
  validate_body Booking "$body_file"

  local location_a booking_a
  location_a="$(extract_header Location "$headers_file")"
  booking_a="$(jq -r '.id' "$body_file")"
  echo "lib.sh: ok — $stack created booking A ($booking_a)"

  jq -e '._links.confirm and ._links.cancel' "$body_file" >/dev/null \
    || fail "$stack: PENDING booking A missing HATEOAS confirm/cancel links"
  echo "lib.sh: ok — $stack booking A (PENDING) carries confirm+cancel _links"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$(resolve_location "$base" "$location_a")")"
  assert_status 200 "$status" "$stack GET Location (A)"
  validate_body Booking "$body_file"

  # -------------------------------------------------------------------
  # 4b. A second booking (B) — filler for pagination, and the subject of
  #     the NDJSON manifest export later (A gets purged first).
  # -------------------------------------------------------------------
  local create_payload_b
  create_payload_b='{"origin":{"unLocode":"SGSIN","name":"Singapore","country":"SG"},"destination":{"unLocode":"USLAX","name":"Los Angeles","country":"US"},"cargo":[{"description":"Consumer electronics","type":"GENERAL","dimensions":{"weightKg":450.0,"volumeM3":2.0},"hazardous":false}],"requestedPickup":"2026-02-10"}'
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload_b" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings (B)"
  validate_body Booking "$body_file"
  local booking_b
  booking_b="$(jq -r '.id' "$body_file")"
  echo "lib.sh: ok — $stack created booking B ($booking_b)"

  # -------------------------------------------------------------------
  # 4c. Keyset pagination (Ch8): limit=1 twice, following the cursor,
  #     asserting the cursor ADVANCES to a genuinely different next page.
  # -------------------------------------------------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings?limit=1")"
  assert_status 200 "$status" "$stack GET /bookings?limit=1 (page 1)"
  validate_body BookingCollection "$body_file"

  local page1_id next_cursor
  page1_id="$(jq -r '.items[0].id' "$body_file")"
  next_cursor="$(jq -r '.page.nextCursor' "$body_file")"
  [[ -n "$page1_id" && "$page1_id" != "null" ]] || fail "$stack: pagination page 1 returned no items"
  [[ -n "$next_cursor" && "$next_cursor" != "null" ]] || fail "$stack: pagination page 1 has no nextCursor despite >1 visible booking"
  jq -e '._links.self' "$body_file" >/dev/null || fail "$stack: BookingCollection missing _links.self"
  echo "lib.sh: ok — $stack pagination page 1: item=$page1_id, nextCursor=$next_cursor"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings?limit=1&cursor=$next_cursor")"
  assert_status 200 "$status" "$stack GET /bookings?limit=1&cursor=... (page 2)"
  validate_body BookingCollection "$body_file"
  local page2_id
  page2_id="$(jq -r '.items[0].id' "$body_file")"
  [[ -n "$page2_id" && "$page2_id" != "null" ]] || fail "$stack: pagination page 2 returned no items"
  [[ "$page2_id" != "$page1_id" ]] || fail "$stack: pagination cursor did not advance — page 2 repeated page 1's item"
  [[ "$page2_id" > "$page1_id" ]] || fail "$stack: pagination page 2's id ($page2_id) is not > page 1's id ($page1_id)"
  echo "lib.sh: ok — $stack pagination cursor advances: page1=$page1_id -> page2=$page2_id (no overlap)"

  # -------------------------------------------------------------------
  # 4d. Async confirmation (Ch10): 202 -> bounded poll -> 303.
  # -------------------------------------------------------------------
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST "$base/bookings/$booking_a/confirmation")"
  assert_status 202 "$status" "$stack POST /bookings/{A}/confirmation"
  assert_header Location "$headers_file" "$stack POST /bookings/{A}/confirmation"
  validate_body Operation "$body_file"

  local op_location
  op_location="$(extract_header Location "$headers_file")"
  echo "lib.sh: ok — $stack confirmation accepted, operation at $op_location"

  local attempt=0 op_status=""
  while (( attempt < POLL_MAX_ATTEMPTS )); do
    status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
      "$(resolve_location "$base" "$op_location")")"
    if [[ "$status" == "303" ]]; then
      op_status="303"
      break
    fi
    assert_status 200 "$status" "$stack GET {operation} (poll, attempt $((attempt + 1)))"
    validate_body Operation "$body_file"
    attempt=$((attempt + 1))
    sleep "$POLL_INTERVAL_SECONDS"
  done
  [[ "$op_status" == "303" ]] \
    || fail "$stack: operation did not reach 303 within $POLL_MAX_ATTEMPTS attempts (${POLL_INTERVAL_SECONDS}s apart)"

  local resolved_location
  resolved_location="$(extract_header Location "$headers_file")"
  [[ "$resolved_location" == *"$booking_a"* ]] \
    || fail "$stack: operation's 303 Location ($resolved_location) does not reference booking A ($booking_a)"
  echo "lib.sh: ok — $stack operation reached 303 See Other -> $resolved_location"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_a")"
  assert_status 200 "$status" "$stack GET /bookings/{A} (post-confirmation)"
  validate_body Booking "$body_file"
  [[ "$(jq -r '.status' "$body_file")" == "CONFIRMED" ]] \
    || fail "$stack: booking A did not transition to CONFIRMED after the operation succeeded"
  jq -e '._links.cancel and (._links.confirm | not)' "$body_file" >/dev/null \
    || fail "$stack: CONFIRMED booking A should carry only a cancel _link (no confirm)"
  echo "lib.sh: ok — $stack booking A is CONFIRMED with state-appropriate _links"

  # -------------------------------------------------------------------
  # 4e. Media-type versioning (Ch14): Accept negotiates v1 vs v2.
  # -------------------------------------------------------------------
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -H 'Accept: application/vnd.shipping.booking.v1+json' "$base/bookings/$booking_a")"
  assert_status 200 "$status" "$stack GET /bookings/{A} (Accept v1)"
  local v1_content_type
  v1_content_type="$(extract_header Content-Type "$headers_file")"
  [[ "$v1_content_type" == *"application/vnd.shipping.booking.v1+json"* ]] \
    || fail "$stack: v1 negotiation returned Content-Type '$v1_content_type'"
  jq -e 'has("cargoDescription") and has("price") and (has("cargo") | not) and (has("quote") | not)' "$body_file" >/dev/null \
    || fail "$stack: v1 body does not have the frozen (cargoDescription/price, no cargo/quote) shape"
  echo "lib.sh: ok — $stack Accept:v1 negotiates the frozen BookingV1 shape"

  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -H 'Accept: application/vnd.shipping.booking.v2+json' "$base/bookings/$booking_a")"
  assert_status 200 "$status" "$stack GET /bookings/{A} (Accept v2)"
  local v2_content_type
  v2_content_type="$(extract_header Content-Type "$headers_file")"
  [[ "$v2_content_type" == *"application/vnd.shipping.booking.v2+json"* ]] \
    || fail "$stack: v2 negotiation returned Content-Type '$v2_content_type'"
  validate_body Booking "$body_file"
  echo "lib.sh: ok — $stack Accept:v2 negotiates the current Booking shape"

  # -------------------------------------------------------------------
  # 4f. Soft delete + GDPR purge (Ch13), on booking A.
  # -------------------------------------------------------------------
  status="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "$base/bookings/$booking_a")"
  assert_status 204 "$status" "$stack DELETE /bookings/{A} (soft delete)"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_a")"
  assert_status 404 "$status" "$stack GET /bookings/{A} (hidden after soft delete)"
  validate_body Problem "$body_file"

  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_a?includeDeleted=true")"
  assert_status 200 "$status" "$stack GET /bookings/{A}?includeDeleted=true"
  validate_body Booking "$body_file"
  [[ "$(jq -r '.status' "$body_file")" == "CANCELLED" ]] \
    || fail "$stack: includeDeleted view of booking A is not CANCELLED"
  assert_header X-Audit-Deleted-At "$headers_file" "$stack audit view"
  assert_header X-Audit-Reason "$headers_file" "$stack audit view"
  echo "lib.sh: ok — $stack soft-deleted booking A is CANCELLED + audit headers present under includeDeleted=true"

  status="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "$base/bookings/$booking_a/purge")"
  assert_status 204 "$status" "$stack DELETE /bookings/{A}/purge"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$booking_a?includeDeleted=true")"
  assert_status 404 "$status" "$stack GET /bookings/{A}?includeDeleted=true (post-purge)"
  validate_body Problem "$body_file"
  echo "lib.sh: ok — $stack booking A is gone for good after purge (even the audit view 404s)"

  # -------------------------------------------------------------------
  # 4g. NDJSON manifest export (Ch16-style streaming), on booking B.
  # -------------------------------------------------------------------
  local timed_file="$TMP_DIR/${stack}-manifest-timed.txt"
  local frame_file="$TMP_DIR/${stack}-manifest-frame.json"
  : > "$timed_file"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    printf '%s|%s\n' "$(date +%s.%N)" "$line" >> "$timed_file"
  done < <(curl -sS -N --max-time 8 "$base/bookings/$booking_b/manifest/export")

  mapfile -t manifest_lines < <(grep . "$timed_file")
  [[ "${#manifest_lines[@]}" -eq "$MANIFEST_LINE_COUNT" ]] \
    || fail "$stack: manifest export expected $MANIFEST_LINE_COUNT lines, got ${#manifest_lines[@]}"

  local first_ts="" last_ts=""
  for row in "${manifest_lines[@]}"; do
    local ts="${row%%|*}"
    local json_line="${row#*|}"
    echo "$json_line" > "$frame_file"
    validate_body BookingEvent "$frame_file"
    [[ -z "$first_ts" ]] && first_ts="$ts"
    last_ts="$ts"
  done
  echo "lib.sh: ok — $stack manifest export emitted ${#manifest_lines[@]} valid BookingEvent lines"

  local spread
  spread="$(awk -v a="$last_ts" -v b="$first_ts" 'BEGIN { printf "%.3f", a - b }')"
  echo "lib.sh: $stack manifest timing — first line at ${first_ts}, last line at ${last_ts}, spread ${spread}s" >&2
  awk_ge "$spread" "$MANIFEST_MIN_SPREAD_SECONDS" \
    || fail "$stack: manifest export spread ${spread}s is below the ${MANIFEST_MIN_SPREAD_SECONDS}s floor — looks BUFFERED, not incremental"
  echo "lib.sh: ok — $stack manifest export spread ${spread}s >= ${MANIFEST_MIN_SPREAD_SECONDS}s floor — genuinely incremental"

  # -------------------------------------------------------------------
  # 4h. Background CloudEvents (Ch21): booking A's confirmation publish.
  # -------------------------------------------------------------------
  check_cloud_event "$stack" "$booking_a"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8106"
run_stack_tests "python" "http://localhost:8025"

echo
echo "PASS — Ch27 complete-project anchor: both Quarkus and FastAPI run ONE" \
     "booking service exercising contract-first create/read, keyset" \
     "pagination with an advancing cursor, HATEOAS state-dependent _links," \
     "async confirmation (202 -> poll -> 303), media-type versioning (v1" \
     "vs v2), soft delete + GDPR purge, an incrementally-streamed NDJSON" \
     "manifest, and a background CloudEvents publish over Kafka — all" \
     "validated against the ONE shared contracts/schemas/shipping.schema.json," \
     "which both contracts/openapi/shipping-api.yaml and" \
     "contracts/asyncapi/shipping-events.yaml \$ref, with the Arazzo" \
     "bookAndConfirm workflow structurally sound."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
