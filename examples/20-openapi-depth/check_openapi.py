#!/usr/bin/env python3
"""Ch20 OpenAPI-in-depth anchor — structural checks on a SERVED OpenAPI
document, invoked by verify.sh for both the Quarkus and the FastAPI stack.

Three assertions, each independent of exact formatting/ordering (no
byte-equal diffing — see README.md's "the drift probe" section):

1. The document contains at least one JSON-Schema-style nullable
   construct: either a `type` ARRAY including "null" (OpenAPI 3.1 / full
   JSON Schema style) or the OAS-3.0 `nullable: true` keyword, found
   anywhere under `components.schemas` (or `components/schemas` nested
   refs) by walking the whole document.
2. The document exposes a non-empty top-level `webhooks` map.
3. DRIFT CHECK: the document's own `Booking` schema (under
   `components.schemas.Booking`) declares the same SET of `required`
   property names as `#/$defs/Booking` in the shared contract schema
   (contracts/schemas/shipping.schema.json) — a normalized/structural
   comparison, not a byte-equal diff. A chapter example that silently drops
   or adds a required Booking field relative to the contract fails here.

Usage:
    check_openapi.py <stack-label> <path-to-served-openapi.json> <path-to-contract-schema.json>

Exit codes:
    0  all three checks pass
    1  one or more checks failed (details printed to stdout)
    2  usage / file-not-found / invalid JSON error

Run under `python3 -I` (isolated mode, stdlib only — no extra deps needed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: str) -> Any:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"No such file: {path}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def _find_nullable_construct(node: Any, path: str = "$") -> str | None:
    """Walk the whole document; return a path string describing the first
    nullable construct found (type-array-with-null OR nullable:true), or
    None if none exists anywhere."""
    if isinstance(node, dict):
        type_value = node.get("type")
        if isinstance(type_value, list) and "null" in type_value:
            return f"{path}.type (type array: {type_value})"
        if node.get("nullable") is True:
            return f"{path}.nullable"
        for key, value in node.items():
            found = _find_nullable_construct(value, f"{path}.{key}")
            if found:
                return found
    elif isinstance(node, list):
        for i, item in enumerate(node):
            found = _find_nullable_construct(item, f"{path}[{i}]")
            if found:
                return found
    return None


def check_document(doc: dict, contract_schema: dict, stack_label: str) -> list[str]:
    errors: list[str] = []

    # --- 1. nullable construct present anywhere in the document ----------
    nullable_path = _find_nullable_construct(doc)
    if nullable_path:
        print(f"  [ok] {stack_label}: nullable construct found at {nullable_path}")
    else:
        errors.append(
            f"{stack_label}: no JSON-Schema nullable construct found anywhere "
            "in the served OpenAPI document (expected a `type` array "
            "containing \"null\", or `nullable: true`)"
        )

    # --- 2. top-level webhooks section, non-empty -------------------------
    webhooks = doc.get("webhooks")
    if isinstance(webhooks, dict) and webhooks:
        print(f"  [ok] {stack_label}: webhooks section present ({sorted(webhooks)})")
    else:
        errors.append(
            f"{stack_label}: served OpenAPI document has no non-empty "
            f"top-level `webhooks` section (got: {webhooks!r})"
        )

    # --- 3. drift check: required-field SET for Booking matches contract -
    live_booking = doc.get("components", {}).get("schemas", {}).get("Booking")
    if live_booking is None:
        errors.append(f"{stack_label}: no components.schemas.Booking in the served document")
    else:
        live_required = set(live_booking.get("required", []))
        contract_required = set(contract_schema["$defs"]["Booking"]["required"])
        if live_required == contract_required:
            print(
                f"  [ok] {stack_label}: Booking required-field set matches contract "
                f"({sorted(live_required)})"
            )
        else:
            errors.append(
                f"{stack_label}: Booking required-field set DRIFTED from the contract.\n"
                f"      contract  (#/$defs/Booking.required): {sorted(contract_required)}\n"
                f"      live doc  (components.schemas.Booking.required): {sorted(live_required)}\n"
                f"      missing from live doc: {sorted(contract_required - live_required)}\n"
                f"      extra in live doc:     {sorted(live_required - contract_required)}"
            )

    return errors


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2

    stack_label = argv[0]
    doc = _load_json(argv[1])
    contract_schema = _load_json(argv[2])

    errors = check_document(doc, contract_schema, stack_label)
    if errors:
        print(f"INVALID: {stack_label} OpenAPI document failed structural checks:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: {stack_label} OpenAPI document passes all structural checks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
