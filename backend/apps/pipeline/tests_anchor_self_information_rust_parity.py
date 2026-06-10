"""Contract tests for the Rust ``extensions.anchor_self_information`` module.

The Rust kernel is the byte-bigram entropy implementation that replaces the
old native extension. ASCII text has the same byte and character bigrams, so it
must match a direct reference calculation. Non-ASCII text is different on
purpose: the old native extension counted UTF-8 bytes, and the Rust port keeps
that persisted corpus-statistics contract.

Skipped when the Rust module is not built and staged yet. The compiled-artifact
builder is what turns these from skipped checks into executed checks.
"""

from __future__ import annotations

import math
import unittest

try:
    from extensions import anchor_self_information as rust_self_info

    _HAS_ANCHOR_SELF_INFORMATION = hasattr(rust_self_info, "bigram_entropy")
except ImportError:
    _HAS_ANCHOR_SELF_INFORMATION = False

_TOL = 1e-9


def _byte_bigram_entropy_reference(text: str) -> float:
    """Independent byte-bigram entropy reference for the Rust contract."""
    data = text.encode("utf-8")
    if len(data) < 2:
        return 0.0
    counts: dict[int, int] = {}
    total = 0
    for i in range(len(data) - 1):
        key = (data[i] << 8) | data[i + 1]
        counts[key] = counts.get(key, 0) + 1
        total += 1
    entropy = 0.0
    inv_total = 1.0 / total
    for count in counts.values():
        p = count * inv_total
        entropy -= p * math.log2(p)
    return entropy


def _character_bigram_entropy_reference(text: str) -> float:
    """Small character-bigram reference used to prove the non-ASCII split."""
    if len(text) < 2:
        return 0.0
    counts: dict[str, int] = {}
    total = 0
    for i in range(len(text) - 1):
        bigram = text[i : i + 2]
        counts[bigram] = counts.get(bigram, 0) + 1
        total += 1
    entropy = 0.0
    inv_total = 1.0 / total
    for count in counts.values():
        p = count * inv_total
        entropy -= p * math.log2(p)
    return entropy


@unittest.skipUnless(
    _HAS_ANCHOR_SELF_INFORMATION,
    "Rust extensions.anchor_self_information not built/staged yet.",
)
class RustAnchorSelfInformationContractTests(unittest.TestCase):
    """Python-facing contract for ``bigram_entropy(text)``."""

    def test_ascii_samples_match_byte_reference(self) -> None:
        samples = ["", "a", "aa", "abc", "aaab", "the quick brown fox"]
        for sample in samples:
            with self.subTest(sample=sample):
                expected = _byte_bigram_entropy_reference(sample)
                actual = rust_self_info.bigram_entropy(sample)
                self.assertAlmostEqual(actual, expected, delta=_TOL)

    def test_multibyte_utf8_counts_bytes_not_characters(self) -> None:
        text = "\u20aca"

        actual = rust_self_info.bigram_entropy(text)

        self.assertAlmostEqual(actual, math.log2(3), delta=_TOL)
        self.assertAlmostEqual(
            actual,
            _byte_bigram_entropy_reference(text),
            delta=_TOL,
        )
        self.assertEqual(_character_bigram_entropy_reference(text), 0.0)

    def test_keyword_text_argument_matches_old_native_api(self) -> None:
        self.assertAlmostEqual(
            rust_self_info.bigram_entropy(text="abc"),
            1.0,
            delta=_TOL,
        )


if __name__ == "__main__":
    unittest.main()
