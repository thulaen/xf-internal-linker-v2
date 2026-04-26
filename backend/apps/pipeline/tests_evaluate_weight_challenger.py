"""Regression tests for the FR-018 Python auto-tune Celery chain.

These tests guard against the 2026-04-26 fix where ``evaluate_weight_challenger``
and ``_check_single_rollback`` were writing ``source="cs_auto_tune"`` even
though migration ``0028`` had already removed that choice from
``WeightAdjustmentHistory.SOURCE_CHOICES`` on 2026-04-12.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.analytics.models import GSCDailyPerformance
from apps.pipeline.tasks import _check_single_rollback, evaluate_weight_challenger
from apps.suggestions.models import RankingChallenger, WeightAdjustmentHistory


_BASELINE_WEIGHTS = {
    "w_semantic": "0.25",
    "w_keyword": "0.25",
    "w_node": "0.25",
    "w_quality": "0.25",
}
_CANDIDATE_WEIGHTS = {
    "w_semantic": "0.30",
    "w_keyword": "0.20",
    "w_node": "0.25",
    "w_quality": "0.25",
}


class EvaluateWeightChallengerSourceTests(TestCase):
    """Promotion must write source='auto_tune', never the retired 'cs_auto_tune'."""

    def setUp(self) -> None:
        self.run_id = "test-promote-001"
        # predicted > champion * 1.05 → SPRT will decide "promote".
        RankingChallenger.objects.create(
            run_id=self.run_id,
            status="pending",
            candidate_weights=_CANDIDATE_WEIGHTS,
            baseline_weights=_BASELINE_WEIGHTS,
            predicted_quality_score=0.90,
            champion_quality_score=0.70,
        )

    def _force_sprt_promote(self):
        """Patch the SPRT evaluator so it deterministically returns 'promote'."""
        from apps.pipeline.services.sprt_evaluator import ChallengerSPRTEvaluator

        sprt_result = type(
            "SPRTResult",
            (),
            {
                "decision": "promote",
                "log_likelihood_ratio": 5.0,
                "lower_boundary": -2.0,
                "upper_boundary": 2.9,
            },
        )()
        return patch.object(
            ChallengerSPRTEvaluator, "evaluate", return_value=sprt_result
        )

    def test_promotion_writes_auto_tune_source(self) -> None:
        # Mock AppSetting writes so we don't have to seed the full preset.
        with patch("apps.suggestions.weight_preset_service.apply_weights"), patch(
            "apps.suggestions.weight_preset_service.get_current_weights",
            return_value=dict(_BASELINE_WEIGHTS),
        ), self._force_sprt_promote():
            result = evaluate_weight_challenger(run_id=self.run_id)
        self.assertEqual(result["status"], "promoted")
        history_rows = WeightAdjustmentHistory.objects.filter(r_run_id=self.run_id)
        self.assertEqual(history_rows.count(), 1)
        self.assertEqual(history_rows.first().source, "auto_tune")

    def test_no_path_writes_cs_auto_tune(self) -> None:
        with patch("apps.suggestions.weight_preset_service.apply_weights"), patch(
            "apps.suggestions.weight_preset_service.get_current_weights",
            return_value=dict(_BASELINE_WEIGHTS),
        ), self._force_sprt_promote():
            evaluate_weight_challenger(run_id=self.run_id)
        self.assertFalse(
            WeightAdjustmentHistory.objects.filter(source="cs_auto_tune").exists()
        )


class CheckWeightRollbackSourceTests(TestCase):
    """Rollback must write source='auto_tune', never the retired 'cs_auto_tune'."""

    def setUp(self) -> None:
        self.run_id = "test-rollback-001"
        promoted_at = timezone.now() - timedelta(days=14)
        challenger = RankingChallenger.objects.create(
            run_id=self.run_id,
            status="promoted",
            candidate_weights=_CANDIDATE_WEIGHTS,
            baseline_weights=_BASELINE_WEIGHTS,
            predicted_quality_score=0.85,
            champion_quality_score=0.80,
        )
        # Force updated_at into the past — auto_now=True on the field would
        # otherwise reset it to now() on save().
        RankingChallenger.objects.filter(pk=challenger.pk).update(
            updated_at=promoted_at
        )
        self.challenger = RankingChallenger.objects.get(pk=challenger.pk)

        # Healthy 14-day baseline (1000 clicks total) followed by a
        # regression in the post-promotion window (200 clicks total — 20%
        # of baseline, well below the 85% threshold).
        promoted_date = self.challenger.updated_at.date()
        for offset in range(1, 15):
            GSCDailyPerformance.objects.create(
                page_url="https://example.invalid/page",
                date=promoted_date - timedelta(days=offset),
                impressions=10000,
                clicks=72,  # ~ 1000 total
                avg_position=5.0,
                ctr=0.0072,
                property_url="https://example.invalid/",
            )
        for offset in range(0, 14):
            GSCDailyPerformance.objects.create(
                page_url="https://example.invalid/page",
                date=promoted_date + timedelta(days=offset),
                impressions=10000,
                clicks=15,  # ~ 200 total
                avg_position=5.0,
                ctr=0.0015,
                property_url="https://example.invalid/",
            )

    def test_rollback_writes_auto_tune_source(self) -> None:
        with patch("apps.suggestions.weight_preset_service.apply_weights"), patch(
            "apps.suggestions.weight_preset_service.get_current_weights",
            return_value=dict(_CANDIDATE_WEIGHTS),
        ):
            _check_single_rollback(self.challenger)

        self.challenger.refresh_from_db()
        self.assertEqual(self.challenger.status, "rolled_back")
        history_rows = WeightAdjustmentHistory.objects.filter(r_run_id=self.run_id)
        self.assertEqual(history_rows.count(), 1)
        self.assertEqual(history_rows.first().source, "auto_tune")

    def test_rollback_never_writes_cs_auto_tune(self) -> None:
        with patch("apps.suggestions.weight_preset_service.apply_weights"), patch(
            "apps.suggestions.weight_preset_service.get_current_weights",
            return_value=dict(_CANDIDATE_WEIGHTS),
        ):
            _check_single_rollback(self.challenger)
        self.assertFalse(
            WeightAdjustmentHistory.objects.filter(source="cs_auto_tune").exists()
        )
