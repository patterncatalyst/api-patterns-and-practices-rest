#!/usr/bin/env bash
# examples/00-prerequisites/verify.sh
#
# Ch0 boot skeleton — proves the toolchain (Quarkus + FastAPI, both on
# UBI 10, both fronted by Postgres) builds and boots over Docker Compose.
# Health only: the real contract-driven API lands in Ch4. The LGTM
# observability profile is intentionally NOT started here — see compose.yaml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch00-prereq"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

ensure_verify_venv

compose_up "$COMPOSE_FILE" "$PROJECT"

wait_for_http "http://localhost:8080/q/health" 90
wait_for_http "http://localhost:8000/health" 60

quarkus_status="$(curl -sS -o /dev/null -w '%{http_code}' http://localhost:8080/q/health)"
assert_status 200 "$quarkus_status" "Quarkus /q/health"

python_status="$(curl -sS -o /dev/null -w '%{http_code}' http://localhost:8000/health)"
assert_status 200 "$python_status" "FastAPI /health"

echo
echo "PASS — Ch0 boot skeleton: Quarkus (HTTP $quarkus_status) and FastAPI (HTTP $python_status) are both up on UBI 10, observability profile untouched."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders,
# per the task spec); compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
