"""Contract tests: the Rust `extensions.count_min_sketch` kernel.

The Rust kernel (`rust/extensions/count_min_sketch`, built to
`count_min_sketch.so` and staged at `/opt/xf/compiled/active/extensions/`) is
the SOLE implementation of the Count-Min Sketch. The C++ kernel
(`backend/extensions/count_min_sketch.cpp`) was deleted when this Rust kernel
landed (RUST-FIRST.md zero-fallback / dead-code-on-replace).

There is NO byte-for-byte parity with the old C++ counter values, and that is
deliberate: the C++ kernel indexed rows with `std::hash<std::string>`, which is
libstdc++-implementation-defined, so the exact counter values were never a
portable contract. A repository-wide search found zero Python callers of
`add`/`estimate`, so no caller depends on specific hash outputs.

These tests therefore assert the Count-Min Sketch BEHAVIOURAL contract
(Cormode & Muthukrishnan 2005, doi:10.1016/j.jalgor.2003.12.001), not C++ value
equality:

1. ``estimate`` of an unseen item is 0.
2. ``estimate(item) >= true_count(item)`` always (the no-undercount guarantee).
3. ``estimate`` is deterministic (same inserts -> same estimates across two
   fresh sketches).
4. ``estimate`` is monotonic non-decreasing as more of the same key is added.
5. ``add(item)`` with the default count increments by 1.
6. ``width()``/``depth()`` echo the constructor values.
7. ``CountMinSketch(0, depth)`` and ``CountMinSketch(width, 0)`` raise
   ``ValueError``.
8. A heavy-hitter with a generous width/depth estimates its true count exactly.

Skipped (not failed) when the Rust `.so` is not built/staged yet, so the suite
stays green on a host that has not run the compiled-artifacts build. The
build-and-wire step (``scripts/ensure_compiled_artifacts.py``) is what flips
this from skipped to executed.

Source for the semantics: ``docs/specs/pick-97-count-min-sketch.md`` and the
Count-Min Sketch paper cited there.
"""

from __future__ import annotations

import unittest

try:
    from extensions import count_min_sketch as rust_cms

    _HAS_CMS = hasattr(rust_cms, "CountMinSketch")
except ImportError:
    _HAS_CMS = False


@unittest.skipUnless(
    _HAS_CMS,
    "Rust extensions.count_min_sketch not built/staged yet — run "
    "scripts/ensure_compiled_artifacts.py in the compiled-tools image.",
)
class RustCountMinSketchContractTests(unittest.TestCase):
    """Behavioural-contract tests for the Rust Count-Min Sketch kernel."""

    def test_unseen_item_estimates_zero(self) -> None:
        cms = rust_cms.CountMinSketch(2048, 5)
        self.assertEqual(cms.estimate("never-added"), 0)

    def test_estimate_never_undercounts_single_key(self) -> None:
        cms = rust_cms.CountMinSketch(4096, 5)
        cms.add("alpha", 7)
        self.assertGreaterEqual(cms.estimate("alpha"), 7)

    def test_estimate_never_undercounts_random_stream(self) -> None:
        import random

        rng = random.Random(20260606)
        cms = rust_cms.CountMinSketch(2048, 5)
        truth: dict[str, int] = {}
        for _ in range(8000):
            key = f"k-{rng.randrange(300)}"
            inc = rng.randrange(1, 4)
            cms.add(key, inc)
            truth[key] = truth.get(key, 0) + inc
        for key, true_count in truth.items():
            self.assertGreaterEqual(
                cms.estimate(key),
                true_count,
                f"estimate undercounted true {true_count} for {key}",
            )

    def test_estimate_is_deterministic(self) -> None:
        def build() -> object:
            cms = rust_cms.CountMinSketch(2048, 5)
            for i in range(300):
                cms.add(f"d-{i % 40}", 2)
            return cms

        a = build()
        b = build()
        for i in range(40):
            key = f"d-{i}"
            self.assertEqual(a.estimate(key), b.estimate(key))

    def test_estimate_is_monotonic_non_decreasing(self) -> None:
        cms = rust_cms.CountMinSketch(8192, 5)
        prev = 0
        for _ in range(50):
            cms.add("grow", 1)
            now = cms.estimate("grow")
            self.assertGreaterEqual(now, prev)
            prev = now

    def test_default_count_increments_by_one(self) -> None:
        cms = rust_cms.CountMinSketch(8192, 5)
        cms.add("solo")
        # Wide table -> negligible collision -> exact 1.
        self.assertEqual(cms.estimate("solo"), 1)

    def test_width_and_depth_echo_constructor(self) -> None:
        cms = rust_cms.CountMinSketch(1234, 7)
        self.assertEqual(cms.width(), 1234)
        self.assertEqual(cms.depth(), 7)

    def test_zero_width_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            rust_cms.CountMinSketch(0, 5)

    def test_zero_depth_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            rust_cms.CountMinSketch(16, 0)

    def test_heavy_hitter_exact_with_generous_table(self) -> None:
        cms = rust_cms.CountMinSketch(65536, 7)
        for _ in range(1000):
            cms.add("hot", 1)
        self.assertEqual(cms.estimate("hot"), 1000)


if __name__ == "__main__":
    unittest.main()
