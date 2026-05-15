"""Regression tests for tuning Celery tasks."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.pipeline.tasks_tuning import (
    evaluate_meta_challenger,
    evaluate_weight_challenger,
    monthly_meta_tune,
)
from apps.suggestions.models import RankingChallenger


class TuningTaskTests(TestCase):
    def test_monthly_meta_tune_creates_meta_algorithm_challenger(self) -> None:
        with (
            patch(
                "apps.suggestions.services.meta_tuner.MetaAlgorithmTuner.propose",
                return_value={"rrf.k": 60.0},
            ),
            patch(
                "apps.suggestions.weight_preset_service.get_current_weights",
                return_value={"rrf.k": "60"},
            ),
        ):
            result = monthly_meta_tune.run()

        self.assertEqual(result["status"], "created")
        challenger = RankingChallenger.objects.get(run_id=result["run_id"])
        self.assertEqual(challenger.kind, "meta_algorithm")
        self.assertEqual(challenger.candidate_weights, {"rrf.k": "60.0"})

    def test_evaluate_meta_challenger_uses_kind_field(self) -> None:
        challenger = RankingChallenger.objects.create(
            run_id="meta-run",
            kind="meta_algorithm",
            candidate_weights={"rrf.k": "60"},
            baseline_weights={"rrf.k": "55"},
        )

        result = evaluate_meta_challenger.run(run_id=challenger.run_id)

        self.assertEqual(result, {"status": "deferred", "run_id": "meta-run"})

    def test_evaluate_weight_challenger_uses_kind_field(self) -> None:
        challenger = RankingChallenger.objects.create(
            run_id="weight-run",
            kind="weights",
            candidate_weights={"w_semantic": "0.3"},
            baseline_weights={"w_semantic": "0.25"},
        )

        result = evaluate_weight_challenger.run(run_id=challenger.run_id)

        self.assertEqual(result, {"status": "deferred", "run_id": "weight-run"})
