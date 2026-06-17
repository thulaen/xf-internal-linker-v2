"""Tests for ranking metrics emitted to VictoriaMetrics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.observability import metrics_ranking as mr


class RankingMetricsTests(SimpleTestCase):
    def test_latency_timer_records_success_batch(self) -> None:
        with (
            patch.object(mr, "get_metric", side_effect=lambda name: name),
            patch.object(mr, "safe_observe") as observe,
            patch.object(mr, "safe_set") as set_metric,
            patch.object(mr, "safe_inc") as inc,
        ):
            with mr.ranking_latency_timer(candidate_count=3, path="composite_batch"):
                pass

        inc.assert_any_call(
            "xf_ranking_batches_total",
            path="composite_batch",
            status="success",
        )
        observe.assert_any_call("xf_index_candidate_count", 3.0)
        observe.assert_any_call(
            "xf_ranking_batch_size",
            3.0,
            path="composite_batch",
        )
        set_metric.assert_any_call(
            "xf_ranking_decision_last_batch_size",
            3.0,
            path="composite_batch",
        )

    def test_latency_timer_records_timeout_and_reraises(self) -> None:
        with (
            patch.object(mr, "get_metric", side_effect=lambda name: name),
            patch.object(mr, "safe_observe"),
            patch.object(mr, "safe_set"),
            patch.object(mr, "safe_inc") as inc,
        ):
            with self.assertRaises(TimeoutError):
                with mr.ranking_latency_timer(candidate_count=2, path="rank_candidates"):
                    raise TimeoutError("too slow")

        inc.assert_any_call("xf_ranking_batch_timeouts_total", path="rank_candidates")
        inc.assert_any_call(
            "xf_ranking_batch_failures_total",
            path="rank_candidates",
            reason="timeout",
        )
        inc.assert_any_call(
            "xf_ranking_batches_total",
            path="rank_candidates",
            status="timeout",
        )

    def test_component_batch_emits_raw_contribution_and_change_driver(self) -> None:
        with (
            patch.object(mr, "get_metric", side_effect=lambda name: name),
            patch.object(mr, "safe_observe") as observe,
            patch.object(mr, "safe_set") as set_metric,
            patch.object(mr, "safe_inc") as inc,
        ):
            mr.observe_component_batch(
                component_scores=[[0.5, 0.25]],
                weights=[0.2, -0.4],
                silo_scores=[0.05],
                signal_names=("semantic", "keyword"),
            )

        observe.assert_any_call(
            "xf_ranking_signal_raw_score",
            0.5,
            signal="semantic",
        )
        observe.assert_any_call(
            "xf_ranking_signal_contribution",
            0.1,
            signal="semantic",
            direction="positive",
        )
        set_metric.assert_any_call(
            "xf_ranking_signal_last_contribution",
            -0.1,
            signal="keyword",
        )
        inc.assert_any_call(
            "xf_ranking_score_change_total",
            driver="semantic",
            direction="positive",
        )


class RankingAlertRulesTests(SimpleTestCase):
    def test_active_vmalert_rules_include_ranking_decision_alerts(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        rules = (repo_root / "config" / "vmalert" / "rules.yml").read_text(
            encoding="utf-8"
        )
        for text in (
            "xf-ranking-health",
            "RankingValidationFailuresHigh",
            "RankingLatencyP95High",
            "RankingBatchSizeP95High",
            "RankingLastBatchSizeHigh",
            "RankingBatchFailuresHigh",
            "RankingBatchTimeoutsHigh",
            "RankingBatchFailureRatioHigh",
            "RankingRawSignalScoreShift",
            "RankingSignalContributionShift",
            "RankingLastContributionShift",
            "RankingScoreChangeDriverDominant",
            "xf_ranking_decision_latency_seconds_bucket",
            "xf_ranking_batch_size_bucket",
            "xf_ranking_signal_raw_score_bucket",
            "xf_ranking_signal_contribution_bucket",
            "xf_ranking_signal_last_contribution",
            "xf_ranking_score_change_total",
        ):
            with self.subTest(text=text):
                self.assertIn(text, rules)
