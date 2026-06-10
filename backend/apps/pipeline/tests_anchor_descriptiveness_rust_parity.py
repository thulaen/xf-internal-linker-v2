"""Parity tests: the Rust `extensions.anchor_descriptiveness` kernel vs the
pure-Python oracle.

The Rust kernel (`rust/extensions/anchor_descriptiveness`, built to
`anchor_descriptiveness.so` and staged at
`/opt/xf/compiled/active/extensions/`) is the SOLE native implementation of the
two anchor-descriptiveness hot paths that
`apps.pipeline.services.anchor_garbage_signals` calls:
``damerau_levenshtein`` (Damerau-Levenshtein edit distance with adjacent
transposition, Damerau 1964) and ``char_trigram_jaccard`` (Jaccard resemblance
over 3-byte character n-grams, Broder 1997). The C++
``anchor_descriptiveness`` kernel (`backend/extensions/anchor_descriptiveness.cpp`
+ its fuzz harness, plus the anchor_descriptiveness pieces of the shared
benchmark) was deleted when this Rust kernel landed (RUST-FIRST.md
zero-fallback / dead-code-on-replace).

The byte-parity oracle is the pure-Python reference kept in
``anchor_garbage_signals.py``: ``_damerau_levenshtein_py`` and
``_char_trigram_jaccard_py`` implement the authoritative behaviour. The parity
basis for this kernel is EXACT for ASCII inputs (deterministic integer DP and a
single deterministic int/int division, no hashing-dependent output), so these
tests assert exact equality between the Rust kernel and the Python reference.

For multi-byte Unicode the Rust kernel (like the deleted C++ kernel) operates on
UTF-8 BYTES, while the pure-Python reference slices by code point, so the two
paths intentionally diverge there. Those cases assert the BYTE semantics
directly, matching the native authority being replaced.

Skipped (not failed) when the Rust ``.so`` is not built/staged yet, so the suite
stays green on a host that has not run the compiled-artifacts build.
"""

from __future__ import annotations

import random
import unittest

from apps.pipeline.services import anchor_garbage_signals as ags

try:
    from extensions import anchor_descriptiveness as rust_descr

    _HAS_DESCR = hasattr(rust_descr, "damerau_levenshtein") and hasattr(
        rust_descr, "char_trigram_jaccard"
    )
except ImportError:
    _HAS_DESCR = False


# Hand-picked ASCII pairs exercising every branch: identity, empty inputs,
# substitution, insertion/deletion, adjacent transposition, whitespace collapse,
# sub-trigram strings, and partial trigram overlap.
_ASCII_PAIRS = [
    ("", ""),
    ("", "abc"),
    ("abc", ""),
    ("hello", "hello"),
    ("ab", "ba"),
    ("cat", "cot"),
    ("cat", "cart"),
    ("kitten", "sitting"),
    ("abcd", "abdc"),
    ("hello world", "hello  world"),
    ("a  b", "a b"),
    ("ab", "ab"),
    ("ab", "cd"),
    ("abcd", "abce"),
    ("the quick brown fox", "the quick brown box"),
    ("plugin settings", "plug in settings"),
]


@unittest.skipUnless(
    _HAS_DESCR,
    "Rust extensions.anchor_descriptiveness not built/staged yet — run "
    "scripts/ensure_compiled_artifacts.py in the compiled-tools image.",
)
class RustAnchorDescriptivenessParityTests(unittest.TestCase):
    """Exact parity of the Rust kernel against the Python reference (ASCII)."""

    def test_damerau_matches_python_reference_on_fixed_pairs(self) -> None:
        for a, b in _ASCII_PAIRS:
            with self.subTest(a=a, b=b):
                self.assertEqual(
                    int(rust_descr.damerau_levenshtein(a, b)),
                    ags._damerau_levenshtein_py(a, b),
                )

    def test_jaccard_matches_python_reference_on_fixed_pairs(self) -> None:
        for a, b in _ASCII_PAIRS:
            with self.subTest(a=a, b=b):
                # Exact f64 equality: both compute the same int/int division.
                self.assertEqual(
                    float(rust_descr.char_trigram_jaccard(a, b)),
                    ags._char_trigram_jaccard_py(a, b),
                )

    def test_damerau_and_jaccard_match_reference_on_random_ascii(self) -> None:
        rng = random.Random(20260607)
        alphabet = "abcdefghijklmnopqrstuvwxyz  "
        for _ in range(500):
            a = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 14)))
            b = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 14)))
            with self.subTest(a=a, b=b):
                self.assertEqual(
                    int(rust_descr.damerau_levenshtein(a, b)),
                    ags._damerau_levenshtein_py(a, b),
                )
                self.assertEqual(
                    float(rust_descr.char_trigram_jaccard(a, b)),
                    ags._char_trigram_jaccard_py(a, b),
                )

    def test_damerau_keyword_arguments_keep_working(self) -> None:
        # The pybind/PyO3 signature pins the param names `a`, `b`; the caller may
        # use keyword calls, so this contract must be preserved.
        self.assertEqual(int(rust_descr.damerau_levenshtein(a="ab", b="ba")), 1)
        self.assertEqual(
            float(rust_descr.char_trigram_jaccard(a="abc", b="abc")), 1.0
        )

    def test_multibyte_unicode_uses_byte_semantics(self) -> None:
        # "é" is 2 UTF-8 bytes (0xC3 0xA9); against ASCII "e" the byte-level
        # distance is 2 (the native authority being replaced is byte-based).
        self.assertEqual(int(rust_descr.damerau_levenshtein("é", "e")), 2)

    def test_live_service_helpers_use_the_rust_kernel(self) -> None:
        # The production wrappers `_damerau_levenshtein` / `_char_trigram_jaccard`
        # now route to the Rust kernel (no Python fallback); confirm they return
        # the same value as a direct kernel call on an ASCII case.
        self.assertEqual(
            ags._damerau_levenshtein("kitten", "sitting"),
            int(rust_descr.damerau_levenshtein("kitten", "sitting")),
        )
        self.assertEqual(
            ags._char_trigram_jaccard("abcd", "abce"),
            float(rust_descr.char_trigram_jaccard("abcd", "abce")),
        )


if __name__ == "__main__":
    unittest.main()
