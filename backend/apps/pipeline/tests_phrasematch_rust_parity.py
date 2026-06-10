"""Parity tests: the Rust `extensions.phrasematch` kernel vs a Python oracle.

The Rust kernel (`rust/extensions/phrasematch`, built to `phrasematch.so` and
staged at `/opt/xf/compiled/active/extensions/`) is the SOLE native
implementation of the longest-contiguous-overlap hot path that
`apps.pipeline.services.phrase_matching._longest_contiguous_overlap` calls. The
C++ `phrasematch` kernel (`backend/extensions/phrasematch.cpp` + its header and
fuzz harness) and the inline pure-Python fallback in `phrase_matching.py` were
both removed when this Rust kernel landed (RUST-FIRST.md zero-fallback /
dead-code-on-replace).

The parity basis is EXACT (deterministic integer / string-equality work, no
hashing, no floats), so these tests assert exact integer equality between the
Rust kernel and an independent pure-Python brute-force reference oracle, for the
10 example cases pinned in the port spec plus boundary cases.

Source of truth: FR-008 phrase-based matching (Patent US7536408B2),
docs/specs/fr008-phrase-based-matching-anchor-expansion.md.

Skipped (not failed) when the Rust ``.so`` is not built/staged yet, so the suite
stays green on a host that has not run the compiled-artifacts build.
"""

from __future__ import annotations

import unittest

try:
    from extensions import phrasematch as rust_phrasematch

    _HAS_PHRASEMATCH = hasattr(rust_phrasematch, "longest_contiguous_overlap")
except ImportError:
    _HAS_PHRASEMATCH = False


def _python_reference(left: list[str], right: list[str]) -> int:
    """Independent brute-force longest-contiguous-overlap oracle.

    Mirrors the C++/Rust kernel semantics exactly: for every pair of start
    indices, extend a counter while tokens match by exact string equality and
    both indices stay in bounds; return the maximum run length (0 when none).
    """
    best = 0
    for left_start in range(len(left)):
        for right_start in range(len(right)):
            match_len = 0
            while (
                left_start + match_len < len(left)
                and right_start + match_len < len(right)
                and left[left_start + match_len] == right[right_start + match_len]
            ):
                match_len += 1
            best = max(best, match_len)
    return best


# The 10 example cases pinned in the port spec and the existing parity test.
_EXAMPLES: list[tuple[list[str], list[str], int]] = [
    ([], [], 0),
    ([], ["a"], 0),
    (["a"], [], 0),
    (["a", "b", "c"], ["a", "b", "c"], 3),
    (["a", "b"], ["x", "y"], 0),
    (["a", "b", "c"], ["a", "b", "x"], 2),
    (["x", "a", "b", "c", "y"], ["q", "a", "b", "c", "r"], 3),
    (["x", "y", "a", "b"], ["q", "a", "b"], 2),
    (["solo"], ["solo", "pair"], 1),
    (["guide", "internal", "links"], ["internal", "links", "guide"], 2),
]

# Extra boundary cases (mutation-killing).
_BOUNDARY: list[tuple[list[str], list[str]]] = [
    (["a", "a", "a"], ["a", "a"]),  # repeats must not double-count
    (["Internal"], ["internal"]),  # exact equality, no case-folding
    (["a", "x", "p", "q", "r"], ["a", "y", "p", "q", "r"]),  # later run wins
    (["a", "b", "c", "d"], ["a", "b"]),  # bounded by shorter list
]


@unittest.skipUnless(
    _HAS_PHRASEMATCH,
    "Rust extensions.phrasematch not built/staged yet — run "
    "scripts/ensure_compiled_artifacts.py in the compiled-tools image.",
)
class RustPhraseMatchParityTests(unittest.TestCase):
    """Exact parity of the Rust kernel against the Python brute-force oracle."""

    def test_example_cases_exact_values(self) -> None:
        for left, right, expected in _EXAMPLES:
            with self.subTest(left=left, right=right):
                self.assertEqual(
                    rust_phrasematch.longest_contiguous_overlap(left, right),
                    expected,
                )

    def test_matches_python_reference_on_boundaries(self) -> None:
        for left, right in _BOUNDARY:
            with self.subTest(left=left, right=right):
                self.assertEqual(
                    rust_phrasematch.longest_contiguous_overlap(left, right),
                    _python_reference(left, right),
                )

    def test_result_is_non_negative_int_bounded(self) -> None:
        left = ["a", "b", "c", "d", "e"]
        right = ["c", "d"]
        result = rust_phrasematch.longest_contiguous_overlap(left, right)
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, min(len(left), len(right)))

    def test_live_caller_matches_reference(self) -> None:
        """The live ``phrase_matching._longest_contiguous_overlap`` == oracle.

        The caller is now Rust-only (RUST-FIRST.md zero-fallback — the old
        ``HAS_CPP_EXT`` branch and inline Python brute force were deleted). It
        must equal the independent Python reference on the example corpus.
        """
        from apps.pipeline.services import phrase_matching

        for left, right, _expected in _EXAMPLES:
            with self.subTest(left=left, right=right):
                live = phrase_matching._longest_contiguous_overlap(
                    tuple(left), tuple(right)
                )
                self.assertEqual(live, _python_reference(left, right))


if __name__ == "__main__":
    unittest.main()
