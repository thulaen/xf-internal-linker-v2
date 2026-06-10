"""Contract tests: the Rust ``extensions.counting_bloom`` kernel.

The Rust kernel (``rust/extensions/counting_bloom``, built to
``counting_bloom.so`` and staged at ``/opt/xf/compiled/active/extensions/``) is
the SOLE implementation of the counting Bloom filter. The C++ kernel
(``backend/extensions/counting_bloom.cpp``) was ported away (RUST-FIRST.md
zero-fallback / dead-code-on-replace).

There is NO byte-for-byte parity with the old C++ counter-to-index mapping, and
that is deliberate: the C++ kernel indexed counters with
``std::hash<std::string>``, which is libstdc++-implementation-defined, so the
exact mapping was never a portable contract. A repository-wide search found zero
Python callers of ``add``/``remove``/``contains``, so no caller depends on
specific hash outputs.

These tests therefore assert the counting Bloom filter BEHAVIOURAL contract
(Fan, Cao, Almeida & Broder 2000, doi:10.1109/90.851975; Bloom 1970,
doi:10.1145/362686.362692), not C++ value equality:

1. No false negatives — a net-present item (``add`` with no balancing
   ``remove``) is always ``contains``-true.
2. Deletion support — ``add`` then balancing ``remove`` of a collision-free key
   returns ``contains`` to false.
3. Saturating increment — adding past ``u16::MAX`` (65535) never wraps to a
   false negative.
4. Flooring decrement — ``remove`` of a never-added item is a safe no-op (no
   underflow).
5. An unseen / never-touched item is not contained.
6. Determinism — identical construction + insert stream yields identical
   ``contains`` / ``counter_count`` / ``hash_count`` across two filters.
7. Accessors — ``counter_count()`` / ``hash_count()`` echo the constructor.
8. Guard — ``CountingBloomFilter(0, h)`` / ``CountingBloomFilter(c, 0)`` raise
   ``ValueError``.

Skipped (not failed) when the Rust ``.so`` is not built/staged yet, so the suite
stays green on a host that has not run the compiled-artifacts build. The
build-and-wire step (``scripts/ensure_compiled_artifacts.py``) is what flips
this from skipped to executed.

Source for the semantics: ``docs/specs/pick-100-counting-bloom.md`` and the
counting Bloom filter papers cited there.
"""

from __future__ import annotations

import unittest

try:
    from extensions import counting_bloom as rust_cbf

    _HAS_CBF = hasattr(rust_cbf, "CountingBloomFilter")
except ImportError:
    _HAS_CBF = False


@unittest.skipUnless(
    _HAS_CBF,
    "Rust extensions.counting_bloom not built/staged yet — run "
    "scripts/ensure_compiled_artifacts.py in the compiled-tools image.",
)
class RustCountingBloomContractTests(unittest.TestCase):
    """Behavioural-contract tests for the Rust counting Bloom filter kernel."""

    def test_unseen_item_is_not_contained(self) -> None:
        bloom = rust_cbf.CountingBloomFilter(2048, 5)
        self.assertFalse(bloom.contains("never-added"))

    def test_added_item_is_contained_no_false_negative(self) -> None:
        bloom = rust_cbf.CountingBloomFilter(4096, 5)
        bloom.add("alpha")
        self.assertTrue(bloom.contains("alpha"))

    def test_no_false_negatives_for_many_added_keys(self) -> None:
        bloom = rust_cbf.CountingBloomFilter(1 << 16, 4)
        for i in range(5000):
            bloom.add(f"key-{i}")
        for i in range(5000):
            self.assertTrue(
                bloom.contains(f"key-{i}"),
                f"false negative for key-{i}",
            )

    def test_add_then_balanced_remove_returns_toward_absent(self) -> None:
        # Wide table -> collision-free -> balanced remove clears the key.
        bloom = rust_cbf.CountingBloomFilter(1 << 16, 4)
        bloom.add("solo")
        self.assertTrue(bloom.contains("solo"))
        bloom.remove("solo")
        self.assertFalse(bloom.contains("solo"))

    def test_remove_of_never_added_is_safe_noop(self) -> None:
        # Flooring decrement: removing an unseen key must not underflow/corrupt
        # the table; a freshly added key is still found.
        bloom = rust_cbf.CountingBloomFilter(1 << 16, 4)
        bloom.remove("ghost")
        self.assertFalse(bloom.contains("ghost"))
        bloom.add("real")
        self.assertTrue(bloom.contains("real"))

    def test_duplicate_remove_does_not_underflow(self) -> None:
        bloom = rust_cbf.CountingBloomFilter(1 << 16, 4)
        bloom.add("once")
        bloom.remove("once")
        bloom.remove("once")  # second remove must floor at 0, not wrap
        self.assertFalse(bloom.contains("once"))
        bloom.add("other")
        self.assertTrue(bloom.contains("other"))
        bloom.remove("other")
        self.assertFalse(bloom.contains("other"))

    def test_saturating_add_does_not_wrap_to_false_negative(self) -> None:
        # Single counter, single hash, add far past u16::MAX. Saturating add
        # pins at the max; a wrapping add would cycle through 0 (false negative).
        bloom = rust_cbf.CountingBloomFilter(1, 1)
        for _ in range(70000):
            bloom.add("alpha")
        self.assertTrue(bloom.contains("alpha"))
        bloom.remove("alpha")  # 65535 -> 65534, still present
        self.assertTrue(bloom.contains("alpha"))

    def test_unicode_key_round_trips(self) -> None:
        bloom = rust_cbf.CountingBloomFilter(1 << 16, 4)
        bloom.add("日本語-mañana-🚀")
        self.assertTrue(bloom.contains("日本語-mañana-🚀"))
        self.assertFalse(bloom.contains("日本語-mañana-🛸"))

    def test_empty_string_key_is_supported(self) -> None:
        bloom = rust_cbf.CountingBloomFilter(1 << 16, 4)
        self.assertFalse(bloom.contains(""))
        bloom.add("")
        self.assertTrue(bloom.contains(""))

    def test_is_deterministic(self) -> None:
        def build() -> object:
            bloom = rust_cbf.CountingBloomFilter(2048, 5)
            for i in range(300):
                bloom.add(f"d-{i % 40}")
            return bloom

        a = build()
        b = build()
        for i in range(40):
            key = f"d-{i}"
            self.assertEqual(a.contains(key), b.contains(key))
        self.assertEqual(a.counter_count(), b.counter_count())
        self.assertEqual(a.hash_count(), b.hash_count())

    def test_counter_count_and_hash_count_echo_constructor(self) -> None:
        bloom = rust_cbf.CountingBloomFilter(1234, 7)
        self.assertEqual(bloom.counter_count(), 1234)
        self.assertEqual(bloom.hash_count(), 7)

    def test_zero_counters_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            rust_cbf.CountingBloomFilter(0, 5)

    def test_zero_hashes_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            rust_cbf.CountingBloomFilter(16, 0)


if __name__ == "__main__":
    unittest.main()
