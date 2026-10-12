#!/usr/bin/env python3
"""Validate instance data against the shared JSON Schema components.

Confirms the acceptance-criterion reuse rule end to end: the CloudEvents example
payload (`contracts/cloudevents/*.example.json`) validates against the
`BookingEvent` component in `contracts/schemas/shipping.schema.json` — the same
component the AsyncAPI document references.

Run:  python3 -I scripts/validate_schemas.py
Needs: jsonschema>=4.18, referencing   (installed in CI)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "contracts" / "schemas" / "shipping.schema.json"
CLOUDEVENTS_DIR = REPO_ROOT / "contracts" / "cloudevents"


def main() -> int:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    registry = Resource.from_contents(schema) @ Registry()
    event_validator = Draft202012Validator(
        {"$ref": schema["$id"] + "#/$defs/BookingEvent"}, registry=registry
    )

    failures: list[str] = []
    examples = sorted(CLOUDEVENTS_DIR.glob("*.example.json"))
    for path in examples:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        data = envelope.get("data", envelope)
        errors = sorted(event_validator.iter_errors(data), key=lambda e: list(e.path))
        for err in errors:
            loc = "/".join(str(p) for p in err.path) or "(root)"
            failures.append(f"{path.name}: data.{loc}: {err.message}")

    print(f"Validated {len(examples)} CloudEvents example(s) against BookingEvent.")
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All instance data conforms to the shared schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
