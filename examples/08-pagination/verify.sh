#!/usr/bin/env bash
# examples/08-pagination/verify.sh
#
# Ch8 filtering, projection & pagination — extends the Ch4 contract-first
# Booking + Cargo resource model with three pagination strategies (offset,
# keyset/cursor, seek) plus sparse fieldset projection on GET /bookings.
# Drives the same scenario against BOTH the Quarkus and the FastAPI stack,
# schema-validating every non-projected response body against
# contracts/schemas/shipping.schema.json. See README.md for the strategy
# comparison, the limit-cap rationale, and a documented drift probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../_lib/lib.sh
source "$SCRIPT_DIR/../_lib/lib.sh"

PROJECT="ch08-page"
COMPOSE_FILE="$SCRIPT_DIR/compose.yaml"

# Number of bookings to seed per stack before exercising the pagination
# strategies. Small enough to keep the keyset walk short, large enough that
# limit=3 needs 3 pages and offset=3/after_id leave a non-trivial remainder.
SEED_COUNT=7

# DoS-guard ceiling asserted against `page.limit` for the limit-cap test —
# must match `#/$defs/PageMeta.limit`'s `maximum` in the shared schema and
# each stack's MAX_LIMIT/_MAX_LIMIT constant.
MAX_LIMIT=100

TMP_DIR="$(mktemp -d)"
cleanup_tmp() {
  rm -rf "$TMP_DIR"
}
trap cleanup_tmp EXIT

CREATE_PAYLOAD='{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":500,"volumeM3":1.5},"hazardous":false}],"requestedPickup":"2026-02-01"}'

fail() {
  echo "lib.sh: FAIL — $*" >&2
  return 1
}

# arrays_equal_ordered <name-for-errors> <expected-list...> -- <actual-list...>
# Compares two bash arrays element-for-element, in order. Pass the expected
# elements, then a literal "--", then the actual elements.
arrays_equal_ordered() {
  local context="$1"; shift
  local -a expected=()
  while [[ "$1" != "--" ]]; do
    expected+=("$1"); shift
  done
  shift # consume the "--"
  local -a actual=("$@")

  if [[ "${#expected[@]}" -ne "${#actual[@]}" ]]; then
    fail "$context: expected ${#expected[@]} items (${expected[*]:-<none>}), got ${#actual[@]} (${actual[*]:-<none>})"
    return 1
  fi
  local i
  for (( i=0; i<${#expected[@]}; i++ )); do
    if [[ "${expected[$i]}" != "${actual[$i]}" ]]; then
      fail "$context: item $i differs — expected '${expected[$i]}', got '${actual[$i]}' (expected=[${expected[*]}] actual=[${actual[*]}])"
      return 1
    fi
  done
  echo "lib.sh: ok — $context: ${#actual[@]} items matched in order" >&2
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

wait_for_http "http://localhost:8088/q/health" 90
wait_for_http "http://localhost:8008/health" 60

# ---------------------------------------------------------------------------
# Step 3: seed SEED_COUNT bookings, then drive offset / keyset-cursor / seek
# pagination, field projection, and the limit-cap DoS guard against EACH
# stack.
# ---------------------------------------------------------------------------

run_stack_tests() {
  local stack="$1" base="$2"
  local body_file="$TMP_DIR/${stack}-body.json"

  echo
  echo "=== Step 3: verifying stack '$stack' at $base ==="

  # -- Seed SEED_COUNT bookings ---------------------------------------------
  local -a seeded_ids=()
  local i
  for (( i=1; i<=SEED_COUNT; i++ )); do
    local status
    status="$(curl -sS -o "$body_file" -w '%{http_code}' \
      -X POST -H 'Content-Type: application/json' -d "$CREATE_PAYLOAD" "$base/bookings")"
    assert_status 201 "$status" "$stack seed booking $i/$SEED_COUNT"
    seeded_ids+=("$(jq -r '.id' "$body_file")")
  done
  echo "lib.sh: ok — $stack seeded $SEED_COUNT bookings" >&2

  # -- Baseline: default GET /bookings (limit default 20 >= SEED_COUNT)
  #    returns ALL bookings in a single page, sorted ascending by id. This
  #    is the ground truth every pagination assertion below is checked
  #    against, rather than assuming seed order == id order (ULIDs minted
  #    within the same millisecond are NOT guaranteed to sort in creation
  #    order — only the server's own sorted view is authoritative). --------
  local status
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings")"
  assert_status 200 "$status" "$stack GET /bookings (baseline)"
  validate_body BookingCollection "$body_file"

  local baseline_cursor
  baseline_cursor="$(jq -r '.page.nextCursor' "$body_file")"
  [[ "$baseline_cursor" == "null" ]] || fail "$stack baseline GET /bookings: expected a single page (nextCursor null) for $SEED_COUNT<=20 items, got '$baseline_cursor'"

  local -a sorted_ids=()
  mapfile -t sorted_ids < <(jq -r '.items[].id' "$body_file")
  [[ "${#sorted_ids[@]}" -eq "$SEED_COUNT" ]] || fail "$stack baseline GET /bookings: returned ${#sorted_ids[@]} items, expected $SEED_COUNT"

  local seeded_sorted actual_sorted
  seeded_sorted="$(printf '%s\n' "${seeded_ids[@]}" | sort)"
  actual_sorted="$(printf '%s\n' "${sorted_ids[@]}" | sort)"
  [[ "$seeded_sorted" == "$actual_sorted" ]] || fail "$stack baseline GET /bookings: item id SET differs from the $SEED_COUNT seeded ids"
  echo "lib.sh: ok — $stack baseline returns exactly the $SEED_COUNT seeded ids" >&2

  # -- Keyset/cursor walk: limit=3, follow page.nextCursor until null -------
  local -a walked_ids=()
  local cursor="" page_num=0 url
  while :; do
    page_num=$((page_num + 1))
    if [[ "$page_num" -gt $(( SEED_COUNT + 5 )) ]]; then
      fail "$stack keyset walk did not terminate after $page_num pages (possible infinite loop / repeating cursor)"
      break
    fi
    if [[ -z "$cursor" ]]; then
      url="$base/bookings?limit=3"
    else
      url="$base/bookings?limit=3&cursor=$cursor"
    fi
    status="$(curl -sS -o "$body_file" -w '%{http_code}' "$url")"
    assert_status 200 "$status" "$stack keyset page $page_num"
    validate_body BookingCollection "$body_file"

    local -a page_ids=()
    mapfile -t page_ids < <(jq -r '.items[].id' "$body_file")
    walked_ids+=("${page_ids[@]}")

    cursor="$(jq -r '.page.nextCursor' "$body_file")"
    if [[ "$cursor" == "null" ]]; then
      break
    fi
  done

  # No dupes, no gaps: the walked id LIST (order-sensitive) must equal the
  # baseline sorted id list exactly.
  arrays_equal_ordered "$stack keyset walk (limit=3, $page_num pages)" "${sorted_ids[@]}" -- "${walked_ids[@]}"

  # Explicit duplicate check (belt-and-suspenders beyond the ordered
  # comparison above — a dup AND a matching gap could in principle cancel
  # out the count, though not the order check).
  local walked_unique_count
  walked_unique_count="$(printf '%s\n' "${walked_ids[@]}" | sort -u | wc -l)"
  [[ "$walked_unique_count" -eq "${#walked_ids[@]}" ]] || fail "$stack keyset walk produced duplicate ids (collected ${#walked_ids[@]}, ${walked_unique_count} unique)"

  # -- Offset pagination: limit=3&offset=3 -----------------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings?limit=3&offset=3")"
  assert_status 200 "$status" "$stack offset pagination"
  validate_body BookingCollection "$body_file"
  local -a offset_ids=()
  mapfile -t offset_ids < <(jq -r '.items[].id' "$body_file")
  arrays_equal_ordered "$stack offset pagination (limit=3,offset=3)" "${sorted_ids[@]:3:3}" -- "${offset_ids[@]}"

  # -- Seek pagination: after_id=<first id>&limit=2 --------------------------
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings?after_id=${sorted_ids[0]}&limit=2")"
  assert_status 200 "$status" "$stack seek pagination"
  validate_body BookingCollection "$body_file"
  local -a seek_ids=()
  mapfile -t seek_ids < <(jq -r '.items[].id' "$body_file")
  arrays_equal_ordered "$stack seek pagination (after_id=${sorted_ids[0]},limit=2)" "${sorted_ids[@]:1:2}" -- "${seek_ids[@]}"

  # -- Field projection: fields=id,status ------------------------------------
  # NOT validate_body BookingCollection — a projected item generally fails
  # the full Booking schema (missing required properties like status/
  # origin/destination/cargo/createdAt if they weren't requested), by
  # design. Assert the field subset directly instead.
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings?fields=id,status")"
  assert_status 200 "$status" "$stack field projection"

  local projection_item_count
  projection_item_count="$(jq -r '.items | length' "$body_file")"
  [[ "$projection_item_count" -eq "$SEED_COUNT" ]] || fail "$stack field projection: expected $SEED_COUNT items, got $projection_item_count"

  local extra_keys
  extra_keys="$(jq -r '[.items[] | keys[] | select(. != "id" and . != "status")] | unique | join(",")' "$body_file")"
  [[ -z "$extra_keys" ]] || fail "$stack field projection: unexpected key(s) beyond id,status present: $extra_keys"

  local has_origin has_cargo
  has_origin="$(jq -r '[.items[] | has("origin")] | any' "$body_file")"
  has_cargo="$(jq -r '[.items[] | has("cargo")] | any' "$body_file")"
  [[ "$has_origin" == "false" ]] || fail "$stack field projection: 'origin' still present in a projected item"
  [[ "$has_cargo" == "false" ]] || fail "$stack field projection: 'cargo' still present in a projected item"

  local missing_id missing_status
  missing_id="$(jq -r '[.items[] | has("id")] | all | not' "$body_file")"
  missing_status="$(jq -r '[.items[] | has("status")] | all | not' "$body_file")"
  [[ "$missing_id" == "false" ]] || fail "$stack field projection: an item is missing 'id' (must always be included)"
  [[ "$missing_status" == "false" ]] || fail "$stack field projection: an item is missing requested field 'status'"
  echo "lib.sh: ok — $stack field projection returns only {id,status} per item" >&2

  # -- Limit cap (DoS guard): limit=1000 -> page.limit clamped to MAX_LIMIT --
  status="$(curl -sS -o "$body_file" -w '%{http_code}' "$base/bookings?limit=1000")"
  assert_status 200 "$status" "$stack limit cap"
  validate_body BookingCollection "$body_file"
  local returned_limit
  returned_limit="$(jq -r '.page.limit' "$body_file")"
  [[ "$returned_limit" -le "$MAX_LIMIT" ]] || fail "$stack limit cap: requested limit=1000 but page.limit=$returned_limit (expected <= $MAX_LIMIT — the cap was NOT enforced)"
  echo "lib.sh: ok — $stack limit=1000 clamped to page.limit=$returned_limit (<= $MAX_LIMIT)" >&2

  echo "=== $stack: all assertions passed ==="
}

run_stack_tests "quarkus" "http://localhost:8088"
run_stack_tests "python" "http://localhost:8008"

echo
echo "PASS — Ch8 filtering, projection & pagination: Quarkus and FastAPI" \
     "both produce correct offset/keyset-cursor/seek pagination, correct" \
     "sparse-fieldset projection, and a correctly clamped limit cap on" \
     "GET /bookings."

# Explicit teardown in addition to lib.sh's EXIT trap (belt-and-suspenders);
# compose_down is idempotent/safe to call twice.
compose_down "$COMPOSE_FILE" "$PROJECT"
