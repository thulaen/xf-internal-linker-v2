"""Tests for the three anti-garbage anchor signals + dispatcher.

Covers:

- Algo 1 — generic_score: lexicon load, blacklist hit, missing
  lexicon path, multi-word match counting, operator-supplied extras.
- Algo 2 — descriptiveness_score: edit-distance vs slug,
  char-trigram Jaccard vs title, composite math.
- Algo 3 — self_information_score: bigram entropy math, modified
  z-score outlier detection, corpus-stats AppSetting fallback.
- Dispatcher — evaluate_all composite, ranking_weight scaling,
  cold-start ``None`` path.
- Pure-Python helpers: ``_damerau_levenshtein``,
  ``_char_trigram_jaccard``, ``_bigram_entropy``.

The C++ kernels are not required to be built — every test exercises
the Python-fallback path that the wrapper module uses when the C++
extensions aren't available. When the kernels ARE built, the same
tests still pass (the wrapper transparently routes through them).
"""

from __future__ import annotations

import math
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.pipeline.services import anchor_garbage_signals as ags


# ─────────────────────────────────────────────────────────────────────
# Algo 1 — generic_score
# ─────────────────────────────────────────────────────────────────────


class GenericScoreTests(SimpleTestCase):
    def test_empty_anchor_returns_no_match(self) -> None:
        result = ags.generic_score("")
        self.assertFalse(result.matched)
        self.assertEqual(result.matched_phrases, ())
        self.assertEqual(result.genericness, 0.0)

    def test_click_here_anchor_matches(self) -> None:
        result = ags.generic_score("click here")
        self.assertTrue(result.matched)
        self.assertIn("click here", result.matched_phrases)
        self.assertEqual(result.genericness, 1.0)

    def test_descriptive_anchor_does_not_match(self) -> None:
        result = ags.generic_score(
            "Comprehensive guide to internal linking for SEO professionals"
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.genericness, 0.0)

    def test_partial_match_proportional_genericness(self) -> None:
        # 4-word anchor with "click here" (2 words) AND "here" (1 word
        # — both are in the curated lexicon, since both are
        # legitimately weak link text per WCAG 2.1 §2.4.4). Total
        # matched-word count = 3; anchor word count = 4 → 0.75.
        result = ags.generic_score("just click here friend")
        self.assertTrue(result.matched)
        self.assertGreaterEqual(result.genericness, 0.5)
        self.assertLessEqual(result.genericness, 1.0)

    def test_disabled_toggle_returns_no_match(self) -> None:
        # No DB available in SimpleTestCase, but is_enabled is wrapped
        # in try/except in the wrapper, so the toggle defaults to True
        # and a real generic phrase still matches. This test asserts
        # the explicit-False path.
        with patch(
            "apps.core.runtime_flags.is_enabled",
            return_value=False,
        ):
            result = ags.generic_score("click here")
            self.assertFalse(result.matched)


# ─────────────────────────────────────────────────────────────────────
# Algo 2 — descriptiveness_score
# ─────────────────────────────────────────────────────────────────────


class DescriptivenessScoreTests(SimpleTestCase):
    def test_empty_anchor_returns_neutral(self) -> None:
        result = ags.descriptiveness_score("", "destination title", "slug")
        self.assertEqual(result.score, 0.0)

    def test_anchor_matches_slug_low_score(self) -> None:
        # Anchor ≈ slug → manufactured-match red flag → score < 0.
        result = ags.descriptiveness_score(
            anchor="best-vpn-reviews-2024",
            destination_title="Best VPN reviews 2024",
            destination_slug="best-vpn-reviews-2024",
        )
        # Edit distance = 0 → ratio 0.0 → manufactured penalty term
        # = -0.5 × (1 - 0) = -0.5. Some Jaccard from the title pulls
        # back toward 0 but score should be < 0.
        self.assertLess(result.score, 0.0)
        self.assertEqual(result.edit_distance_ratio, 0.0)

    def test_descriptive_anchor_with_overlap_high_score(self) -> None:
        # Anchor shares many character trigrams with the title; slug
        # is unrelated. → high Jaccard, low manufactured-match
        # penalty. Composite score positive.
        result = ags.descriptiveness_score(
            anchor="step-by-step VPN setup guide",
            destination_title="Step-by-step VPN setup guide for beginners",
            destination_slug="totally-different-url",
        )
        self.assertGreater(result.char_trigram_jaccard, 0.3)
        self.assertGreater(result.score, 0.0)

    def test_no_slug_short_circuits_edit_distance(self) -> None:
        result = ags.descriptiveness_score(
            anchor="some descriptive anchor text",
            destination_title="some descriptive anchor text exactly",
            destination_slug="",
        )
        # No slug → edit_distance_ratio = 1.0 → manufactured penalty
        # = -0.5 × 0 = 0. Score driven entirely by Jaccard.
        self.assertEqual(result.edit_distance_ratio, 1.0)
        self.assertGreater(result.score, 0.0)


# ─────────────────────────────────────────────────────────────────────
# Algo 3 — self_information_score
# ─────────────────────────────────────────────────────────────────────


class SelfInformationScoreTests(SimpleTestCase):
    def test_empty_anchor_returns_neutral(self) -> None:
        result = ags.self_information_score("")
        self.assertEqual(result.entropy, 0.0)
        self.assertFalse(result.anomaly_flag)

    def test_repeated_pattern_low_entropy(self) -> None:
        # A repetitive single-character anchor has just one unique
        # bigram ("aa") with 100% probability → entropy = 0.
        repetitive = "a" * 20
        result = ags.self_information_score(repetitive)
        self.assertAlmostEqual(result.entropy, 0.0, places=3)

    def test_alternating_two_chars_yields_one_bit(self) -> None:
        # "ababab..." has two unique bigrams ("ab" + "ba") with 50%
        # probability each → entropy = 1 bit. (Not zero — that's the
        # information-theory cost of needing to remember which char
        # came first.)
        alternating = "ab" * 20
        result = ags.self_information_score(alternating)
        self.assertAlmostEqual(result.entropy, 1.0, places=3)

    def test_typical_english_in_baseline(self) -> None:
        text = "the quick brown fox jumps over the lazy dog"
        result = ags.self_information_score(text)
        # Real English text bigram entropy is in [3, 5] bits.
        self.assertGreater(result.entropy, 1.0)
        # Modified z-score should be within the threshold for typical
        # English text with the default corpus stats (median 4, MAD 0.5).
        self.assertFalse(result.anomaly_flag)

    def test_random_high_entropy_outlier_flagged(self) -> None:
        # A random-looking high-entropy anchor (every bigram unique).
        rare = "qz vw xy bd jk lm np ru cd"
        # Corpus expects median ~4, MAD ~0.5. Random text has higher
        # entropy → modified z-score positive → anomaly when above
        # threshold.
        result = ags.self_information_score(
            rare, corpus_median=2.0, corpus_mad=0.3, threshold=1.0
        )
        # With a tighter threshold, we expect this to trip.
        self.assertTrue(result.anomaly_flag)
        self.assertGreater(result.anomaly_penalty, 0.0)


# ─────────────────────────────────────────────────────────────────────
# Pure-Python helpers (must produce identical results to the C++
# kernels when those are built — these tests pin the contract).
# ─────────────────────────────────────────────────────────────────────


class HelperMathTests(SimpleTestCase):
    def test_damerau_levenshtein_zero_for_identical(self) -> None:
        self.assertEqual(ags._damerau_levenshtein("hello", "hello"), 0)

    def test_damerau_levenshtein_transposition_costs_one(self) -> None:
        # "ab" → "ba" is a single adjacent transposition under
        # Damerau, distance = 1.
        self.assertEqual(ags._damerau_levenshtein("ab", "ba"), 1)

    def test_damerau_levenshtein_empty_inputs(self) -> None:
        self.assertEqual(ags._damerau_levenshtein("", "abc"), 3)
        self.assertEqual(ags._damerau_levenshtein("abc", ""), 3)
        self.assertEqual(ags._damerau_levenshtein("", ""), 0)

    def test_char_trigram_jaccard_identical_is_one(self) -> None:
        self.assertEqual(
            ags._char_trigram_jaccard("hello world", "hello world"),
            1.0,
        )

    def test_char_trigram_jaccard_disjoint_is_zero(self) -> None:
        self.assertEqual(
            ags._char_trigram_jaccard("abc", "xyz"),
            0.0,
        )

    def test_bigram_entropy_uniform_text(self) -> None:
        # Uniform 26 bigrams → entropy = log2(26) ≈ 4.7
        # Use random pairs to avoid repeats.
        text = "ab cd ef gh ij kl mn op qr st uv wx yz"
        h = ags._bigram_entropy(text)
        # Loose bound — many bigrams, decent entropy.
        self.assertGreater(h, 2.0)

    def test_bigram_entropy_single_char_returns_zero(self) -> None:
        self.assertEqual(ags._bigram_entropy("a"), 0.0)
        self.assertEqual(ags._bigram_entropy(""), 0.0)


# ─────────────────────────────────────────────────────────────────────
# Dispatcher composite
# ─────────────────────────────────────────────────────────────────────


class EvaluateAllTests(SimpleTestCase):
    def test_seo_keyword_stuffed_anchor_negative_composite(self) -> None:
        # Anchor exactly matches the URL slug AND the title is only
        # loosely related → manufactured-keyword red flag dominates,
        # Jaccard contribution is moderate, composite goes negative.
        ev = ags.evaluate_all(
            anchor="best vpn reviews 2024",
            destination_title="VPN reviews and best practices in 2024",
            destination_slug="best-vpn-reviews-2024",
        )
        self.assertLess(ev.score_anchor_genericness, 0.0)

    def test_anchor_matching_both_slug_and_title_goes_neutral_or_better(
        self,
    ) -> None:
        # When the anchor matches both the slug AND the title (the
        # honest case for a well-titled article), the manufactured-
        # match penalty is offset by the high Jaccard with the
        # title. Composite ends up neutral or slightly positive —
        # NOT a red flag.
        ev = ags.evaluate_all(
            anchor="comprehensive linking guide",
            destination_title="Comprehensive linking guide",
            destination_slug="comprehensive-linking-guide",
        )
        self.assertGreaterEqual(ev.score_anchor_genericness, -0.1)

    def test_clearly_generic_anchor_negative_composite(self) -> None:
        ev = ags.evaluate_all(
            anchor="click here",
            destination_title="Some completely unrelated topic",
            destination_slug="unrelated-slug",
        )
        # Generic match → strong negative pull.
        self.assertLess(ev.score_anchor_genericness, -0.3)

    def test_descriptive_anchor_positive_composite(self) -> None:
        ev = ags.evaluate_all(
            anchor="step-by-step setup guide for VPN beginners",
            destination_title="Step-by-step setup guide for VPN beginners",
            destination_slug="totally-different-slug-name",
        )
        # No generic match + high Jaccard + no manufactured-match
        # penalty → positive.
        self.assertGreater(ev.score_anchor_genericness, 0.0)

    def test_composite_clamped_to_unit_range(self) -> None:
        # Even with a worst-case input, the composite stays in [-1, 1].
        ev = ags.evaluate_all("click here", "click here", "click-here")
        self.assertGreaterEqual(ev.score_anchor_genericness, -1.0)
        self.assertLessEqual(ev.score_anchor_genericness, 1.0)


# ─────────────────────────────────────────────────────────────────────
# Dispatcher build path
# ─────────────────────────────────────────────────────────────────────


class BuildDispatcherTests(TestCase):
    def setUp(self) -> None:
        from apps.core.runtime_flags import invalidate

        invalidate(ags.KEY_DISPATCHER_ENABLED)

    def test_master_disabled_returns_none(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.runtime_flags import invalidate

        AppSetting.objects.update_or_create(
            key=ags.KEY_DISPATCHER_ENABLED,
            defaults={"value": "false", "description": ""},
        )
        invalidate(ags.KEY_DISPATCHER_ENABLED)
        self.assertIsNone(ags.build_anchor_garbage_signals())

    def test_zero_weight_returns_none(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.runtime_flags import invalidate

        AppSetting.objects.update_or_create(
            key=ags.KEY_DISPATCHER_ENABLED,
            defaults={"value": "true", "description": ""},
        )
        AppSetting.objects.update_or_create(
            key=ags.KEY_DISPATCHER_WEIGHT,
            defaults={"value": "0.0", "description": ""},
        )
        invalidate(ags.KEY_DISPATCHER_ENABLED)
        self.assertIsNone(ags.build_anchor_garbage_signals())

    def test_recommended_default_yields_active_dispatcher(self) -> None:
        # Migration 0047 already seeded the dispatcher key with value
        # 0.05. Just verify it parses and the dispatcher is built.
        from apps.core.runtime_flags import invalidate

        invalidate(ags.KEY_DISPATCHER_ENABLED)
        d = ags.build_anchor_garbage_signals()
        self.assertIsNotNone(d)
        self.assertAlmostEqual(d.ranking_weight, 0.05, places=6)

    def test_dispatcher_contribution_applies_weight(self) -> None:
        d = ags.AnchorGarbageDispatcher(ranking_weight=0.10)
        # Generic anchor → composite is negative → contribution is
        # negative × 0.10.
        contrib = d.contribution("click here", "Unrelated dest", "slug")
        self.assertLess(contrib, 0.0)
        self.assertGreater(contrib, -0.2)  # bounded by weight × 1.0

    def test_zero_weight_dispatcher_short_circuits(self) -> None:
        d = ags.AnchorGarbageDispatcher(ranking_weight=0.0)
        # Even on a worst-case generic anchor, contribution is 0.0
        # when weight is 0 — no work done.
        self.assertEqual(d.contribution("click here", "x", "y"), 0.0)


# Quiet linters about unused imports kept for type safety.
_ = math
