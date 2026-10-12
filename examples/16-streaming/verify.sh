#!/usr/bin/env bash
# examples/16-streaming/verify.sh
#
# Ch16 streaming deep-dive — both stacks extend the Ch4 contract-first
# Booking resource with three ways to deliver a sequence of
# #/$defs/BookingEvent payloads INCREMENTALLY rather than as one buffered
# response: Server-Sent Events, NDJSON export, and a dedicated chunked-
# transfer demo. This is the load-bearing step: it doesn't just check that
# each endpoint returns 200 with the right Content-Type — for the SSE
# endpoint it proves the bytes actually dripped in over wall-clock time
# (first-byte vs. last-byte spread), which is the one thing a naive
# "generate everything, then write it all at once" implementation would
# fail silently at the status-code/Content-Type level. See README.md for
# the full explainer and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch16-stream"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

# A syntactically valid but never-issued booking id (26 zeros — the
# Crockford alphabet includes '0', so this is a legal ULID shape).
NONEXISTENT_ID="bkg_$(printf '0%.0s' $(seq 1 26))"

# Must match EventGenerator.java's / app/events.py's constants exactly —
# verify.sh asserts against these, it doesn't read them back from the app.
SSE_EVENT_COUNT=5
SSE_INTERVAL_SECONDS=0.25
EXPORT_EVENT_COUNT=10
CHUNKED_LINE_COUNT=500

# The minimum acceptable first-byte-to-last-byte spread for the SSE stream,
# in seconds. The IDEAL spread is (SSE_EVENT_COUNT-1) * SSE_INTERVAL_SECONDS
# = 4 * 0.25 = 1.0s (time from the first frame arriving to the last frame
# arriving). This threshold is set well below that (60%) to absorb CI
# scheduling jitter and container startup noise, while staying far above
# the near-zero spread a BUFFERED implementation would produce (all frames
# generated internally, then flushed to the socket in one burst right
# before the connection closes).
SSE_MIN_SPREAD_SECONDS=0.6

# ---------------------------------------------------------------------------
# Header helpers (lib.sh's assert_header only checks presence; the test
# sequence below also needs header VALUES, and one case needs to assert a
# header's ABSENCE).
# ---------------------------------------------------------------------------

extract_header() {
  local name="$1" file="$2"
  grep -i "^${name}:" "$file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n'
}

assert_header_absent() {
  local header_name="$1" headers_file="$2" context="${3:-}"
  if grep -qi "^${header_name}:" "$headers_file"; then
    echo "lib.sh: FAIL — ${context:-header check}: '$header_name' header unexpectedly present" >&2
    return 1
  fi
  echo "lib.sh: ok — ${context:-header check}: '$header_name' header absent" >&2
}

awk_ge() {
  # True (exit 0) iff $1 >= $2, both floating-point strings.
  awk -v a="$1" -v b="$2" 'BEGIN { exit !(a >= b) }'
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

wait_for_http "http://localhost:8096/q/health" 90
wait_for_http "http://localhost:8016/health" 60

# ---------------------------------------------------------------------------
# Step 3: for EACH stack — create a booking (to have an id), then drive the
# SSE / NDJSON-export / chunked-export sequence, proving incremental
# delivery (not one buffered blob) for the SSE case.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.txt"
  local frame_file="$TMP_DIR/${stack}-frame.json"

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

  # -------------------------------------------------------------------
  # 3a. SSE: GET /bookings/{id}/events -> text/event-stream, EXACTLY
  #     SSE_EVENT_COUNT `data:` frames, each a valid BookingEvent, and —
  #     the load-bearing assertion — frame-to-frame WALL-CLOCK ARRIVAL
  #     TIMES that prove the frames actually dripped in over time.
  #
  #     NOTE: this deliberately does NOT use curl's aggregate
  #     `time_starttransfer`/`time_total` fields. Both Quarkus and FastAPI
  #     flush HTTP response HEADERS to the socket immediately (before the
  #     first event is even generated) regardless of whether the BODY is
  #     streamed or buffered — so `time_starttransfer` (time to first byte,
  #     which includes header bytes) comes back near-zero either way, and
  #     "time_total - time_starttransfer" ends up measuring the SAME total
  #     compute duration in both the good and the buffered-bug case. That
  #     was tried and verified to NOT distinguish the two. Instead, a
  #     second request is read line-by-line through a bash `read` loop
  #     piped straight from `curl -N` (no internal buffering), timestamping
  #     each line as it's actually delivered to the reader. A genuinely
  #     streamed response produces `data:` lines spread ~SSE_INTERVAL_apart;
  #     a buffered response delivers all of them within the same OS pipe
  #     read burst, microseconds apart, no matter how long the server
  #     internally slept before writing them.
  # -------------------------------------------------------------------
  status="$(curl -sS -D "$headers_file" -o /dev/null -w '%{http_code}' --max-time 8 \
    "$base/bookings/$booking_id/events")"
  assert_status 200 "$status" "$stack GET /bookings/{id}/events"

  local content_type
  content_type="$(extract_header Content-Type "$headers_file")"
  [[ "$content_type" == *"text/event-stream"* ]] \
    || fail "$stack SSE: expected Content-Type text/event-stream, got '$content_type'"
  echo "lib.sh: ok — $stack SSE Content-Type '$content_type'"

  local timed_file="$TMP_DIR/${stack}-sse-timed.txt"
  : > "$timed_file"
  while IFS= read -r line; do
    printf '%s|%s\n' "$(date +%s.%N)" "$line" >> "$timed_file"
  done < <(curl -sS -N --max-time 8 "$base/bookings/$booking_id/events")

  mapfile -t data_rows < <(grep '|data:' "$timed_file")
  [[ "${#data_rows[@]}" -eq "$SSE_EVENT_COUNT" ]] \
    || fail "$stack SSE: expected $SSE_EVENT_COUNT 'data:' frames, got ${#data_rows[@]}"
  echo "lib.sh: ok — $stack SSE emitted ${#data_rows[@]} frames"

  local i=0 first_ts="" last_ts=""
  for row in "${data_rows[@]}"; do
    local ts="${row%%|*}"
    local rest="${row#*|}"
    local json_frame
    json_frame="$(printf '%s' "$rest" | sed -E 's/^data:[[:space:]]*//')"
    echo "$json_frame" > "$frame_file"
    validate_body BookingEvent "$frame_file"
    [[ -z "$first_ts" ]] && first_ts="$ts"
    last_ts="$ts"
    i=$((i + 1))
  done
  echo "lib.sh: ok — $stack all $i SSE frames validate as BookingEvent"

  local spread
  spread="$(awk -v a="$last_ts" -v b="$first_ts" 'BEGIN { printf "%.3f", a - b }')"
  echo "lib.sh: $stack SSE timing — first frame read at ${first_ts}, last frame read at ${last_ts}, spread ${spread}s" >&2
  if ! awk_ge "$spread" "$SSE_MIN_SPREAD_SECONDS"; then
    fail "$stack SSE: frame-to-frame spread ${spread}s is below the ${SSE_MIN_SPREAD_SECONDS}s floor — these frames look BUFFERED (all arrived in one burst), not delivered incrementally"
  fi
  echo "lib.sh: ok — $stack SSE spread ${spread}s >= ${SSE_MIN_SPREAD_SECONDS}s floor — delivery is genuinely incremental"

  # -- SSE for an unknown booking -> 404, Problem --------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings/$NONEXISTENT_ID/events")"
  assert_status 404 "$status" "$stack GET /bookings/{nonexistent}/events"
  validate_body Problem "$body_file"

  # -------------------------------------------------------------------
  # 3b. NDJSON: GET /bookings/events/export -> application/x-ndjson,
  #     EXACTLY EXPORT_EVENT_COUNT non-empty lines, each a valid
  #     BookingEvent on its own line.
  # -------------------------------------------------------------------
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' "$base/bookings/events/export")"
  assert_status 200 "$status" "$stack GET /bookings/events/export"

  content_type="$(extract_header Content-Type "$headers_file")"
  [[ "$content_type" == *"application/x-ndjson"* ]] \
    || fail "$stack NDJSON export: expected Content-Type application/x-ndjson, got '$content_type'"
  echo "lib.sh: ok — $stack NDJSON export Content-Type '$content_type'"

  mapfile -t ndjson_lines < <(grep . "$body_file")
  [[ "${#ndjson_lines[@]}" -eq "$EXPORT_EVENT_COUNT" ]] \
    || fail "$stack NDJSON export: expected $EXPORT_EVENT_COUNT lines, got ${#ndjson_lines[@]}"

  i=0
  for line in "${ndjson_lines[@]}"; do
    echo "$line" > "$frame_file"
    validate_body BookingEvent "$frame_file"
    i=$((i + 1))
  done
  echo "lib.sh: ok — $stack NDJSON export produced $i valid BookingEvent lines"

  # -------------------------------------------------------------------
  # 3c. Chunked: GET /bookings/events/export/chunked -> no Content-Length
  #     (the response's total size is never known up front), proving this
  #     is real HTTP chunked transfer, not a pre-sized buffered body.
  # -------------------------------------------------------------------
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' "$base/bookings/events/export/chunked")"
  assert_status 200 "$status" "$stack GET /bookings/events/export/chunked"

  assert_header_absent Content-Length "$headers_file" "$stack chunked export"

  local transfer_encoding
  transfer_encoding="$(extract_header Transfer-Encoding "$headers_file")"
  [[ "$transfer_encoding" == *"chunked"* ]] \
    || fail "$stack chunked export: expected Transfer-Encoding: chunked, got '${transfer_encoding:-<absent>}'"
  echo "lib.sh: ok — $stack chunked export Transfer-Encoding '$transfer_encoding', no Content-Length"

  local chunked_line_count
  chunked_line_count="$(wc -l < "$body_file" | tr -d ' ')"
  [[ "$chunked_line_count" -ge "$CHUNKED_LINE_COUNT" ]] \
    || fail "$stack chunked export: expected >= $CHUNKED_LINE_COUNT lines, got $chunked_line_count"
  echo "lib.sh: ok — $stack chunked export delivered $chunked_line_count lines"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8096"
run_stack_tests "python" "http://localhost:8016"

echo
echo "PASS — Ch16 streaming deep-dive: Quarkus and FastAPI both deliver" \
     "Server-Sent Events, an NDJSON export, and a chunked-transfer export," \
     "and the SSE stream is proven to arrive INCREMENTALLY (a first-byte-to-" \
     "last-byte spread consistent with real delivery timing, not a" \
     "buffered burst)."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
