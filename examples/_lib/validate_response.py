#!/usr/bin/env python3
"""Validate a JSON response body against the shared shipping contract schema.

Every hands-on example's `verify.sh` shells out to this script (via the venv
python built by `lib.sh`) to assert payload *semantics*, not just HTTP status
codes, against `contracts/schemas/shipping.schema.json` (JSON Schema
2020-12). It reuses the exact load/registry pattern from
`scripts/validate_schemas.py` so `$ref` resolution inside the shared schema
works the same way everywhere in the repo.

Usage:
    validate_response.py <TypeName> [path-to-json]
    cat body.json | validate_response.py <TypeName>

    <TypeName> is any key under the schema's top-level `$defs`, e.g.
    Booking, BookingCollection, Cargo, Operation, Problem, Money, Location,
    BookingEvent.

Exit codes:
    0  body validates against #/$defs/<TypeName>
    1  body fails validation (per-error detail printed to stdout)
    2  usage error (missing/invalid args, bad JSON, unknown type, etc.)

Self-test (no app, no network — proves the gate has teeth):
    validate_response.py --selftest

Run under `python3 -I` (isolated mode) via a dedicated venv; see lib.sh.
Needs: jsonschema>=4.18, referencing
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# examples/_lib/validate_response.py -> examples/_lib -> examples -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "shipping.schema.json"


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def build_validator(schema: dict[str, Any], type_name: str) -> Draft202012Validator:
    defs = schema.get("$defs", {})
    if type_name not in defs:
        available = ", ".join(sorted(defs))
        raise SystemExit(
            f"Unknown type '{type_name}'. Available $defs: {available}"
        )
    registry = Resource.from_contents(schema) @ Registry()
    return Draft202012Validator(
        {"$ref": schema["$id"] + f"#/$defs/{type_name}"}, registry=registry
    )


def validate_body(type_name: str, body: Any) -> list[str]:
    """Return a list of human-readable error strings; empty means valid."""
    schema = load_schema()
    validator = build_validator(schema, type_name)
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
    messages: list[str] = []
    for err in errors:
        loc = "/".join(str(p) for p in err.path) or "(root)"
        messages.append(f"{loc}: {err.message}")
    return messages


def _read_body(arg: str | None) -> Any:
    if arg is None or arg == "-":
        raw = sys.stdin.read()
        source = "<stdin>"
    else:
        path = Path(arg)
        if not path.is_file():
            raise SystemExit(f"No such file: {arg}")
        raw = path.read_text(encoding="utf-8")
        source = arg
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {source}: {exc}") from exc


# --------------------------------------------------------------------------
# Self-test: drift-proof check that the validator actually rejects bad data.
# This must pass with NO app, NO network, NO fixtures on disk — only the
# schema file itself.
# --------------------------------------------------------------------------

def _known_good_booking() -> dict[str, Any]:
    return {
        "id": "bkg_01H9XZ8K3QJ7M2N4P6R8T0V2W4",
        "status": "PENDING",
        "origin": {"unLocode": "USNYC", "name": "New York", "country": "US"},
        "destination": {"unLocode": "NLRTM", "name": "Rotterdam", "country": "NL"},
        "cargo": [
            {
                "id": "crg_01H9XZ8K3QJ7M2N4P6R8T0V2W4",
                "description": "Palletized electronics",
                "type": "GENERAL",
                "dimensions": {"weightKg": 1200.5, "volumeM3": 4.2},
                "hazardous": False,
            }
        ],
        "quote": {"currency": "USD", "amount": "1250.00"},
        "requestedPickup": "2026-02-01",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }


def _known_good_operation_with_null_completed() -> dict[str, Any]:
    return {
        "id": "op_01H9XZ8K3QJ7M2N4P6R8T0V2W4",
        "status": "RUNNING",
        "createdAt": "2026-01-01T00:00:00Z",
        "completedAt": None,
        "resource": None,
        "error": None,
    }


def _selftest_case(label: str, ok: bool) -> bool:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    return ok


def selftest() -> int:
    passed = True

    # 1. Known-good Booking must validate cleanly.
    good = _known_good_booking()
    good_errors = validate_body("Booking", good)
    passed &= _selftest_case(
        "known-good Booking validates", not good_errors
    )
    if good_errors:
        for e in good_errors:
            print(f"      - {e}")

    # 2a. Tamper: unexpected additional property -> additionalProperties:false.
    tampered_extra_field = copy.deepcopy(good)
    tampered_extra_field["unexpectedField"] = "should not be allowed"
    errors_extra = validate_body("Booking", tampered_extra_field)
    passed &= _selftest_case(
        "tampered Booking (extra field) is rejected", bool(errors_extra)
    )

    # 2b. Tamper: status outside the FSM enum.
    tampered_status = copy.deepcopy(good)
    tampered_status["status"] = "TELEPORTING"
    errors_status = validate_body("Booking", tampered_status)
    passed &= _selftest_case(
        "tampered Booking (bad status enum) is rejected", bool(errors_status)
    )

    # 2c. Tamper: id that doesn't match the bkg_ pattern.
    tampered_id = copy.deepcopy(good)
    tampered_id["id"] = "not-a-valid-id"
    errors_id = validate_body("Booking", tampered_id)
    passed &= _selftest_case(
        "tampered Booking (bad id pattern) is rejected", bool(errors_id)
    )

    # 3. Operation with completedAt: null must validate (2020-12 nullable
    #    via type:["string","null"]). This catches a validator/schema setup
    #    that mishandles nullable fields (e.g. wrong draft, broken $ref).
    op = _known_good_operation_with_null_completed()
    op_errors = validate_body("Operation", op)
    passed &= _selftest_case(
        "Operation with completedAt:null validates", not op_errors
    )
    if op_errors:
        for e in op_errors:
            print(f"      - {e}")

    return 0 if passed else 1


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        print("Running validate_response.py self-test (no app required)...")
        rc = selftest()
        print("SELFTEST PASSED" if rc == 0 else "SELFTEST FAILED")
        return rc

    if not argv:
        print(__doc__)
        return 2

    type_name = argv[0]
    path_arg = argv[1] if len(argv) > 1 else None
    body = _read_body(path_arg)

    errors = validate_body(type_name, body)
    if errors:
        print(f"INVALID: body does not conform to #/$defs/{type_name}")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: body conforms to #/$defs/{type_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
