#!/usr/bin/env python3
"""Structural check for contracts/arazzo/booking-workflow.yaml — deliberately
NOT a full Arazzo validator (the task is proving the workflow document is
well-formed enough to drive the `bookAndConfirm` sequence, not re-implementing
an Arazzo runtime in CI). Stdlib-only, no PyYAML dependency: scans lines
rather than parsing YAML, which is enough to assert the required top-level
and nested keys are present in the right place.

Usage: check_arazzo.py <path-to-booking-workflow.yaml>
Exit 0 and prints "ok: ..." on success; exit 1 with a message on failure.
"""
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_arazzo.py <path-to-booking-workflow.yaml>")
        return 2

    path = argv[0]
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()

    if not any(line.startswith("arazzo:") for line in lines):
        print(f"FAIL: {path} is missing a top-level 'arazzo:' key")
        return 1

    if not any(line.startswith("workflows:") for line in lines):
        print(f"FAIL: {path} is missing a top-level 'workflows:' key")
        return 1

    start = None
    for i, line in enumerate(lines):
        if "workflowId: bookAndConfirm" in line:
            start = i
            break
    if start is None:
        print(f"FAIL: {path} has no workflow with workflowId: bookAndConfirm")
        return 1

    # The bookAndConfirm workflow's block runs from `start` up to (but not
    # including) the next list item at the same nesting level, i.e. the next
    # "- workflowId:" line, or end of file.
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].strip().startswith("- workflowId:"):
            end = j
            break
    block = lines[start:end]

    if not any(line.strip() == "steps:" for line in block):
        print(f"FAIL: workflow 'bookAndConfirm' in {path} has no 'steps:' key")
        return 1

    print(f"ok: {path} has 'arazzo', 'workflows', and workflow 'bookAndConfirm' with 'steps'")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
