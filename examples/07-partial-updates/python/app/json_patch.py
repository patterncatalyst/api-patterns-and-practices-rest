"""RFC 6902 JSON Patch, hand-rolled against plain dict/list/JSON-ish values
so this chapter needs no extra dependency (the same choice `_merge_patch`
in main.py makes for RFC 7396 JSON Merge Patch).

`apply_patch` never mutates its input: every structural operation
(add/remove/replace/move/copy) works against a deep copy and returns a
brand-new value.

Supports all six RFC 6902 Section 4 operations: add, remove, replace, move,
copy, test. JSON Pointer (RFC 6901) path syntax is implemented directly,
including the `~1`/`~0` escapes and the `-` "append" array index.
"""
from __future__ import annotations

import copy
from typing import Any

_MISSING = object()


class JsonPatchError(Exception):
    """A patch op addressed a path that doesn't exist, or the document is malformed."""


class JsonPatchTestFailed(Exception):
    """A `test` operation's actual value did not match its expected `value` (RFC 6902 Section 4.6)."""


# ---------------------------------------------------------------------------
# RFC 6901 JSON Pointer
# ---------------------------------------------------------------------------

def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _tokenize(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise JsonPatchError(f"invalid JSON Pointer: {pointer!r}")
    return [_unescape(t) for t in pointer.split("/")[1:]]


def _read_index(token: str, size: int) -> int:
    """Index for a READ (get/remove/replace-target): '-' is not a readable index."""
    if token == "-":
        raise JsonPatchError("'-' is only valid as an add/move/copy destination, not a read")
    return _parse_index(token, size, size - 1)


def _write_index(token: str, size: int) -> int:
    """Index for a WRITE destination (add/move/copy target): '-' means append."""
    if token == "-":
        return size
    return _parse_index(token, size, size)


def _parse_index(token: str, size: int, max_index: int) -> int:
    try:
        idx = int(token)
    except ValueError as exc:
        raise JsonPatchError(f"invalid array index: {token!r}") from exc
    if idx < 0 or idx > max_index:
        raise JsonPatchError(f"array index out of bounds: {idx} (size {size})")
    return idx


def _get(doc: Any, tokens: list[str]) -> Any:
    node = doc
    for token in tokens:
        if isinstance(node, list):
            node = node[_read_index(token, len(node))]
        elif isinstance(node, dict):
            if token not in node:
                raise JsonPatchError(f"path segment not found: {token!r}")
            node = node[token]
        else:
            raise JsonPatchError(f"cannot descend into a scalar at {token!r}")
    return node


def _navigate_to_parent(doc: Any, tokens: list[str]) -> Any:
    node = doc
    for token in tokens[:-1]:
        if isinstance(node, list):
            node = node[_read_index(token, len(node))]
        elif isinstance(node, dict):
            if token not in node:
                raise JsonPatchError(f"path segment not found: {token!r}")
            node = node[token]
        else:
            raise JsonPatchError(f"cannot descend into a scalar at {token!r}")
    return node


def _add(target: Any, tokens: list[str], value: Any) -> Any:
    if not tokens:
        return value
    doc = copy.deepcopy(target)
    parent = _navigate_to_parent(doc, tokens)
    last = tokens[-1]
    if isinstance(parent, list):
        parent.insert(_write_index(last, len(parent)), value)
    elif isinstance(parent, dict):
        parent[last] = value
    else:
        raise JsonPatchError("cannot add into a scalar")
    return doc


def _replace(target: Any, tokens: list[str], value: Any) -> Any:
    if not tokens:
        return value
    doc = copy.deepcopy(target)
    parent = _navigate_to_parent(doc, tokens)
    last = tokens[-1]
    if isinstance(parent, list):
        parent[_read_index(last, len(parent))] = value
    elif isinstance(parent, dict):
        if last not in parent:
            raise JsonPatchError(f"path segment not found: {last!r}")
        parent[last] = value
    else:
        raise JsonPatchError("cannot replace into a scalar")
    return doc


def _remove(target: Any, tokens: list[str]) -> Any:
    if not tokens:
        raise JsonPatchError("cannot remove the document root")
    doc = copy.deepcopy(target)
    parent = _navigate_to_parent(doc, tokens)
    last = tokens[-1]
    if isinstance(parent, list):
        del parent[_read_index(last, len(parent))]
    elif isinstance(parent, dict):
        if last not in parent:
            raise JsonPatchError(f"path segment not found: {last!r}")
        del parent[last]
    else:
        raise JsonPatchError("cannot remove from a scalar")
    return doc


def apply_patch(doc: Any, operations: Any) -> Any:
    """Apply an RFC 6902 JSON Patch document to `doc`, returning a NEW
    value. `doc` is never mutated in place."""
    if not isinstance(operations, list):
        raise JsonPatchError("a JSON Patch document must be a JSON array of operations")

    for op_doc in operations:
        if not isinstance(op_doc, dict) or "op" not in op_doc or "path" not in op_doc:
            raise JsonPatchError("each operation needs an 'op' and a 'path'")
        op = op_doc["op"]
        tokens = _tokenize(op_doc["path"])

        if op == "add":
            doc = _add(doc, tokens, _require_value(op_doc))
        elif op == "remove":
            doc = _remove(doc, tokens)
        elif op == "replace":
            doc = _replace(doc, tokens, _require_value(op_doc))
        elif op == "move":
            from_tokens = _tokenize(_require_text(op_doc, "from"))
            value = _get(doc, from_tokens)
            doc = _add(_remove(doc, from_tokens), tokens, value)
        elif op == "copy":
            from_tokens = _tokenize(_require_text(op_doc, "from"))
            doc = _add(doc, tokens, copy.deepcopy(_get(doc, from_tokens)))
        elif op == "test":
            actual = _get(doc, tokens)
            expected = op_doc.get("value")
            if actual != expected:
                raise JsonPatchTestFailed(
                    f"test failed at {op_doc['path']!r}: expected {expected!r}, got {actual!r}"
                )
        else:
            raise JsonPatchError(f"unsupported op: {op!r}")

    return doc


def _require_value(op_doc: dict) -> Any:
    if "value" not in op_doc:
        raise JsonPatchError(f"'{op_doc.get('op')}' requires a 'value'")
    return op_doc["value"]


def _require_text(op_doc: dict, field: str) -> str:
    value = op_doc.get(field, _MISSING)
    if value is _MISSING or not isinstance(value, str):
        raise JsonPatchError(f"'{op_doc.get('op')}' requires a '{field}' string")
    return value
