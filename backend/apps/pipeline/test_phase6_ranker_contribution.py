"""Tests for the Phase 6 ranker-time contribution dispatcher.

Covers the public surface in
``apps.pipeline.services.phase6_ranker_contribution``:

- ``Phase6RankerContribution.contribute_total`` aggregates weighted
  per-pick contributions.
- ``Phase6RankerContribution.per_pick_breakdown`` returns the raw
  pre-weight scores for diagnostics.
- ``build_phase6_contribution`` returns ``None`` when no pick has a
  non-zero weight (cold-start / disabled paths).
- VADER #22 adapter wires through to ``apps.sources.vader_sentiment``
  and respects the ``vader_sentiment.enabled`` AppSetting.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.pipeline.services import phase6_ranker_contribution as p6


class DispatcherSimpleTests(SimpleTestCase):
    def test_no_weights_returns_zero(self) -> None:
        c = p6.Phase6RankerContribution(weights={})
        self.assertEqual(
            c.contribute_total(host_sentence_text="x", destination_text="y"),
            0.0,
        )

    def test_zero_weight_skipped(self) -> None:
        c = p6.Phase6RankerContribution(weights={"vader_sentiment": 0.0})
        self.assertEqual(c.contribute_total(host_sentence_text="happy day"), 0.0)

    def test_unknown_pick_skipped(self) -> None:
        c = p6.Phase6RankerContribution(weights={"non_existent_pick": 1.0})
        self.assertEqual(c.contribute_total(host_sentence_text="x"), 0.0)

    def test_is_active_false_when_all_zero(self) -> None:
        c = p6.Phase6RankerContribution(weights={"vader_sentiment": 0.0})
        self.assertFalse(c.is_active)

    def test_is_active_true_with_one_nonzero(self) -> None:
        c = p6.Phase6RankerContribution(weights={"vader_sentiment": 0.5})
        self.assertTrue(c.is_active)


class VaderAdapterTests(TestCase):
    """The VADER adapter is the first wired pick — verify it produces a
    non-zero compound score for clearly-emotional input and zero for
    empty input.

    Uses ``TestCase`` (not ``SimpleTestCase``) because the adapter
    consults the ``vader_sentiment.enabled`` AppSetting via
    ``apps.core.runtime_flags.is_enabled`` — that talks to the DB and
    consults Django cache. Each test invalidates the cache to avoid
    cross-test contamination.
    """

    def setUp(self) -> None:
        from apps.core.models import AppSetting
        from apps.core.runtime_flags import invalidate

        # Make sure VADER is enabled in this test's DB and the cache
        # doesn't shadow that.
        AppSetting.objects.update_or_create(
            key="vader_sentiment.enabled",
            defaults={"value": "true", "description": ""},
        )
        invalidate("vader_sentiment.enabled")

    def test_empty_text_returns_zero(self) -> None:
        self.assertEqual(p6._vader_adapter("", ""), 0.0)
        self.assertEqual(p6._vader_adapter("", "destination irrelevant"), 0.0)

    def test_positive_text_returns_positive(self) -> None:
        from apps.sources import vader_sentiment as vs

        if not vs.HAS_VADER:
            self.skipTest("vaderSentiment not installed; adapter returns 0.0")
        self.assertGreater(
            p6._vader_adapter("This is amazing and wonderful!", ""),
            0.0,
        )

    def test_negative_text_returns_negative(self) -> None:
        from apps.sources import vader_sentiment as vs

        if not vs.HAS_VADER:
            self.skipTest("vaderSentiment not installed; adapter returns 0.0")
        self.assertLess(
            p6._vader_adapter("Terrible, awful, the worst day ever.", ""),
            0.0,
        )


class DispatcherWeightingTests(SimpleTestCase):
    """Verify the weight × adapter math without depending on real VADER."""

    def test_weight_multiplies_adapter_output(self) -> None:
        # Stub the adapter to return a known constant.
        with patch.dict(p6._ADAPTERS, {"fake_pick": lambda h, d: 0.5}):
            c = p6.Phase6RankerContribution(weights={"fake_pick": 2.0})
            self.assertAlmostEqual(
                c.contribute_total(host_sentence_text="x"),
                1.0,  # 0.5 * 2.0
                places=6,
            )

    def test_negative_weight_flips_sign(self) -> None:
        with patch.dict(p6._ADAPTERS, {"fake_pick": lambda h, d: 0.5}):
            c = p6.Phase6RankerContribution(weights={"fake_pick": -1.0})
            self.assertAlmostEqual(
                c.contribute_total(host_sentence_text="x"),
                -0.5,
                places=6,
            )

    def test_multiple_picks_sum(self) -> None:
        with patch.dict(
            p6._ADAPTERS,
            {
                "pick_a": lambda h, d: 0.3,
                "pick_b": lambda h, d: -0.2,
            },
        ):
            c = p6.Phase6RankerContribution(
                weights={"pick_a": 1.0, "pick_b": 0.5}
            )
            self.assertAlmostEqual(
                c.contribute_total(host_sentence_text="x"),
                0.3 - 0.1,  # 1.0*0.3 + 0.5*(-0.2)
                places=6,
            )

    def test_failing_adapter_does_not_crash_total(self) -> None:
        def boom(h: str, d: str) -> float:
            raise RuntimeError("simulated adapter outage")

        with patch.dict(p6._ADAPTERS, {"good": lambda h, d: 0.5, "bad": boom}):
            c = p6.Phase6RankerContribution(
                weights={"good": 1.0, "bad": 1.0}
            )
            # Bad adapter is logged and skipped; good adapter still
            # contributes.
            self.assertAlmostEqual(
                c.contribute_total(host_sentence_text="x"), 0.5, places=6
            )

    def test_per_pick_breakdown_returns_raw_unweighted_scores(self) -> None:
        with patch.dict(
            p6._ADAPTERS,
            {
                "pick_a": lambda h, d: 0.7,
                "pick_b": lambda h, d: -0.3,
            },
        ):
            c = p6.Phase6RankerContribution(
                weights={"pick_a": 100.0, "pick_b": 100.0}
            )
            breakdown = c.per_pick_breakdown(host_sentence_text="x")
            # Pre-weight raw values, NOT 100 × value.
            self.assertAlmostEqual(breakdown["pick_a"], 0.7, places=6)
            self.assertAlmostEqual(breakdown["pick_b"], -0.3, places=6)


class BuildDispatcherTests(TestCase):
    """build_phase6_contribution() reads AppSetting; needs DB.

    Each test invalidates ``runtime_flags`` cache for keys it touches
    so cross-test cache contamination doesn't leak between cases.
    """

    def _invalidate_pick_caches(self) -> None:
        from apps.core.runtime_flags import invalidate

        for pick_name in p6._ADAPTERS:
            invalidate(f"{pick_name}.enabled")

    def test_global_disabled_returns_none(self) -> None:
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=False)
        self.assertIsNone(result)

    def test_no_weights_set_returns_none(self) -> None:
        # No <pick>.ranking_weight rows in AppSetting — every pick
        # has weight 0.0 — so no contribution; helper returns None.
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=True)
        self.assertIsNone(result)

    def test_weight_picked_up_from_appsetting(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="vader_sentiment.ranking_weight",
            defaults={"value": "0.25", "description": ""},
        )
        AppSetting.objects.update_or_create(
            key="vader_sentiment.enabled",
            defaults={"value": "true", "description": ""},
        )
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=True)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.weights["vader_sentiment"], 0.25, places=6)

    def test_disabled_pick_excluded(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="vader_sentiment.ranking_weight",
            defaults={"value": "0.25", "description": ""},
        )
        AppSetting.objects.update_or_create(
            key="vader_sentiment.enabled",
            defaults={"value": "false", "description": ""},
        )
        self._invalidate_pick_caches()
        result = p6.build_phase6_contribution(enabled_global=True)
        # Only pick has its enabled flag off → dispatcher returns None.
        self.assertIsNone(result)
