#!/usr/bin/env bash
# examples/19-http2-http3/verify.sh
#
# Ch19 REST over HTTP/2 & HTTP/3 anchor — the load-bearing assertion is the
# NEGOTIATED WIRE PROTOCOL, not just a 200. For each stack this fires one
# request forcing HTTP/1.1 and one forcing HTTP/2 cleartext ("h2c", via
# curl's prior-knowledge mode — no TLS/ALPN available in this compose
# stack) and asserts curl's own `%{http_version}` reports `1.1` and `2`
# respectively, with a 200 both times. That's the thing a server that
# quietly stopped speaking HTTP/2 would fail at the protocol-negotiation
# level even though the response body and status code look fine. See
# README.md for the h1-vs-h2 explainer, the HTTP/3 local-only instructions
# (deliberately NOT exercised here), and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch19-h2"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

fail() {
  echo "lib.sh: FAIL — $*" >&2
  return 1
}

# ---------------------------------------------------------------------------
# Step 1: bring the stack up.
# ---------------------------------------------------------------------------

echo "=== Step 1: docker compose up ==="
compose_up "$COMPOSE_FILE" "$PROJECT"

wait_for_http "http://localhost:8098/q/health" 90
wait_for_http "http://localhost:8018/health" 60

# ---------------------------------------------------------------------------
# Step 2: for each stack, confirm curl negotiates HTTP/1.1 when asked for
# HTTP/1.1, and HTTP/2 (h2c, prior knowledge) when asked for HTTP/2.
# ---------------------------------------------------------------------------

check_protocol() {
  local stack="$1" base="$2" curl_flag="$3" expected_version="$4"
  local out status version

  out="$(curl -sS "$curl_flag" -o /dev/null -w '%{http_code} %{http_version}' "$base/")"
  status="${out%% *}"
  version="${out#* }"

  assert_status 200 "$status" "$stack $curl_flag GET /"

  if [[ "$version" != "$expected_version" ]]; then
    fail "$stack $curl_flag GET /: expected http_version '$expected_version', got '$version'"
  fi
  echo "lib.sh: ok — $stack $curl_flag negotiated HTTP/$version"
}

echo
echo "=== Step 2: HTTP/1.1 and HTTP/2 (h2c) negotiation ==="

check_protocol "quarkus" "http://localhost:8098" "--http1.1" "1.1"
check_protocol "quarkus" "http://localhost:8098" "--http2-prior-knowledge" "2"

check_protocol "python" "http://localhost:8018" "--http1.1" "1.1"
check_protocol "python" "http://localhost:8018" "--http2-prior-knowledge" "2"

echo
echo "PASS — Ch19 HTTP/2 & HTTP/3 anchor: both Quarkus (Vert.x HTTP, h2c" \
     "on by default) and FastAPI (served by Hypercorn, not uvicorn) answer" \
     "HTTP/1.1 requests as HTTP/1.1 and HTTP/2-prior-knowledge requests as" \
     "HTTP/2. HTTP/3/QUIC is tier-gated out of this script — see README.md."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
