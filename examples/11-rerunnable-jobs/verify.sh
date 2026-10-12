#!/usr/bin/env bash
# examples/11-rerunnable-jobs/verify.sh
#
# Ch11 rerunnable-jobs example — the reference both-stack implementation of
# a server-owned, rerunnable "manifest-reconcile" job, split into configure
# (the schedule, server-owned) and execute (run records):
#
#   PUT/GET /jobs/manifest-reconcile        — configure/read the schedule
#   POST    /jobs/manifest-reconcile/runs   — "run now" (on-demand execution)
#   GET     /jobs/manifest-reconcile/runs   — list run records
#   GET     /jobs/manifest-reconcile/runs/{runId} — read one run record
#
# Every run-record body from BOTH the Quarkus and the FastAPI stack is
# schema-validated against the shared contract
# (contracts/schemas/shipping.schema.json's Operation, reused as the run
# record shape), not just checked for an HTTP status code. See README.md
# for the lifecycle and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch11-jobs"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

# A syntactically valid but never-issued run id (26 zeros — the Crockford
# alphabet includes '0', so this is a legal ULID shape).
# "op_" prefix (not "run_"): run records reuse #/$defs/Operation's id
# pattern verbatim (^op_[0-9A-HJKMNP-TV-Z]{26}$) — see README.md.
NONEXISTENT_RUN_ID="op_$(printf '0%.0s' $(seq 1 26))"

# The schedule configured on each stack: SHORT and deterministic so CI stays
# bounded (the server's own scheduler is expected to fire within a few
# multiples of this).
JOB_INTERVAL_SECONDS=2

# How long to poll GET .../runs/{id} before giving up on ever seeing
# SUCCEEDED. Each run's trivial "reconcile" work takes
# JobStore.WORK_DELAY_MS / jobs.WORK_DELAY_SECONDS (~0.3s); 10s gives
# generous headroom without letting a genuinely broken stack hang CI.
POLL_TIMEOUT_SECONDS=10
POLL_INTERVAL_SECONDS=1

# How long to wait, after the manual run-now round-trip completes, for the
# server's OWN scheduler to produce at least one additional run on its
# configured interval. Interval + a generous buffer keeps this deterministic
# without over-extending CI wall time.
AUTO_RUN_WAIT_SECONDS=$(( JOB_INTERVAL_SECONDS + 3 ))

# ---------------------------------------------------------------------------
# Header helpers (lib.sh's assert_header only checks presence; the test
# sequence below also needs the VALUE to chase the Location it got back).
# ---------------------------------------------------------------------------

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

wait_for_http "http://localhost:8091/q/health" 90
wait_for_http "http://localhost:8011/health" 60

# ---------------------------------------------------------------------------
# Step 3: drive the configure -> run-now -> poll -> list lifecycle against
# EACH stack, schema-validating every run-record body, and proving the
# job's own scheduler (not just "run now") produces runs too.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local headers_file="$TMP_DIR/${stack}-headers.txt"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- GET the job before it's ever configured -> 404, Problem -------------
  local status
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/jobs/manifest-reconcile")"
  assert_status 404 "$status" "$stack GET /jobs/manifest-reconcile (unconfigured)"
  validate_body Problem "$body_file"

  # -- "run now" before the job is configured -> 404, Problem ---------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' -X POST "$base/jobs/manifest-reconcile/runs")"
  assert_status 404 "$status" "$stack POST .../runs (unconfigured)"
  validate_body Problem "$body_file"
  echo "lib.sh: ok — $stack rejects GET/POST on an unconfigured job with 404 Problem"

  # -- PUT /jobs/manifest-reconcile -> 201 the FIRST time, schedule present -
  local put_payload
  put_payload="{\"enabled\":true,\"intervalSeconds\":${JOB_INTERVAL_SECONDS}}"
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PUT -H 'Content-Type: application/json' -d "$put_payload" "$base/jobs/manifest-reconcile")"
  assert_status 201 "$status" "$stack PUT /jobs/manifest-reconcile (first configure)"

  local def_enabled def_interval
  def_enabled="$(jq -r '.enabled' "$body_file")"
  def_interval="$(jq -r '.intervalSeconds' "$body_file")"
  [[ "$def_enabled" == "true" ]] || fail "$stack job definition: expected enabled=true, got $def_enabled"
  [[ "$def_interval" == "$JOB_INTERVAL_SECONDS" ]] \
    || fail "$stack job definition: expected intervalSeconds=$JOB_INTERVAL_SECONDS, got $def_interval"
  echo "lib.sh: ok — $stack job definition configured with a schedule (enabled=$def_enabled, intervalSeconds=$def_interval)"

  # -- PUT again (same body) -> 200, not 201 (upsert, not re-create) -------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X PUT -H 'Content-Type: application/json' -d "$put_payload" "$base/jobs/manifest-reconcile")"
  assert_status 200 "$status" "$stack PUT /jobs/manifest-reconcile (re-configure)"

  # -- GET /jobs/manifest-reconcile -> 200, schedule still present ---------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/jobs/manifest-reconcile")"
  assert_status 200 "$status" "$stack GET /jobs/manifest-reconcile (configured)"
  def_enabled="$(jq -r '.enabled' "$body_file")"
  [[ "$def_enabled" == "true" ]] || fail "$stack GET job definition: expected enabled=true, got $def_enabled"

  # -- POST .../runs -> 202, Location, a run record (PENDING/RUNNING) ------
  status="$(curl -sS -D "$headers_file" -o "$body_file" -w '%{http_code}' \
    -X POST "$base/jobs/manifest-reconcile/runs")"
  assert_status 202 "$status" "$stack POST .../runs (run now)"
  assert_header Location "$headers_file" "$stack POST .../runs (run now)"
  validate_body Operation "$body_file"

  local run_location run_id run_status
  run_location="$(extract_header Location "$headers_file")"
  run_id="$(jq -r '.id' "$body_file")"
  run_status="$(jq -r '.status' "$body_file")"
  [[ "$run_status" == "PENDING" || "$run_status" == "RUNNING" ]] \
    || fail "$stack run $run_id: expected PENDING or RUNNING immediately after run-now, got $run_status"
  echo "lib.sh: ok — $stack run-now $run_id is $run_status immediately after 202"

  # -- Poll GET .../runs/{id} until SUCCEEDED -------------------------------
  local waited=0 final_status=""
  while (( waited < POLL_TIMEOUT_SECONDS )); do
    status="$(curl -sS -o "$body_file" -w '%{http_code}' "$(resolve_location "$base" "$run_location")")"
    assert_status 200 "$status" "$stack GET .../runs/{id} (polling)"
    validate_body Operation "$body_file"
    run_status="$(jq -r '.status' "$body_file")"
    if [[ "$run_status" == "SUCCEEDED" ]]; then
      final_status="SUCCEEDED"
      break
    fi
    [[ "$run_status" == "FAILED" ]] && fail "$stack run $run_id unexpectedly FAILED"
    sleep "$POLL_INTERVAL_SECONDS"
    waited=$(( waited + POLL_INTERVAL_SECONDS ))
  done
  [[ "$final_status" == "SUCCEEDED" ]] \
    || fail "$stack run $run_id never reached SUCCEEDED within ${POLL_TIMEOUT_SECONDS}s"
  echo "lib.sh: ok — $stack run-now $run_id reached SUCCEEDED within ${waited}s"

  # -- GET .../runs -> 200, array with at least our run-now entry ----------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/jobs/manifest-reconcile/runs")"
  assert_status 200 "$status" "$stack GET .../runs (list)"
  local run_count_before
  run_count_before="$(jq 'length' "$body_file")"
  (( run_count_before >= 1 )) || fail "$stack GET .../runs: expected at least 1 run, got $run_count_before"
  jq -c '.[0]' "$body_file" > "$TMP_DIR/${stack}-run0.json"
  validate_body Operation "$TMP_DIR/${stack}-run0.json"
  echo "lib.sh: ok — $stack GET .../runs lists $run_count_before run(s), newest entry schema-valid"

  # -- GET an unknown run -> 404, Problem -----------------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/jobs/manifest-reconcile/runs/$NONEXISTENT_RUN_ID")"
  assert_status 404 "$status" "$stack GET unknown run"
  validate_body Problem "$body_file"

  # -- The job's OWN scheduler must also produce runs, on its configured
  #    interval, with no further client action ("run now" is an ADDITION
  #    to the schedule, not a replacement for it). -------------------------
  echo "lib.sh: waiting ${AUTO_RUN_WAIT_SECONDS}s for the scheduler (interval ${JOB_INTERVAL_SECONDS}s) to fire on its own ..."
  sleep "$AUTO_RUN_WAIT_SECONDS"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/jobs/manifest-reconcile/runs")"
  assert_status 200 "$status" "$stack GET .../runs (after scheduler wait)"
  local run_count_after
  run_count_after="$(jq 'length' "$body_file")"
  (( run_count_after > run_count_before )) \
    || fail "$stack scheduler produced no additional run in ${AUTO_RUN_WAIT_SECONDS}s (before=$run_count_before, after=$run_count_after)"
  echo "lib.sh: ok — $stack scheduler fired on its own: $run_count_before -> $run_count_after run(s)"

  # -- Every auto-produced run is schema-valid too, and at least one more
  #    reached SUCCEEDED (the ticker's runs go through the same lifecycle). -
  local succeeded_count
  succeeded_count="$(jq '[.[] | select(.status == "SUCCEEDED")] | length' "$body_file")"
  (( succeeded_count >= 1 )) || fail "$stack GET .../runs: expected >=1 SUCCEEDED run, got $succeeded_count"
  jq -c '.[]' "$body_file" | while IFS= read -r run_json; do
    echo "$run_json" > "$TMP_DIR/${stack}-run-each.json"
    validate_body Operation "$TMP_DIR/${stack}-run-each.json"
  done

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8091"
run_stack_tests "python" "http://localhost:8011"

echo
echo "PASS — Ch11 rerunnable-jobs example: Quarkus and FastAPI both produce" \
     "schema-conforming job-definition/run-record bodies for the" \
     "configure -> run-now -> poll -> list lifecycle, AND both stacks'" \
     "own schedulers autonomously produce additional runs on the" \
     "configured interval."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
