#!/usr/bin/env bash
# examples/18-concurrency/verify.sh
#
# Ch18 back-end I/O concurrency anchor — the load-bearing step is MEASURED
# concurrency, not just a 200 from a single request. This fires K concurrent
# requests at each stack's `GET /io/slow?ms=200` (the idiomatic non-blocking
# implementation — Mutiny `Uni` + a Vert.x timer on Quarkus, `async def` +
# `await asyncio.sleep` on FastAPI) and asserts the whole batch comes back
# well under the SERIAL time it would take if requests were queued one
# after another (K * 200ms). That's the one thing a naive thread-per-request
# or synchronous implementation would fail at the wall-clock level, even
# though every individual response is a perfectly valid 200. See README.md
# for the full explainer and a documented drift probe (point this same
# assertion at `/io/slow-blocking` with the worker pool capped to 1, and
# watch it fail).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch18-conc"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

# K concurrent requests, each simulating a 200ms downstream I/O call. Serial
# time for K requests at MS_PER_CALL each would be K * MS_PER_CALL = 4.0s.
# The concurrent implementations on both stacks should finish the whole
# batch in roughly one call's worth of wall time (~0.2-0.4s locally); the
# bound below is set generously below the 4s serial floor (well under half)
# so it stays robust to CI scheduling jitter and container CPU contention
# while still being far enough below 4s to clearly discriminate concurrent
# from serial execution.
K=20
MS_PER_CALL=200
MAX_CONCURRENT_SECONDS=2.0

awk_lt() {
  # True (exit 0) iff $1 < $2, both floating-point strings.
  awk -v a="$1" -v b="$2" 'BEGIN { exit !(a < b) }'
}

# ---------------------------------------------------------------------------
# Step 1: bring the stack up.
# ---------------------------------------------------------------------------

ensure_verify_venv

echo "=== Step 1: docker compose up ==="
compose_up "$COMPOSE_FILE" "$PROJECT"

wait_for_http "http://localhost:8097/q/health" 90
wait_for_http "http://localhost:8017/health" 60

# ---------------------------------------------------------------------------
# Step 2: fire K concurrent requests at each stack's /io/slow endpoint and
# measure total wall-clock time for the whole batch.
# ---------------------------------------------------------------------------

run_concurrency_test() {
  local stack="$1" base="$2"
  local endpoint="${3:-/io/slow}"
  local codes_dir="$TMP_DIR/${stack}-codes"
  mkdir -p "$codes_dir"

  echo
  echo "=== Step 2: firing $K concurrent requests at $stack ($base$endpoint?ms=$MS_PER_CALL) ==="

  local start_ts end_ts elapsed
  start_ts="$(date +%s.%N)"

  local i
  for ((i = 0; i < K; i++)); do
    (
      code="$(curl -sS -o /dev/null -w '%{http_code}' "$base$endpoint?ms=$MS_PER_CALL")"
      echo "$code" > "$codes_dir/$i"
    ) &
  done
  wait

  end_ts="$(date +%s.%N)"
  elapsed="$(awk -v a="$end_ts" -v b="$start_ts" 'BEGIN { printf "%.3f", a - b }')"

  # -- every request returned 200 ------------------------------------------
  local fail_count=0 code
  for ((i = 0; i < K; i++)); do
    code="$(cat "$codes_dir/$i" 2>/dev/null || echo "MISSING")"
    if [[ "$code" != "200" ]]; then
      echo "lib.sh: FAIL — $stack request #$i returned '$code', expected 200" >&2
      fail_count=$((fail_count + 1))
    fi
  done
  if (( fail_count > 0 )); then
    fail "$stack: $fail_count of $K concurrent requests did not return 200"
  fi
  echo "lib.sh: ok — $stack all $K concurrent requests returned 200"

  # -- total wall-clock time is well under the serial floor ----------------
  echo "lib.sh: $stack batch of $K requests completed in ${elapsed}s" \
       "(serial floor would be $(awk -v k="$K" -v ms="$MS_PER_CALL" 'BEGIN { printf "%.1f", k * ms / 1000 }')s)"
  if ! awk_lt "$elapsed" "$MAX_CONCURRENT_SECONDS"; then
    fail "$stack: $K concurrent requests took ${elapsed}s — expected under ${MAX_CONCURRENT_SECONDS}s." \
         "This looks SERIALIZED (one request handled at a time), not concurrent."
  fi
  echo "lib.sh: ok — $stack ${elapsed}s < ${MAX_CONCURRENT_SECONDS}s bound — requests ran CONCURRENTLY, not serialized"

  echo "=== $stack: concurrency assertions passed ==="
}

fail() {
  echo "lib.sh: FAIL — $*" >&2
  return 1
}

run_concurrency_test "quarkus" "http://localhost:8097"
run_concurrency_test "python" "http://localhost:8017"

echo
echo "PASS — Ch18 back-end I/O concurrency anchor: both Quarkus (Mutiny Uni" \
     "+ non-blocking delay) and FastAPI (async def + await asyncio.sleep)" \
     "served $K concurrent /io/slow calls well under the $(awk -v k="$K" -v ms="$MS_PER_CALL" 'BEGIN { printf "%.1f", k * ms / 1000 }')s serial floor."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
