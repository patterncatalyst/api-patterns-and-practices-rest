#!/usr/bin/env bash
# examples/23-fastapi-depth/verify.sh
#
# Ch23 "FastAPI in depth" anchor — a single-stack (FastAPI-only) example
# proving the chapter's thesis: ASGI depth beyond "it returns JSON". Three
# mechanics, each asserted for its OBSERVABLE effect, not just a status
# code:
#
#   1. StreamingResponse/SSE — GET /bookings/{id}/events delivers
#      `#/$defs/BookingEvent` frames INCREMENTALLY, proven with the same
#      technique as Ch16/Ch22: a second request is read line-by-line
#      through a bash `read` loop piped straight from `curl -N`,
#      timestamping each `data:` line as it actually arrives. A buffered
#      implementation would pass every status-code/Content-Type check here
#      and still fail this timing assertion.
#   2. BackgroundTasks — POST /bookings/{id}/notify returns 202 PROMPTLY
#      (asserted against a wall-clock budget well under the background
#      task's own delay), the side effect is NOT yet observable immediately
#      after (GET .../notifications is still empty), and then IS observable
#      once polled within a bounded timeout — proving the work genuinely
#      ran after the response, not before it behind a disguised 202.
#   3. async vs. threadpool — GET /thread/async (an `async def` handler)
#      always reports running on the process's main thread (uvicorn's event
#      loop); GET /thread/sync (a plain `def` handler) never does, because
#      Starlette offloads it to an anyio threadpool worker. Same request,
#      same process, two different execution contexts.
#
# See README.md for the full explainer and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch23-fastapi"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"
BASE="http://localhost:8022"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

# A syntactically valid but never-issued booking id (26 zeros — the
# Crockford alphabet includes '0', so this is a legal ULID shape).
NONEXISTENT_ID="bkg_$(printf '0%.0s' $(seq 1 26))"

# Must match app/events.py's / app/main.py's constants exactly — verify.sh
# asserts against these, it doesn't read them back from the app.
SSE_EVENT_COUNT=5
SSE_INTERVAL_SECONDS=0.25
NOTIFY_DELAY_SECONDS=1.0

# The minimum acceptable first-byte-to-last-byte spread for the SSE stream,
# in seconds. The IDEAL spread is (SSE_EVENT_COUNT-1) * SSE_INTERVAL_SECONDS
# = 4 * 0.25 = 1.0s. This threshold sits well below that (60%) to absorb CI
# scheduling jitter, while staying far above the near-zero spread a
# BUFFERED implementation would produce.
SSE_MIN_SPREAD_SECONDS=0.6

# POST /notify must return well before NOTIFY_DELAY_SECONDS elapses — this
# is the "prompt response" half of the BackgroundTasks assertion.
NOTIFY_MAX_RESPONSE_SECONDS=0.5

# Bounded poll for the notification side effect to become observable.
NOTIFY_POLL_TIMEOUT_SECONDS=5
NOTIFY_POLL_INTERVAL_SECONDS=0.25

# ---------------------------------------------------------------------------
# Helpers (lib.sh's assert_header only checks presence; some assertions
# below need header/body VALUES or a float comparison).
# ---------------------------------------------------------------------------

extract_header() {
  local name="$1" file="$2"
  grep -i "^${name}:" "$file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n'
}

awk_ge() {
  # True (exit 0) iff $1 >= $2, both floating-point strings.
  awk -v a="$1" -v b="$2" 'BEGIN { exit !(a >= b) }'
}

awk_le() {
  # True (exit 0) iff $1 <= $2, both floating-point strings.
  awk -v a="$1" -v b="$2" 'BEGIN { exit !(a <= b) }'
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

wait_for_http "$BASE/health" 60

# ---------------------------------------------------------------------------
# Step 3: POST /bookings -> 201, Booking (just to mint an id).
# ---------------------------------------------------------------------------

echo
echo "=== Step 3: POST /bookings (mint a booking id) ==="

headers_file="$TMP_DIR/headers.txt"
body_file="$TMP_DIR/body.json"
frame_file="$TMP_DIR/frame.json"

create_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'
status="$(curl -sS -o "$body_file" -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' -d "$create_payload" "$BASE/bookings")"
assert_status 201 "$status" "POST /bookings"
validate_body Booking "$body_file"

booking_id="$(jq -r '.id' "$body_file")"
echo "lib.sh: ok — booking $booking_id created"

# ---------------------------------------------------------------------------
# Step 4: StreamingResponse/SSE — incremental delivery, schema-valid frames.
#
# NOTE: this deliberately does NOT use curl's aggregate
# `time_starttransfer`/`time_total` fields — both a streamed and a buffered
# implementation flush HTTP response HEADERS immediately, before the first
# event is even generated, so that aggregate comparison does not distinguish
# the two cases (verified while building Ch16). Instead, a second request is
# read line-by-line through a bash `read` loop piped straight from
# `curl -N` (no internal buffering), timestamping each line as it's
# actually delivered to the reader.
# ---------------------------------------------------------------------------

echo
echo "=== Step 4: GET /bookings/{id}/events (SSE) — incremental delivery ==="

status="$(curl -sS -D "$headers_file" -o /dev/null -w '%{http_code}' --max-time 8 \
  "$BASE/bookings/$booking_id/events")"
assert_status 200 "$status" "GET /bookings/{id}/events"

content_type="$(extract_header Content-Type "$headers_file")"
[[ "$content_type" == *"text/event-stream"* ]] \
  || fail "SSE: expected Content-Type text/event-stream, got '$content_type'"
echo "lib.sh: ok — SSE Content-Type '$content_type'"

timed_file="$TMP_DIR/sse-timed.txt"
: > "$timed_file"
while IFS= read -r line; do
  printf '%s|%s\n' "$(date +%s.%N)" "$line" >> "$timed_file"
done < <(curl -sS -N --max-time 8 "$BASE/bookings/$booking_id/events")

mapfile -t data_rows < <(grep '|data:' "$timed_file")
[[ "${#data_rows[@]}" -eq "$SSE_EVENT_COUNT" ]] \
  || fail "SSE: expected $SSE_EVENT_COUNT 'data:' frames, got ${#data_rows[@]}"
echo "lib.sh: ok — SSE emitted ${#data_rows[@]} frames"

i=0 first_ts="" last_ts=""
for row in "${data_rows[@]}"; do
  ts="${row%%|*}"
  rest="${row#*|}"
  json_frame="$(printf '%s' "$rest" | sed -E 's/^data:[[:space:]]*//')"
  echo "$json_frame" > "$frame_file"
  validate_body BookingEvent "$frame_file"
  [[ -z "$first_ts" ]] && first_ts="$ts"
  last_ts="$ts"
  i=$((i + 1))
done
echo "lib.sh: ok — all $i SSE frames validate as BookingEvent"

spread="$(awk -v a="$last_ts" -v b="$first_ts" 'BEGIN { printf "%.3f", a - b }')"
echo "lib.sh: SSE timing — first frame read at ${first_ts}, last frame read at ${last_ts}, spread ${spread}s" >&2
if ! awk_ge "$spread" "$SSE_MIN_SPREAD_SECONDS"; then
  fail "SSE: frame-to-frame spread ${spread}s is below the ${SSE_MIN_SPREAD_SECONDS}s floor — these frames look BUFFERED (all arrived in one burst), not delivered incrementally"
fi
echo "lib.sh: ok — SSE spread ${spread}s >= ${SSE_MIN_SPREAD_SECONDS}s floor — delivery is genuinely incremental"

# -- SSE for an unknown booking -> 404, Problem ------------------------------
status="$(curl -sS -o "$body_file" -w '%{http_code}' "$BASE/bookings/$NONEXISTENT_ID/events")"
assert_status 404 "$status" "GET /bookings/{nonexistent}/events"
validate_body Problem "$body_file"
echo "lib.sh: ok — SSE on an unknown booking id returns 404 Problem"

# ---------------------------------------------------------------------------
# Step 5: BackgroundTasks — prompt response, deferred-but-observable effect.
# ---------------------------------------------------------------------------

echo
echo "=== Step 5: POST /bookings/{id}/notify (BackgroundTasks) ==="

notify_payload='{"message":"Your shipment has cleared customs."}'

start_ts="$(date +%s.%N)"
status="$(curl -sS -o "$body_file" -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' -d "$notify_payload" \
  "$BASE/bookings/$booking_id/notify")"
end_ts="$(date +%s.%N)"
assert_status 202 "$status" "POST /bookings/{id}/notify"

response_time="$(awk -v a="$end_ts" -v b="$start_ts" 'BEGIN { printf "%.3f", a - b }')"
echo "lib.sh: POST /notify responded in ${response_time}s (budget ${NOTIFY_MAX_RESPONSE_SECONDS}s, background delay ${NOTIFY_DELAY_SECONDS}s)" >&2
if ! awk_le "$response_time" "$NOTIFY_MAX_RESPONSE_SECONDS"; then
  fail "POST /notify took ${response_time}s, exceeding the ${NOTIFY_MAX_RESPONSE_SECONDS}s prompt-response budget — looks like the notification ran SYNCHRONOUSLY before the response was sent, not as a background task"
fi
echo "lib.sh: ok — POST /notify returned promptly (${response_time}s < ${NOTIFY_MAX_RESPONSE_SECONDS}s), well before the ${NOTIFY_DELAY_SECONDS}s background delay"

queued_status="$(jq -r '.status' "$body_file")"
[[ "$queued_status" == "queued" ]] \
  || fail "POST /notify: expected status 'queued', got '$queued_status'"

# -- Immediately after: the side effect must NOT be observable yet ----------
status="$(curl -sS -o "$body_file" -w '%{http_code}' "$BASE/bookings/$booking_id/notifications")"
assert_status 200 "$status" "GET /bookings/{id}/notifications (immediately after POST)"
immediate_count="$(jq '.notifications | length' "$body_file")"
[[ "$immediate_count" -eq 0 ]] \
  || fail "GET /notifications immediately after POST: expected 0 notifications (background task hasn't run yet), got $immediate_count — looks like the work ran synchronously, not in the background"
echo "lib.sh: ok — immediately after POST, notification is NOT yet observable (background task hasn't run) — 0 notifications"

# -- Poll (bounded timeout) until the side effect becomes observable --------
waited=0
observed_count=0
while awk_le "$waited" "$NOTIFY_POLL_TIMEOUT_SECONDS"; do
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$BASE/bookings/$booking_id/notifications")"
  assert_status 200 "$status" "GET /bookings/{id}/notifications (polling)"
  observed_count="$(jq '.notifications | length' "$body_file")"
  if [[ "$observed_count" -ge 1 ]]; then
    break
  fi
  sleep "$NOTIFY_POLL_INTERVAL_SECONDS"
  waited="$(awk -v a="$waited" -v b="$NOTIFY_POLL_INTERVAL_SECONDS" 'BEGIN { printf "%.3f", a + b }')"
done

[[ "$observed_count" -ge 1 ]] \
  || fail "notification side effect never became observable within ${NOTIFY_POLL_TIMEOUT_SECONDS}s — background task did not run (or didn't persist its effect)"
echo "lib.sh: ok — notification side effect became observable after ~${waited}s (bounded poll, timeout ${NOTIFY_POLL_TIMEOUT_SECONDS}s)"

observed_message="$(jq -r '.notifications[0].message' "$body_file")"
[[ "$observed_message" == "Your shipment has cleared customs." ]] \
  || fail "notification message mismatch: expected the posted message, got '$observed_message'"
echo "lib.sh: ok — observed notification carries the posted message"

# -- notify on an unknown booking -> 404, Problem ----------------------------
status="$(curl -sS -o "$body_file" -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' -d "$notify_payload" \
  "$BASE/bookings/$NONEXISTENT_ID/notify")"
assert_status 404 "$status" "POST /bookings/{nonexistent}/notify"
validate_body Problem "$body_file"
echo "lib.sh: ok — notify on an unknown booking id returns 404 Problem"

# ---------------------------------------------------------------------------
# Step 6: async vs. threadpool — different execution contexts, same process.
# ---------------------------------------------------------------------------

echo
echo "=== Step 6: GET /thread/async vs. GET /thread/sync ==="

status="$(curl -sS -o "$body_file" -w '%{http_code}' "$BASE/thread/async")"
assert_status 200 "$status" "GET /thread/async"
async_is_main="$(jq -r '.isMainThread' "$body_file")"
async_thread_name="$(jq -r '.threadName' "$body_file")"
[[ "$async_is_main" == "true" ]] \
  || fail "GET /thread/async: expected isMainThread=true (event loop runs on the main thread), got '$async_is_main' (thread '$async_thread_name')"
echo "lib.sh: ok — /thread/async ran on the main thread (event loop), thread name '$async_thread_name'"

status="$(curl -sS -o "$body_file" -w '%{http_code}' "$BASE/thread/sync")"
assert_status 200 "$status" "GET /thread/sync"
sync_is_main="$(jq -r '.isMainThread' "$body_file")"
sync_thread_name="$(jq -r '.threadName' "$body_file")"
[[ "$sync_is_main" == "false" ]] \
  || fail "GET /thread/sync: expected isMainThread=false (Starlette offloads plain 'def' handlers to a threadpool), got '$sync_is_main' (thread '$sync_thread_name')"
echo "lib.sh: ok — /thread/sync ran OFF the main thread (threadpool worker), thread name '$sync_thread_name'"

[[ "$async_thread_name" != "$sync_thread_name" ]] \
  || fail "expected /thread/async and /thread/sync to report DIFFERENT thread names, both reported '$async_thread_name'"
echo "lib.sh: ok — async ('$async_thread_name') and sync ('$sync_thread_name') handlers ran on distinct execution contexts"

# Repeat once more to confirm determinism (not a fluke of request ordering).
status="$(curl -sS -o "$body_file" -w '%{http_code}' "$BASE/thread/async")"
assert_status 200 "$status" "GET /thread/async (2nd call)"
[[ "$(jq -r '.isMainThread' "$body_file")" == "true" ]] \
  || fail "GET /thread/async (2nd call): expected isMainThread=true again"

status="$(curl -sS -o "$body_file" -w '%{http_code}' "$BASE/thread/sync")"
assert_status 200 "$status" "GET /thread/sync (2nd call)"
[[ "$(jq -r '.isMainThread' "$body_file")" == "false" ]] \
  || fail "GET /thread/sync (2nd call): expected isMainThread=false again"
echo "lib.sh: ok — repeated calls are deterministic: async always main-thread, sync never main-thread"

echo
echo "PASS — Ch23 FastAPI in depth: StreamingResponse/SSE delivers" \
     "#/\$defs/BookingEvent frames INCREMENTALLY (proven by frame-to-frame" \
     "wall-clock timing), BackgroundTasks returns 202 PROMPTLY and defers" \
     "an OBSERVABLE side effect until after the response (absent" \
     "immediately after, present on a bounded poll), and async-def vs." \
     "plain-def handlers are PROVEN to run on different execution contexts" \
     "(event loop main thread vs. threadpool worker)."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
