"""Bloom filter for pre-fetch ID dedup.

Reference: Bloom, Burton H. (1970). "Space/time trade-offs in hash
coding with allowable errors." *Communications of the ACM* 13(7):
422-426.

Sizing (see the docstring on :func:`optimal_params`):

    m = ceil( -n * ln(p) / ln(2)**2 )        # number of bits
    k = round( m/n * ln(2) )                 # number of hash functions

For a target 1% false-positive rate the filter uses ~9.6 bits per
element — 10M IDs -> ~12 MB. At 100M IDs (still under the plan's
256 MB disk budget) the filter is ~120 MB.

Pure Python, dependency-free. The bit vector is a :class:`bytearray`;
hashing uses the stdlib ``hashlib.blake2b`` and splits the digest into
``k`` independent 64-bit integers — Kirsch & Mitzenmacher's 2006
"Less Hashing, Same Performance" double-hashing trick keeps CPU cost
linear in *k* with only one real hash computation.

Thread safety: ``add`` and ``contains`` both call ``_indices``; the
bit writes in ``add`` are not atomic. For single-threaded producer +
multi-threaded consumer, wrap calls in a lock or construct one filter
per worker.
"""

from __future__ import annotations

import hashlib
import math
from typing import Iterable


def optimal_params(capacity: int, false_positive_rate: float) -> tuple[int, int]:
    """Return (num_bits, num_hashes) for the given capacity + FP rate."""
    if capacity <= 0:
        raise ValueError("capacity must be > 0")
    if not 0.0 < false_positive_rate < 1.0:
        raise ValueError("false_positive_rate must be in (0, 1)")
    ln2 = math.log(2)
    num_bits = int(
        math.ceil(
            -capacity * math.log(false_positive_rate) / (ln2 * ln2),
        )
    )
    num_hashes = max(1, round((num_bits / capacity) * ln2))
    return num_bits, num_hashes


class BloomFilter:
    """Standard Bloom filter over a bytearray bit vector."""

    __slots__ = ("_bits", "_num_bits", "_num_hashes", "_capacity", "_fp_rate")

    def __init__(
        self,
        *,
        capacity: int = 10_000_000,
        false_positive_rate: float = 0.01,
    ) -> None:
        num_bits, num_hashes = optimal_params(capacity, false_positive_rate)
        # Round up to the nearest byte so we can store the vector in a bytearray.
        byte_count = (num_bits + 7) // 8
        self._num_bits = byte_count * 8
        self._num_hashes = num_hashes
        self._bits = bytearray(byte_count)
        self._capacity = capacity
        self._fp_rate = false_positive_rate

    # ── Dunder + introspection ────────────────────────────────────

    def __contains__(self, key: bytes | str | int) -> bool:
        return all(self._test_bit(i) for i in self._indices(key))

    def __len__(self) -> int:
        """Set-cardinality estimate (Swamidass & Baldi 2007 formula).

        Bloom filters don't know their own cardinality exactly; this
        returns an estimate useful for "is it ~nearly full?" checks.
        For a precise count use :class:`HyperLogLog` alongside.
        """
        set_bits = sum(bin(b).count("1") for b in self._bits)
        if set_bits == 0:
            return 0
        if set_bits >= self._num_bits:
            # Saturated — the estimator diverges; report capacity.
            return self._capacity
        ratio = 1.0 - (set_bits / self._num_bits)
        if ratio <= 0:
            return self._capacity
        return int(
            -(self._num_bits / self._num_hashes) * math.log(ratio),
        )

    @property
    def num_bits(self) -> int:
        return self._num_bits

    @property
    def num_hashes(self) -> int:
        return self._num_hashes

    @property
    def byte_size(self) -> int:
        """Approximate on-disk size of the bit vector."""
        return len(self._bits)

    # ── Public API ────────────────────────────────────────────────

    def add(self, key: bytes | str | int) -> None:
        """Mark *key* as seen."""
        for idx in self._indices(key):
            byte_idx, bit_mask = divmod(idx, 8)
            self._bits[byte_idx] |= 1 << bit_mask

    def update(self, keys: Iterable[bytes | str | int]) -> None:
        """Bulk-add every element of *keys*."""
        for key in keys:
            self.add(key)

    def clear(self) -> None:
        """Reset the filter to empty."""
        for i in range(len(self._bits)):
            self._bits[i] = 0

    # ── Internals ─────────────────────────────────────────────────

    def _test_bit(self, idx: int) -> bool:
        byte_idx, bit_mask = divmod(idx, 8)
        return bool(self._bits[byte_idx] & (1 << bit_mask))

    def _indices(self, key: bytes | str | int):
        """Yield the k bit positions for *key* via double-hashing."""
        data = self._to_bytes(key)
        # 16-byte digest: split into two 64-bit ints for the Kirsch-
        # Mitzenmacher double-hashing construction. ``blake2b`` is
        # faster than SHA-256 and has no collision-attack relevance
        # here; the Bloom filter's FP rate is driven by random
        # distribution, not cryptographic strength.
        digest = hashlib.blake2b(data, digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], "little")
        h2 = int.from_bytes(digest[8:], "little")
        for i in range(self._num_hashes):
            # (h1 + i * h2) mod m — double hashing.
            yield (h1 + i * h2) % self._num_bits

    @staticmethod
    def _to_bytes(key: bytes | str | int) -> bytes:
        if isinstance(key, bytes):
            return key
        if isinstance(key, str):
            return key.encode("utf-8")
        if isinstance(key, int):
            # signed-safe encoding — negative ints get two's-complement.
            length = max(1, (key.bit_length() + 8) // 8)
            return key.to_bytes(length, "little", signed=True)
        raise TypeError(f"Bloom key must be bytes/str/int, got {type(key).__name__}")
