#!/usr/bin/env bash
# examples/21-multi-protocol-contracts/verify.sh
#
# Ch21 multi-protocol-contracts anchor — the load-bearing assertion is that
# ONE service, on BOTH stacks, pairs a synchronous REST path with a
# background event-streaming path over the SAME shared schema
# (contracts/schemas/shipping.schema.json). Default `docker compose up`
# brings up only kafka + quarkus + python (no governance tier — see
# README.md for the local-only Apicurio/OpenMetadata profiles). For each
# stack this script:
#   1. proves the validation gate has teeth (validate_response.py --selftest)
#   2. POSTs a booking over REST -> 201 + Location, body vs #/$defs/Booking;
#      GETs the Location -> 200, body vs #/$defs/Booking
#   3. consumes the CloudEvents-enveloped BookingEvent the service publishes
#      to Kafka as a background action, with a BOUNDED timeout, and
#      validates the envelope attributes + `data` vs #/$defs/BookingEvent
#   4. statically confirms shipping.schema.json is $ref'd by BOTH the
#      OpenAPI and the AsyncAPI documents (the "one schema, two protocol
#      contracts" claim)
#   5. structurally validates contracts/arazzo/booking-workflow.yaml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch21-contracts"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"
TOPIC="shipping.bookings.lifecycle"

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

# ---------------------------------------------------------------------------
# Step 1: prove the validation gate has teeth before trusting it for
# anything below.
# ---------------------------------------------------------------------------

ensure_verify_venv

echo "=== Step 1: validate_response.py --selftest ==="
"$LGTM_VERIFY_VENV_DIR/bin/python" -I "$VALIDATE_RESPONSE_PY" --selftest

# ---------------------------------------------------------------------------
# Step 2: static contract checks — fast, no services needed. Prove the
# "one schema, two protocol contracts" claim and that the Arazzo workflow
# document is structurally sound, BEFORE spending time on docker compose.
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
# Step 3: bring the stack up (kafka + quarkus + python only — governance
# tier profiles are NOT started by a plain `compose up`).
# ---------------------------------------------------------------------------

echo
echo "=== Step 3: docker compose up (kafka + quarkus + python) ==="
compose_up "$COMPOSE_FILE" "$PROJECT"

wait_for_http "http://localhost:8101/q/health" 90
wait_for_http "http://localhost:8021/health" 60

# ---------------------------------------------------------------------------
# Step 4: for each stack — REST create/read, then consume + validate the
# background CloudEvents publish. EVENTS_SO_FAR tracks the running count of
# events produced across both stacks so each stack's bounded
# `--max-messages` consume reads exactly "everything published up to and
# including this stack's event" from a FRESH consumer group reading
# `--from-beginning` — deterministic and bounded, no open-ended waiting.
# ---------------------------------------------------------------------------

EVENTS_SO_FAR=0

check_event() {
  local stack="$1" booking_id="$2"
  EVENTS_SO_FAR=$((EVENTS_SO_FAR + 1))

  local group="ch21-verify-${stack}-$$"
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
  echo "=== Step 4: verifying stack '$stack' at $base ==="

  local create_payload
  create_payload='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

  local status
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' -d "$create_payload" "$base/bookings")"
  assert_status 201 "$status" "$stack POST /bookings"
  assert_header Location "$headers_file" "$stack POST /bookings"
  validate_body Booking "$body_file"

  local location booking_id
  location="$(extract_header Location "$headers_file")"
  booking_id="$(jq -r '.id' "$body_file")"
  echo "lib.sh: ok — $stack POST /bookings created $booking_id"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$(resolve_location "$base" "$location")")"
  assert_status 200 "$status" "$stack GET Location"
  validate_body Booking "$body_file"

  check_event "$stack" "$booking_id"

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8101"
run_stack_tests "python" "http://localhost:8021"

echo
echo "PASS — Ch21 multi-protocol-contracts anchor: both Quarkus and FastAPI" \
     "pair a synchronous REST path (Booking vs #/\$defs/Booking) with a" \
     "background event-streaming path (a CloudEvents-enveloped BookingEvent" \
     "on $TOPIC, vs #/\$defs/BookingEvent) over the SAME shared schema; both" \
     "contracts/openapi/shipping-api.yaml and" \
     "contracts/asyncapi/shipping-events.yaml \$ref it, and the Arazzo" \
     "bookAndConfirm workflow is structurally sound."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
