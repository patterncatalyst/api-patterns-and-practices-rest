#!/usr/bin/env bash
# examples/22-quarkus-rest-depth/verify.sh
#
# Ch22 "Quarkus REST in depth" anchor — a single-stack (Quarkus-only)
# example proving the chapter's thesis: Quarkus REST (RESTEasy Reactive)
# resolves `@RestHeader`/`@RestQuery` parameter bindings at BUILD TIME via
# bytecode generation, not via per-request reflection like classic JAX-RS's
# `@HeaderParam`/`@QueryParam`. That difference is invisible on the wire —
# what IS observable, and what this script asserts, is:
#
#   1. `@RestHeader("X-Tenant")` on GET /tenant: sending the header makes it
#      come back in the response; omitting it falls back to a documented
#      default ("public").
#   2. `@RestQuery("limit")` on GET /bookings/events/export DRIVES the
#      response: different `limit` values change exactly how many NDJSON
#      records stream back, the omitted case uses a documented default, and
#      an oversized value is CLAMPED (DoS guard) rather than honored
#      unbounded.
#   3. The NDJSON export is reactive (Mutiny Multi, not a buffered List) —
#      proven with the same INCREMENTAL-DELIVERY timing technique Ch16's
#      SSE endpoint uses: a second request is read line-by-line through a
#      bash `read` loop piped straight from `curl -N`, timestamping each
#      line as it actually arrives, and the first-line-to-last-line spread
#      is asserted to be consistent with real per-tick delivery rather than
#      a near-zero buffered burst.
#   4. Every streamed record validates against the shared contract's
#      `#/$defs/BookingEvent`.
#
# See README.md for the full explainer and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch22-quarkus"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"
BASE="http://localhost:8102"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

# Must match EventGenerator.java's constants exactly — verify.sh asserts
# against these, it doesn't read them back from the app.
DEFAULT_LIMIT=5
MAX_LIMIT=20
STREAM_INTERVAL_SECONDS=0.2

# The minimum acceptable first-line-to-last-line spread for the timed NDJSON
# run below, in seconds. With TIMING_LIMIT items at STREAM_INTERVAL_SECONDS
# apart, the IDEAL spread is (TIMING_LIMIT-1) * STREAM_INTERVAL_SECONDS =
# 4 * 0.2 = 0.8s. This threshold sits well below that (~62%) to absorb CI
# scheduling jitter and container startup noise, while staying far above
# the near-zero spread a BUFFERED implementation (generate everything
# internally, then flush it all in one burst) would produce.
TIMING_LIMIT=5
MIN_SPREAD_SECONDS=0.5

# ---------------------------------------------------------------------------
# Header/body helpers (lib.sh's assert_header only checks presence; some
# assertions below need header/body VALUES).
# ---------------------------------------------------------------------------

extract_header() {
  local name="$1" file="$2"
  grep -i "^${name}:" "$file" | head -1 | sed -E 's/^[^:]*:[[:space:]]*//' | tr -d '\r\n'
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

wait_for_http "$BASE/q/health" 90

# ---------------------------------------------------------------------------
# Step 3: @RestHeader — zero-reflection header binding.
# ---------------------------------------------------------------------------

echo
echo "=== Step 3: @RestHeader('X-Tenant') on GET /tenant ==="

headers_file="$TMP_DIR/tenant-headers.txt"
body_file="$TMP_DIR/tenant-body.json"

status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
  -H 'X-Tenant: acme-shipping' "$BASE/tenant")"
assert_status 200 "$status" "GET /tenant with X-Tenant header"

content_type="$(extract_header Content-Type "$headers_file")"
[[ "$content_type" == *"application/json"* ]] \
  || fail "GET /tenant: expected Content-Type application/json, got '$content_type'"

tenant_value="$(jq -r '.tenant' "$body_file")"
defaulted_value="$(jq -r '.defaulted' "$body_file")"
[[ "$tenant_value" == "acme-shipping" ]] \
  || fail "GET /tenant with header: expected tenant 'acme-shipping', got '$tenant_value'"
[[ "$defaulted_value" == "false" ]] \
  || fail "GET /tenant with header: expected defaulted=false, got '$defaulted_value'"
echo "lib.sh: ok — @RestHeader reflects explicit X-Tenant value '$tenant_value' (defaulted=$defaulted_value)"

status="$(curl -sS -o "$body_file" -w '%{http_code}' "$BASE/tenant")"
assert_status 200 "$status" "GET /tenant without X-Tenant header"

tenant_value="$(jq -r '.tenant' "$body_file")"
defaulted_value="$(jq -r '.defaulted' "$body_file")"
[[ "$tenant_value" == "public" ]] \
  || fail "GET /tenant without header: expected documented default 'public', got '$tenant_value'"
[[ "$defaulted_value" == "true" ]] \
  || fail "GET /tenant without header: expected defaulted=true, got '$defaulted_value'"
echo "lib.sh: ok — @RestHeader falls back to documented default 'public' when X-Tenant is absent (defaulted=$defaulted_value)"

# ---------------------------------------------------------------------------
# Step 4: @RestQuery('limit') DRIVES the NDJSON export's record count.
# ---------------------------------------------------------------------------

echo
echo "=== Step 4: @RestQuery('limit') on GET /bookings/events/export ==="

ndjson_file="$TMP_DIR/ndjson-body.txt"
frame_file="$TMP_DIR/frame.json"

assert_export_line_count() {
  local query="$1" expected="$2" label="$3"
  local url="$BASE/bookings/events/export${query}"
  local status

  status="$(curl -sS -D "$headers_file" -o "$ndjson_file" -w '%{http_code}' "$url")"
  assert_status 200 "$status" "GET /bookings/events/export$query"

  local content_type
  content_type="$(extract_header Content-Type "$headers_file")"
  [[ "$content_type" == *"application/x-ndjson"* ]] \
    || fail "$label: expected Content-Type application/x-ndjson, got '$content_type'"

  local -a lines
  mapfile -t lines < <(grep . "$ndjson_file")
  [[ "${#lines[@]}" -eq "$expected" ]] \
    || fail "$label: expected $expected NDJSON lines, got ${#lines[@]}"
  echo "lib.sh: ok — $label produced ${#lines[@]} lines (expected $expected)"

  local line
  for line in "${lines[@]}"; do
    echo "$line" > "$frame_file"
    validate_body BookingEvent "$frame_file"
  done
  echo "lib.sh: ok — $label: all ${#lines[@]} lines validate as BookingEvent"
}

# limit=3 and limit=8 produce DIFFERENT counts — proves the query param
# genuinely drives the response rather than being accepted and ignored.
assert_export_line_count "?limit=3" 3 "limit=3"
assert_export_line_count "?limit=8" 8 "limit=8"

# Omitted entirely -> documented default.
assert_export_line_count "" "$DEFAULT_LIMIT" "limit omitted (default)"

# Oversized -> clamped to MAX_LIMIT, never honored unbounded (DoS guard).
assert_export_line_count "?limit=999" "$MAX_LIMIT" "limit=999 (clamped)"

# Zero/negative -> clamped up to 1, never an empty/invalid stream.
assert_export_line_count "?limit=0" 1 "limit=0 (clamped)"

# ---------------------------------------------------------------------------
# Step 5: incremental delivery — prove the NDJSON export is a genuinely
# reactive Multi stream, not a buffered blob. Same technique as Ch16's SSE
# endpoint: read a second request line-by-line through `curl -N` piped into
# a bash `read` loop (no internal buffering), timestamping each line the
# moment it is actually received.
# ---------------------------------------------------------------------------

echo
echo "=== Step 5: proving INCREMENTAL delivery (not buffered) ==="

timed_file="$TMP_DIR/ndjson-timed.txt"
: > "$timed_file"
while IFS= read -r line; do
  # Each NDJSON record is followed by a BLANK line (the record's own
  # trailing "\n" plus the HTTP chunk/line framing) — skip those here
  # rather than timestamp them, so only genuine record arrivals count.
  [[ -z "$line" ]] && continue
  printf '%s|%s\n' "$(date +%s.%N)" "$line" >> "$timed_file"
done < <(curl -sS -N --max-time 8 "$BASE/bookings/events/export?limit=$TIMING_LIMIT")

mapfile -t timed_lines < <(grep . "$timed_file")
[[ "${#timed_lines[@]}" -eq "$TIMING_LIMIT" ]] \
  || fail "timed export: expected $TIMING_LIMIT lines, got ${#timed_lines[@]}"
echo "lib.sh: ok — timed export emitted ${#timed_lines[@]} lines"

first_ts=""
last_ts=""
for row in "${timed_lines[@]}"; do
  ts="${row%%|*}"
  rest="${row#*|}"
  echo "$rest" > "$frame_file"
  validate_body BookingEvent "$frame_file"
  [[ -z "$first_ts" ]] && first_ts="$ts"
  last_ts="$ts"
done
echo "lib.sh: ok — all ${#timed_lines[@]} timed lines validate as BookingEvent"

spread="$(awk -v a="$last_ts" -v b="$first_ts" 'BEGIN { printf "%.3f", a - b }')"
echo "lib.sh: NDJSON timing — first line read at ${first_ts}, last line read at ${last_ts}, spread ${spread}s" >&2
if ! awk_ge "$spread" "$MIN_SPREAD_SECONDS"; then
  fail "NDJSON export: line-to-line spread ${spread}s is below the ${MIN_SPREAD_SECONDS}s floor — these lines look BUFFERED (all arrived in one burst), not delivered incrementally"
fi
echo "lib.sh: ok — NDJSON spread ${spread}s >= ${MIN_SPREAD_SECONDS}s floor — delivery is genuinely incremental"

echo
echo "PASS — Ch22 Quarkus REST in depth: @RestHeader binds and defaults an" \
     "X-Tenant header, @RestQuery('limit') genuinely drives (and clamps) the" \
     "reactive NDJSON export's record count, every exported record validates" \
     "against #/\$defs/BookingEvent, and the export is proven to arrive" \
     "INCREMENTALLY (a first-line-to-last-line spread consistent with real" \
     "per-tick delivery, not a buffered burst)."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
