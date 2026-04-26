"""HyperLogLog cardinality sketch — pure Python, dependency-free.

Reference: Flajolet, Fusy, Gandouet & Meunier (2007). "HyperLogLog:
the analysis of a near-optimal cardinality estimation algorithm."
*Proceedings of the 2007 International Conference on Analysis of
Algorithms* (AofA '07), 127-146.

Design decisions:

- Precision ``b`` is the number of register-index bits. The register
  array has size ``m = 2**b``. Each register holds a 6-bit count
  (enough for hash widths up to 64 bits). With ``b=14`` (the default)
  the sketch uses ``m = 16384`` registers × 6 bits ≈ **12 KB** and
  estimates cardinalities from 0 to ~2^57 with a standard error of
  ``1.04 / sqrt(m) ≈ 0.81%``.

- We use the standard ``blake2b(digest_size=8)`` 64-bit hash, split
  into:
      idx = high ``b`` bits           → register index
      w   = remaining ``64 - b`` bits → leading-zero count + 1 feeds
                                        into the register

- Small-cardinality estimates use the linear-counting correction
  from the original paper. Large-cardinality correction (above
  ``2^32 / 30``) is omitted because the 64-bit hash width makes it
  practically unreachable in our use case; implemented for
  completeness anyway.

- Registers live in a bytearray (one register per byte for simple
  indexing — the extra 2 bits per register are a cheap trade to
  avoid bit-packing, and ``b=14`` still leaves the sketch at ~16 KB).

Mergeability: two HLLs with the same ``b`` can be union-merged by
taking the register-wise max. Useful when shards compute per-partition
HLLs and aggregate once.
"""

from __future__ import annotations

import hashlib
import math


class HyperLogLog:
    """Approximate distinct-element counter.

    Typical use::

        hll = HyperLogLog(precision=14)
        for post_id in stream:
            hll.add(post_id)
        print("seen ~", hll.count(), "unique posts")
    """

    __slots__ = ("_b", "_m", "_registers", "_alpha")

    MIN_PRECISION: int = 4
    MAX_PRECISION: int = 16

    def __init__(self, *, precision: int = 14) -> None:
        if not self.MIN_PRECISION <= precision <= self.MAX_PRECISION:
            raise ValueError(
                f"precision must be in [{self.MIN_PRECISION}, " f"{self.MAX_PRECISION}]"
            )
        self._b = precision
        self._m = 1 << precision
        self._registers = bytearray(self._m)
        self._alpha = self._alpha_for(self._m)

    # ── Public API ────────────────────────────────────────────────

    def add(self, key: bytes | str | int) -> None:
        """Record a single element."""
        data = self._to_bytes(key)
        h = hashlib.blake2b(data, digest_size=8).digest()
        hashed = int.from_bytes(h, "little")
        # Top `b` bits → register index.
        idx = hashed >> (64 - self._b)
        # Remaining (64 - b) bits → leading-zero count + 1.
        w = (hashed << self._b) & ((1 << 64) - 1)
        # rank = position of leftmost 1-bit in w, 1-indexed.
        rank = self._leading_zeros(w, width=64) + 1
        if rank > self._registers[idx]:
            self._registers[idx] = min(rank, 63)

    def update(self, keys) -> None:
        """Bulk-add every element of *keys*."""
        for key in keys:
            self.add(key)

    def count(self) -> int:
        """Return the cardinality estimate."""
        m = self._m
        # Raw estimate.
        # E = alpha_m * m^2 / sum_i(2^-M[i])
        raw_sum = 0.0
        zero_registers = 0
        for r in self._registers:
            raw_sum += 2.0**-r
            if r == 0:
                zero_registers += 1
        est = self._alpha * m * m / raw_sum

        # Small-range correction (linear counting).
        if est <= 2.5 * m and zero_registers > 0:
            est = m * math.log(m / zero_registers)
        # Large-range correction (negligible with 64-bit hashes but cheap).
        elif est > (1 << 32) / 30.0:
            est = -(1 << 32) * math.log(1.0 - est / (1 << 32))

        return int(round(est))

    def merge(self, other: "HyperLogLog") -> None:
        """In-place register-wise max merge with another HLL of the same precision."""
        if other._b != self._b:
            raise ValueError(
                f"merge requires equal precision, got {self._b} and {other._b}"
            )
        for i in range(self._m):
            if other._registers[i] > self._registers[i]:
                self._registers[i] = other._registers[i]

    def clear(self) -> None:
        """Reset every register to 0."""
        for i in range(self._m):
            self._registers[i] = 0

    # ── Introspection ─────────────────────────────────────────────

    @property
    def precision(self) -> int:
        return self._b

    @property
    def register_count(self) -> int:
        return self._m

    @property
    def byte_size(self) -> int:
        return len(self._registers)

    @property
    def relative_error(self) -> float:
        """Typical standard error of the estimate."""
        return 1.04 / math.sqrt(self._m)

    # ── Internals ─────────────────────────────────────────────────

    @staticmethod
    def _alpha_for(m: int) -> float:
        """HLL alpha constants from the paper, with the closed-form for m >= 128."""
        if m == 16:
            return 0.673
        if m == 32:
            return 0.697
        if m == 64:
            return 0.709
        return 0.7213 / (1.0 + 1.079 / m)

    @staticmethod
    def _leading_zeros(n: int, *, width: int) -> int:
        """Number of leading zeros in *n* treated as a *width*-bit integer."""
        if n == 0:
            return width
        return width - n.bit_length()

    @staticmethod
    def _to_bytes(key: bytes | str | int) -> bytes:
        if isinstance(key, bytes):
            return key
        if isinstance(key, str):
            return key.encode("utf-8")
        if isinstance(key, int):
            length = max(1, (key.bit_length() + 8) // 8)
            return key.to_bytes(length, "little", signed=True)
        raise TypeError(f"HLL key must be bytes/str/int, got {type(key).__name__}")
