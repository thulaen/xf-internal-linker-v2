"""Contract tests: the Rust ``extensions.compressed_bloom`` kernel.

The Rust kernel (``rust/extensions/compressed_bloom``, built to
``compressed_bloom.so`` and staged at ``/opt/xf/compiled/active/extensions/``)
is the SOLE implementation of the compressed Bloom filter. The C++ kernel
(``backend/extensions/compressed_bloom.cpp``) is ported away (RUST-FIRST.md
zero-fallback / dead-code-on-replace); its C++ source is deleted in the
follow-up phase.

There is NO byte-for-byte parity with the old C++ bit-to-index mapping, and that
is deliberate: the C++ kernel indexed bits with ``std::hash<std::string>``,
which is libstdc++-implementation-defined, so the exact mapping was never a
portable contract. A repository-wide search found zero Python callers of
``add``/``contains``, so no caller depends on specific hash outputs or specific
bit layouts.

These tests therefore assert the Bloom filter BEHAVIOURAL contract (Bloom 1970,
"Space/Time Trade-offs in Hash Coding with Allowable Errors", Communications of
the ACM 13(7):422-426, doi:10.1145/362686.362692), not C++ value equality. Every
committed assertion is STANDALONE — it depends only on the Rust kernel's own
output and on hand-computed exact values — so the suite survives the C++
source's deletion in the next phase (there is no Python fallback to compare
against; ``python_fallback_path`` is "none" in the port spec).

Contract asserted here:

1. No false negatives — an added item is always ``contains``-true, and stays
   true forever after further inserts (bits are never cleared; there is no
   ``remove``).
2. An unseen / never-added item is not contained (barring collisions, which a
   wide table avoids for these probes).
3. ``contains`` requires ALL indexed bits set — a fresh, empty filter contains
   nothing.
4. ``byte_count() == (bit_count + 7) // 8`` (hand-computed exact values across
   byte boundaries).
5. ``bit_count()`` and ``hash_count()`` echo the constructor arguments.
6. Determinism — identical construction + insert stream yields identical
   ``contains`` / ``bit_count`` / ``byte_count`` / ``hash_count`` across two
   filters.
7. Guard — ``CompressedBloomFilter(0, h)`` / ``CompressedBloomFilter(c, 0)``
   raise ``ValueError``.
8. Unicode and empty-string keys round-trip.

Skipped (not failed) when the Rust ``.so`` is not built/staged yet, so the suite
stays green on a host that has not run the compiled-artifacts build. The
build-and-wire step (``scripts/ensure_compiled_artifacts.py``) flips this from
skipped to executed.

Source for the semantics: ``backend/tmp/port-specs/compressed_bloom.json`` and
the Bloom 1970 paper cited there.
"""

from __future__ import annotations

import unittest

try:
    from extensions import compressed_bloom as rust_cbf

    _HAS_CBF = hasattr(rust_cbf, "CompressedBloomFilter")
except ImportError:
    _HAS_CBF = False


@unittest.skipUnless(
    _HAS_CBF,
    "Rust extensions.compressed_bloom not built/staged yet — run "
    "scripts/ensure_compiled_artifacts.py in the compiled-tools image.",
)
class RustCompressedBloomContractTests(unittest.TestCase):
    """Behavioural-contract tests for the Rust compressed Bloom filter kernel."""

    def test_unseen_item_is_not_contained(self) -> None:
        bloom = rust_cbf.CompressedBloomFilter(2048, 5)
        self.assertFalse(bloom.contains("never-added"))

    def test_added_item_is_contained_no_false_negative(self) -> None:
        bloom = rust_cbf.CompressedBloomFilter(4096, 5)
        bloom.add("alpha")
        self.assertTrue(bloom.contains("alpha"))

    def test_no_false_negatives_for_many_added_keys(self) -> None:
        bloom = rust_cbf.CompressedBloomFilter(1 << 20, 4)
        for i in range(5000):
            bloom.add(f"key-{i}")
        for i in range(5000):
            self.assertTrue(
                bloom.contains(f"key-{i}"),
                f"false negative for key-{i}",
            )

    def test_add_is_permanent_no_remove(self) -> None:
        # A set bit is never cleared (no remove): a once-added item stays
        # contained forever, even after many other inserts.
        bloom = rust_cbf.CompressedBloomFilter(1 << 20, 4)
        bloom.add("permanent")
        self.assertTrue(bloom.contains("permanent"))
        for i in range(1000):
            bloom.add(f"noise-{i}")
        self.assertTrue(bloom.contains("permanent"))

    def test_empty_filter_contains_nothing(self) -> None:
        # contains() requires ALL indexed bits set; a fresh filter has every
        # bit zero, so anything probed is absent.
        bloom = rust_cbf.CompressedBloomFilter(2048, 5)
        self.assertFalse(bloom.contains("anything"))

    def test_byte_count_is_ceil_bit_count_over_eight(self) -> None:
        # Hand-computed exact values across byte boundaries:
        #   1 -> 1, 8 -> 1, 9 -> 2, 16 -> 2, 17 -> 3, 1000 -> 125, 2048 -> 256.
        cases = {1: 1, 8: 1, 9: 2, 16: 2, 17: 3, 1000: 125, 2048: 256}
        for bits, expected_bytes in cases.items():
            bloom = rust_cbf.CompressedBloomFilter(bits, 1)
            self.assertEqual(
                bloom.byte_count(),
                expected_bytes,
                f"byte_count for {bits} bits should be {expected_bytes}",
            )

    def test_bit_count_and_hash_count_echo_constructor(self) -> None:
        bloom = rust_cbf.CompressedBloomFilter(1234, 7)
        self.assertEqual(bloom.bit_count(), 1234)
        self.assertEqual(bloom.hash_count(), 7)

    def test_unicode_key_round_trips(self) -> None:
        bloom = rust_cbf.CompressedBloomFilter(1 << 20, 4)
        bloom.add("日本語-mañana-🚀")
        self.assertTrue(bloom.contains("日本語-mañana-🚀"))
        self.assertFalse(bloom.contains("日本語-mañana-🛸"))

    def test_empty_string_key_is_supported(self) -> None:
        bloom = rust_cbf.CompressedBloomFilter(1 << 20, 4)
        self.assertFalse(bloom.contains(""))
        bloom.add("")
        self.assertTrue(bloom.contains(""))

    def test_is_deterministic(self) -> None:
        def build() -> object:
            bloom = rust_cbf.CompressedBloomFilter(2048, 5)
            for i in range(300):
                bloom.add(f"d-{i % 40}")
            return bloom

        a = build()
        b = build()
        for i in range(40):
            key = f"d-{i}"
            self.assertEqual(a.contains(key), b.contains(key))
        self.assertEqual(a.bit_count(), b.bit_count())
        self.assertEqual(a.byte_count(), b.byte_count())
        self.assertEqual(a.hash_count(), b.hash_count())

    def test_zero_bit_count_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            rust_cbf.CompressedBloomFilter(0, 5)

    def test_zero_hashes_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            rust_cbf.CompressedBloomFilter(16, 0)


if __name__ == "__main__":
    unittest.main()
