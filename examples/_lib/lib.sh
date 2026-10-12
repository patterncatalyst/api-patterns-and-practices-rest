#!/usr/bin/env bash
# examples/_lib/lib.sh
#
# Shared verification harness for every hands-on example's verify.sh.
# Source this file, then use the functions below to bring up the example's
# docker compose stack, poll endpoints, and validate response BODIES against
# the shared contract schema (contracts/schemas/shipping.schema.json) — not
# just HTTP status codes.
#
# Usage (from an example's verify.sh):
#
#   #!/usr/bin/env bash
#   set -euo pipefail
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   # shellcheck source=../_lib/lib.sh
#   source "$SCRIPT_DIR/../_lib/lib.sh"
#
#   PROJECT="rest-ch07-pagination"   # unique per example, for CI isolation
#   compose_up "$SCRIPT_DIR/docker-compose.yml" "$PROJECT"
#
#   wait_for_http "http://localhost:8080/health"
#
#   body="$(curl -sS http://localhost:8080/bookings/bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4)"
#   validate_body Booking <<<"$body"
#
# compose_down runs automatically on EXIT via a trap registered by
# compose_up — no example needs its own cleanup trap.
#
# This file must stay bash -n clean: scripts/validate.py runs `bash -n` on
# every *.sh in the repo as part of `python3 -I scripts/validate.py`.

set -euo pipefail

# ---------------------------------------------------------------------------
# Path resolution — works regardless of the calling example's cwd.
# ---------------------------------------------------------------------------

# This file lives at <REPO_ROOT>/examples/_lib/lib.sh
LGTM_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$LGTM_LIB_DIR/../.." && pwd)"
export REPO_ROOT

VALIDATE_RESPONSE_PY="$LGTM_LIB_DIR/validate_response.py"
SHIPPING_SCHEMA="$REPO_ROOT/contracts/schemas/shipping.schema.json"

if [[ ! -f "$VALIDATE_RESPONSE_PY" ]]; then
  echo "lib.sh: cannot find validate_response.py at $VALIDATE_RESPONSE_PY" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Self-contained Python: build (or reuse) a venv with the validator's deps,
# so verify.sh needs no CI YAML change / pre-installed Python packages.
# ---------------------------------------------------------------------------

# Shared across all examples, cached across runs. Override with
# LGTM_VERIFY_VENV_DIR if a caller wants an isolated/ephemeral venv (e.g. a
# read-only checkout) — falls back to a per-invocation dir under TMPDIR.
LGTM_VERIFY_VENV_DIR="${LGTM_VERIFY_VENV_DIR:-$LGTM_LIB_DIR/.venv}"
LGTM_VERIFY_VENV_MARKER="$LGTM_VERIFY_VENV_DIR/.deps-installed"

_lib_venv_python() {
  echo "$LGTM_VERIFY_VENV_DIR/bin/python"
}

# Create the venv and install deps if not already present/cached. Safe to
# call repeatedly; a no-op once the marker file exists.
ensure_verify_venv() {
  local py
  py="$(_lib_venv_python)"

  if [[ -x "$py" && -f "$LGTM_VERIFY_VENV_MARKER" ]]; then
    return 0
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "lib.sh: python3 is required but not found on PATH" >&2
    return 1
  fi

  echo "lib.sh: creating verification venv at $LGTM_VERIFY_VENV_DIR ..." >&2
  mkdir -p "$(dirname "$LGTM_VERIFY_VENV_DIR")"
  if [[ ! -d "$LGTM_VERIFY_VENV_DIR" ]]; then
    python3 -m venv "$LGTM_VERIFY_VENV_DIR"
  fi

  "$py" -m pip install --quiet --upgrade pip
  "$py" -m pip install --quiet 'jsonschema>=4.18' referencing
  touch "$LGTM_VERIFY_VENV_MARKER"
}

# ---------------------------------------------------------------------------
# Docker compose lifecycle
# ---------------------------------------------------------------------------

_LIB_COMPOSE_FILE=""
_LIB_COMPOSE_PROJECT=""

# compose_up <compose-file> <project-name>
#
# Brings the stack up with docker compose (v2 plugin). Registers an EXIT
# trap so the stack is always torn down, even if later steps fail.
compose_up() {
  local compose_file="$1"
  local project="$2"

  if [[ ! -f "$compose_file" ]]; then
    echo "lib.sh: compose file not found: $compose_file" >&2
    return 1
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "lib.sh: docker is required but not found on PATH" >&2
    return 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "lib.sh: 'docker compose' (v2 plugin) is required; legacy docker-compose is not supported" >&2
    return 1
  fi

  _LIB_COMPOSE_FILE="$compose_file"
  _LIB_COMPOSE_PROJECT="$project"

  echo "lib.sh: docker compose -p $project up -d --build" >&2
  docker compose -p "$project" -f "$compose_file" up -d --build

  # Register teardown AFTER a successful up, so a failed `up` doesn't try to
  # tear down a stack that (partially) isn't there — compose_down is a no-op
  # against a missing/partial project either way, but this keeps intent
  # explicit and matches the spec: "register after up".
  trap 'compose_down "$_LIB_COMPOSE_FILE" "$_LIB_COMPOSE_PROJECT"' EXIT
}

# compose_down <compose-file> <project-name>
#
# Tears the stack down, including volumes and orphaned containers, so a
# shared CI runner never leaks containers between examples.
compose_down() {
  local compose_file="$1"
  local project="$2"

  if [[ -z "$project" ]]; then
    return 0
  fi

  echo "lib.sh: docker compose -p $project down -v --remove-orphans" >&2
  docker compose -p "$project" -f "$compose_file" down -v --remove-orphans || true
}

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

# wait_for_http <url> [timeout_secs]
#
# Polls <url> until it returns a 2xx status, or fails loudly after
# timeout_secs (default 60).
wait_for_http() {
  local url="$1"
  local timeout="${2:-60}"
  local waited=0
  local interval=2
  local code

  echo "lib.sh: waiting for $url (timeout ${timeout}s) ..." >&2
  while (( waited < timeout )); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" || echo "000")"
    if [[ "$code" =~ ^2[0-9][0-9]$ ]]; then
      echo "lib.sh: $url is up (HTTP $code) after ${waited}s" >&2
      return 0
    fi
    sleep "$interval"
    waited=$(( waited + interval ))
  done

  echo "lib.sh: FAIL — $url did not become healthy within ${timeout}s (last HTTP code: ${code:-none})" >&2
  return 1
}

# assert_status <expected> <actual> <context>
assert_status() {
  local expected="$1"
  local actual="$2"
  local context="${3:-}"

  if [[ "$expected" != "$actual" ]]; then
    echo "lib.sh: FAIL — ${context:-status check}: expected HTTP $expected, got $actual" >&2
    return 1
  fi
  echo "lib.sh: ok — ${context:-status check}: HTTP $actual" >&2
}

# assert_header <header-name> <response-headers-file-or-string> <context>
#
# Case-insensitive check that <header-name> is present in the given raw
# headers (either a path to a saved headers file, e.g. `curl -D -`, or the
# headers text passed directly as a string).
assert_header() {
  local header_name="$1"
  local headers_input="$2"
  local context="${3:-}"
  local headers_text

  if [[ -f "$headers_input" ]]; then
    headers_text="$(cat "$headers_input")"
  else
    headers_text="$headers_input"
  fi

  if ! grep -qi "^${header_name}:" <<<"$headers_text"; then
    echo "lib.sh: FAIL — ${context:-header check}: missing '$header_name' header" >&2
    return 1
  fi
  echo "lib.sh: ok — ${context:-header check}: '$header_name' header present" >&2
}

# ---------------------------------------------------------------------------
# Contract/body validation
# ---------------------------------------------------------------------------

# validate_body <TypeName> <body-file-or-stdin>
#
# Validates a JSON body against #/$defs/<TypeName> in the shared contract
# schema. Pass a file path as the 2nd arg, or pipe the body in on stdin:
#
#   validate_body Booking response.json
#   curl -sS "$url" | validate_body Booking
validate_body() {
  local type_name="$1"
  local body_arg="${2:-}"

  ensure_verify_venv
  local py
  py="$(_lib_venv_python)"

  local rc=0
  if [[ -n "$body_arg" ]]; then
    "$py" -I "$VALIDATE_RESPONSE_PY" "$type_name" "$body_arg" || rc=$?
  else
    "$py" -I "$VALIDATE_RESPONSE_PY" "$type_name" || rc=$?
  fi

  if [[ "$rc" -ne 0 ]]; then
    echo "lib.sh: FAIL — body does not conform to #/\$defs/$type_name" >&2
    return "$rc"
  fi
}
