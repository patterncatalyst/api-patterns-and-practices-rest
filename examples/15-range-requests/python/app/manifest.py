"""Deterministic, fixed-size, in-memory "manifest" generator — the large
binary resource this chapter serves Range requests against.

Each booking's manifest is a MANIFEST_SIZE_BYTES-byte blob derived purely
from the booking id: block[0] = SHA-256(bookingId), block[n] =
SHA-256(block[n-1]), concatenated until the target size is reached and
truncated to it. Same id in, same bytes out, every time, with no
persistence — generated once per booking id and cached, so repeated Range
requests against the same manifest don't re-hash ~2 MiB on every call. The
two stacks are NOT required to produce byte-identical manifests for the same
id (each has its own booking store and ids); what matters for Ch15's point
is that EACH stack, independently, produces a deterministic, known-size
manifest that correctly serves Range requests over it. Mirrors
../../quarkus/.../ManifestGenerator.java conceptually (same chaining idea),
not byte-for-byte.
"""
from __future__ import annotations

import hashlib

# ~2 MiB — comfortably in the "1-5 MiB" range the chapter targets.
MANIFEST_SIZE_BYTES = 2 * 1024 * 1024

_cache: dict[str, bytes] = {}


def _generate(booking_id: str) -> bytes:
    chunks: list[bytes] = []
    block = hashlib.sha256(booking_id.encode("utf-8")).digest()
    total = 0
    while total < MANIFEST_SIZE_BYTES:
        chunks.append(block)
        total += len(block)
        block = hashlib.sha256(block).digest()
    return b"".join(chunks)[:MANIFEST_SIZE_BYTES]


def get_manifest(booking_id: str) -> bytes:
    cached = _cache.get(booking_id)
    if cached is None:
        cached = _generate(booking_id)
        _cache[booking_id] = cached
    return cached
