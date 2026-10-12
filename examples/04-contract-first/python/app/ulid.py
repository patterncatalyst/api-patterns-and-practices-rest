"""Minimal ULID generator (Crockford Base32, 26 chars): 48-bit timestamp (ms
since epoch, 10 chars) + 80-bit randomness (16 chars). Deliberately
dependency-free so this chapter's Containerfile stays small — a real project
would pull a vetted ULID library, but the shared schema only cares that
`bkg_`/`crg_` ids match `^[0-9A-HJKMNP-TV-Z]{26}$` (Crockford base32: no I,
L, O, U). Mirrors app/../quarkus/.../Ulid.java bit for bit.
"""
from __future__ import annotations

import hashlib
import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars = [""] * length
    for i in range(length - 1, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def generate_ulid() -> str:
    """Return a 26-char Crockford-Base32 ULID string (no prefix)."""
    timestamp_ms = int(time.time() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    return _encode(timestamp_ms, 10) + _encode(randomness, 16)


def generate_deterministic_ulid(seed: str) -> str:
    """A deterministic, non-random "ULID-shaped" id derived from `seed` —
    same seed in, same 26-char Crockford string out, every time.

    Used by PUT (full replace), NOT by POST: an idempotent replace must
    converge on the SAME resource state (including sub-resource ids like
    Cargo.id) when called twice with the same body, whereas a create must
    mint a genuinely new id every call. Mirrors
    ../quarkus/.../Ulid.java#deterministic bit for bit (SHA-256, first 17
    hash bytes -> 26 Crockford chars).
    """
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    value = int.from_bytes(digest[:17], "big")
    return _encode(value, 26)
