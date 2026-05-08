"""Tests for the pure-function helpers extracted from pipeline/tasks.py.

These helpers replaced ~1000 lines of inlined try/except/return boilerplate
across 14 long functions. Each helper is small and testable in
``SimpleTestCase`` (no DB), so a future tweak to threshold values or
short-circuit semantics shows up here before it ships.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.pipeline.tasks import (
    _build_standard_purge_specs,
    _decide_challenger_promotion,
    _evaluate_gsc_spike,
    _gsc_spike_setup,
    _MIN_PRE_CLICKS_FOR_ROLLBACK,
    _OPTIMISER_COVERAGE_NOTE,
    _read_checkpoint_pk,
    _record_challenger_rejection,
    _REGRESSION_THRESHOLD,
    _retention_progress_reporter,
)


class RetentionProgressReporterTests(SimpleTestCase):
    """Verify the wrapped reporter is no-op-on-error."""

    def test_no_callback_means_no_op(self):
        report = _retention_progress_reporter(None)
        # Should not raise — silently noops.
        report(0.5, "halfway")

    def test_callback_invoked(self):
        calls = []
        report = _retention_progress_reporter(lambda pct, msg: calls.append((pct, msg)))
        report(0.5, "halfway")
        self.assertEqual(calls, [(0.5, "halfway")])

    def test_callback_failure_does_not_propagate(self):
        def _boom(pct, msg):
            raise RuntimeError("callback exploded")

        report = _retention_progress_reporter(_boom)
        # Caller must not crash even if callback raises.
        report(0.5, "halfway")


class BuildStandardPurgeSpecsTests(TestCase):
    """Verify the retention spec table is well-formed.

    Uses Django TestCase because the spec list imports model classes that
    require Django's app registry to be ready.
    """

    def test_spec_count_and_required_keys(self):
        from django.utils import timezone

        specs = _build_standard_purge_specs(timezone.now())
        self.assertEqual(
            len(specs), 7
        )  # SearchMetric, PipelineRun, Suggestion-superseded, AuditEntry, ErrorLog, WebhookReceipt, CrawlerVisit
        required_keys = {
            "model_cls",
            "cutoff_field",
            "cutoff",
            "result_key",
            "label",
            "step",
            "fix_hint",
        }
        for spec in specs:
            missing = required_keys - set(spec.keys())
            self.assertFalse(
                missing,
                msg=f"spec {spec.get('label')} missing keys: {missing}",
            )

    def test_each_spec_has_unique_result_key(self):
        from django.utils import timezone

        specs = _build_standard_purge_specs(timezone.now())
        keys = [s["result_key"] for s in specs]
        self.assertEqual(
            len(keys),
            len(set(keys)),
            msg="duplicate result_keys would clobber the results dict",
        )


class GscSpikeSetupTests(TestCase):
    """Verify the GSC spike setup pulls thresholds + computes the right windows."""

    def test_windows_are_3day_recent_and_7day_baseline(self):
        from datetime import timedelta

        thresholds, today, recent, baseline = _gsc_spike_setup()
        # Recent: yesterday back 2 days = 3-day window
        self.assertEqual((recent[1] - recent[0]).days, 2)
        # Baseline: 7-day window ending the day before recent_start
        self.assertEqual((baseline[1] - baseline[0]).days, 6)
        self.assertEqual(baseline[1] + timedelta(days=1), recent[0])

    def test_default_thresholds(self):
        thresholds, _, _, _ = _gsc_spike_setup()
        self.assertEqual(thresholds["min_impressions_delta"], 50)
        self.assertEqual(thresholds["min_clicks_delta"], 5)
        self.assertEqual(thresholds["min_relative_lift"], 0.5)


class EvaluateGscSpikeTests(SimpleTestCase):
    """Verify the spike-evaluation rules."""

    def setUp(self):
        self.thresholds = {
            "min_impressions_delta": 50,
            "min_clicks_delta": 5,
            "min_relative_lift": 0.5,
        }

    def test_no_baseline_returns_none(self):
        result = _evaluate_gsc_spike(
            {"avg_impressions": 100, "avg_clicks": 10},
            {"avg_impressions": 0, "avg_clicks": 0},
            self.thresholds,
        )
        self.assertIsNone(result)

    def test_below_threshold_returns_none(self):
        result = _evaluate_gsc_spike(
            {"avg_impressions": 110, "avg_clicks": 11},  # +10 imp, +1 clk
            {"avg_impressions": 100, "avg_clicks": 10},
            self.thresholds,
        )
        self.assertIsNone(result)

    def test_impressions_spike_returns_diagnostics(self):
        result = _evaluate_gsc_spike(
            {"avg_impressions": 200, "avg_clicks": 10},  # +100 imp, 100% lift
            {"avg_impressions": 100, "avg_clicks": 10},
            self.thresholds,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["imp_delta"], 100)
        self.assertEqual(result["imp_lift"], 1.0)

    def test_clicks_spike_alone_triggers(self):
        result = _evaluate_gsc_spike(
            {"avg_impressions": 100, "avg_clicks": 20},  # +0 imp, +10 clk (100%)
            {"avg_impressions": 100, "avg_clicks": 10},
            self.thresholds,
        )
        self.assertIsNotNone(result)


class ChallengerPromotionTests(SimpleTestCase):
    """Verify the SPRT-driven challenger decision logic."""

    def test_null_scores_auto_promote(self):
        challenger = mock.Mock(
            predicted_quality_score=None,
            champion_quality_score=None,
        )
        decision = _decide_challenger_promotion(challenger, "run-x")
        self.assertTrue(decision["should_promote"])
        self.assertEqual(decision["decision"], "auto")

    def test_score_pair_returns_decision(self):
        # SPRT with a single observation typically returns "continue" (needs
        # more samples to converge); only auto-promote bypasses SPRT entirely.
        # Test that the decision shape is correct, not the specific outcome.
        challenger = mock.Mock(
            predicted_quality_score=0.85,
            champion_quality_score=0.70,
        )
        decision = _decide_challenger_promotion(challenger, "run-x")
        self.assertIn(decision["decision"], {"promote", "reject", "continue"})
        self.assertEqual(decision["should_promote"], decision["decision"] == "promote")

    def test_score_pair_does_not_auto_promote(self):
        # When both scores are present, the decision MUST come from SPRT (not auto).
        challenger = mock.Mock(
            predicted_quality_score=0.55,
            champion_quality_score=0.70,
        )
        decision = _decide_challenger_promotion(challenger, "run-x")
        self.assertNotEqual(decision["decision"], "auto")


class ChallengerRejectionTests(SimpleTestCase):
    """Verify the rejection record + payload."""

    def test_rejection_payload_includes_coverage_note(self):
        challenger = mock.Mock(
            run_id="run-x",
            status="pending",
            updated_at=None,
        )
        challenger.save = mock.Mock()
        decision = {
            "should_promote": False,
            "decision": "reject",
            "cand_score": 0.55,
            "champ_score": 0.70,
        }
        result = _record_challenger_rejection(challenger, "run-x", decision)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["coverage_note"], _OPTIMISER_COVERAGE_NOTE)
        challenger.save.assert_called_once_with(update_fields=["status", "updated_at"])
        self.assertEqual(challenger.status, "rejected")


class CheckpointReadTests(TestCase):
    """Verify the AppSetting checkpoint reader."""

    def setUp(self):
        from apps.core.models import AppSetting

        AppSetting.objects.filter(key__startswith="test.checkpoint.").delete()

    def test_missing_key_returns_zero(self):
        self.assertEqual(_read_checkpoint_pk("test.checkpoint.missing"), 0)

    def test_integer_value_parsed(self):
        from apps.core.models import AppSetting

        AppSetting.objects.create(
            key="test.checkpoint.x",
            value="42",
            value_type="int",
        )
        self.assertEqual(_read_checkpoint_pk("test.checkpoint.x"), 42)

    def test_non_integer_falls_back_to_zero(self):
        from apps.core.models import AppSetting

        AppSetting.objects.create(
            key="test.checkpoint.bad",
            value="not-a-number",
            value_type="str",
        )
        self.assertEqual(_read_checkpoint_pk("test.checkpoint.bad"), 0)


class RegressionThresholdTests(SimpleTestCase):
    """Sanity: rollback threshold is in the documented 0–1 range."""

    def test_threshold_is_in_unit_interval(self):
        self.assertGreater(_REGRESSION_THRESHOLD, 0.0)
        self.assertLess(_REGRESSION_THRESHOLD, 1.0)

    def test_min_pre_clicks_positive(self):
        self.assertGreater(_MIN_PRE_CLICKS_FOR_ROLLBACK, 0)
