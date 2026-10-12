# examples/_lib

Shared verification harness for every hands-on example in `examples/`. Each
example's `verify.sh` sources `lib.sh` instead of reinventing compose
lifecycle, HTTP polling, and response validation.

`examples/` is excluded from the Jekyll build (see `_config.yml`), so nothing
here affects the site.

## What it does

1. **Brings a docker compose stack up/down safely** — unique project name
   per example (so a shared CI runner never leaks containers between
   examples), and an `EXIT` trap so the stack is always torn down even if a
   later assertion fails.
2. **Hits endpoints** — polls until healthy, asserts status codes and
   headers.
3. **Validates response BODIES against the shared contract schema** —
   `contracts/schemas/shipping.schema.json` (JSON Schema 2020-12). This
   checks payload *semantics* (field shapes, enums, required properties,
   `additionalProperties: false`), not just "did we get a 200".

## Files

- `lib.sh` — bash functions a `verify.sh` sources directly.
- `validate_response.py` — stdlib + `jsonschema` + `referencing` CLI that
  validates a JSON body against any `#/$defs/<TypeName>` in the shared
  schema. Run through a dedicated venv under `python3 -I` (isolated mode).
- `.venv/` (git-ignored, created on first use) — the venv `lib.sh` builds
  and caches so `verify.sh` needs no CI YAML change and no pre-installed
  Python packages.

## Using it from an example's `verify.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../_lib/lib.sh"

# Unique per example so parallel/shared CI runs never collide.
PROJECT="rest-ch07-pagination"
compose_up "$SCRIPT_DIR/docker-compose.yml" "$PROJECT"
# compose_down now runs automatically on EXIT — no cleanup code needed here.

wait_for_http "http://localhost:8080/health"

status_and_body="$(curl -sS -o /tmp/body.json -w '%{http_code}' \
  http://localhost:8080/bookings/bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4)"
assert_status 200 "$status_and_body" "GET booking"
validate_body Booking /tmp/body.json
```

Available functions: `compose_up`, `compose_down`, `wait_for_http`,
`assert_status`, `assert_header`, `validate_body`, `ensure_verify_venv`.
`REPO_ROOT` is also exported, resolved from `lib.sh`'s own location so paths
to `contracts/` and `examples/_lib/` work regardless of the calling
example's current directory.

## The drift probe

`validate_response.py --selftest` is a self-contained, app-free proof that
the gate has teeth: it builds a known-good `Booking` body and asserts it
validates, then tampers it three ways (an unexpected field, an
out-of-enum `status`, a malformed `id`) and asserts each tampered variant is
*rejected*. It also validates an `Operation` body with `completedAt: null`
to catch a validator/schema setup that mishandles JSON Schema 2020-12
nullable typing (`type: ["string", "null"]`).

Run it any time with no example app required:

```bash
python3 -m venv /tmp/vlib
/tmp/vlib/bin/pip install -q 'jsonschema>=4.18' referencing
/tmp/vlib/bin/python -I examples/_lib/validate_response.py --selftest
```

If this selftest ever starts passing on a tampered body, the validation
wiring itself is broken — independent of whether any particular example's
app is behaving. Every example's `verify.sh` inherits the same wiring via
`lib.sh`, so this one script is the regression guard for the whole harness.
