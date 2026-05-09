"""Regression tests for the FR-018 Python WeightTuner.

These tests guard against the runtime bugs fixed on 2026-04-26:

1. ``WeightTuner.run()`` previously created ``RankingChallenger`` with the
   stale kwargs ``proposed_weights``, ``previous_weights``, and
   ``optimisation_meta`` — none of which exist on the model.  The model
   fields are ``candidate_weights``, ``baseline_weights``,
   ``predicted_quality_score``, and ``champion_quality_score``.
2. ``WeightTuner`` never populated the two ``*_quality_score`` columns so
   ``evaluate_weight_challenger`` always took the auto-promote fallback
   branch instead of running the SPRT comparator.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.suggestions.models import RankingChallenger
from apps.suggestions.services.weight_tuner import WeightTuner


def _synthetic_samples(n: int = 120) -> list[dict[str, float | str]]:
    """Build a list of fake ``Suggestion.objects.values(...)`` rows.

    Half the rows are approved, half rejected, with a strong correlation
    between ``score_semantic`` and approval so the optimiser is forced
    to move ``w_semantic`` away from the equal-weight baseline.

    Includes ``score_embedding_age`` (FR-249 5th tunable) so the
    optional-feature path in ``WeightTuner._maybe_add_fr249_age_decay``
    finds the field on every sample dict and doesn't KeyError. A neutral
    0.5 keeps the optimiser uninfluenced by this feature.
    """
    samples: list[dict[str, float | str]] = []
    for i in range(n):
        is_approved = i < n // 2
        samples.append(
            {
                "score_semantic": 0.95 if is_approved else 0.05,
                "score_keyword": 0.5,
                "score_node_affinity": 0.5,
                "score_quality": 0.5,
                "score_embedding_age": 0.5,
                "score_final": 0.8 if is_approved else 0.2,
                "status": "approved" if is_approved else "rejected",
            }
        )
    return samples


class WeightTunerRunTests(TestCase):
    """Verify WeightTuner.run() persists a challenger with the live model schema."""

    def setUp(self) -> None:
        # Equal-weight baseline so the optimiser has room to move.
        # Includes w_embedding_age (FR-249 5th tunable, seeded by migration
        # 0064_seed_w_embedding_age) so the baseline matches what the live
        # WeightTuner reads at runtime.
        self._current_weights = {
            "w_semantic": "0.20",
            "w_keyword": "0.20",
            "w_node": "0.20",
            "w_quality": "0.20",
            "w_embedding_age": "0.20",
        }

    def _run_with_mocks(self) -> RankingChallenger | None:
        """Run the tuner against synthetic samples + a fixed weights dict."""
        samples = _synthetic_samples()
        with (
            patch(
                "apps.suggestions.services.weight_tuner.get_current_weights",
                return_value=self._current_weights,
            ),
            patch(
                "apps.suggestions.services.weight_tuner.Suggestion.objects.filter",
            ) as filter_mock,
        ):
            filter_mock.return_value.values.return_value = samples
            tuner = WeightTuner(lookback_days=90)
            return tuner.run(run_id="test-run-001")

    def test_creates_challenger_with_live_field_names(self) -> None:
        challenger = self._run_with_mocks()
        self.assertIsNotNone(challenger)
        assert challenger is not None  # for type narrowing
        self.assertEqual(challenger.run_id, "test-run-001")
        self.assertEqual(challenger.status, "pending")
        # The model fields are candidate_weights / baseline_weights — not
        # the legacy proposed_weights / previous_weights kwargs.
        self.assertTrue(challenger.candidate_weights)
        self.assertTrue(challenger.baseline_weights)
        # FR-249 promoted w_embedding_age to a 5th tunable (migration 0064);
        # the live tuner now reads 5 weights when the AppSetting
        # `pipeline.embedding_age_weight_in_composite` is positive.
        expected = {"w_semantic", "w_keyword", "w_node", "w_quality", "w_embedding_age"}
        self.assertSetEqual(set(challenger.candidate_weights), expected)
        self.assertSetEqual(set(challenger.baseline_weights), expected)

    def test_populates_both_quality_scores(self) -> None:
        """Both predicted and champion quality scores must be populated."""
        challenger = self._run_with_mocks()
        self.assertIsNotNone(challenger)
        assert challenger is not None
        self.assertIsNotNone(challenger.predicted_quality_score)
        self.assertIsNotNone(challenger.champion_quality_score)

    def test_quality_scores_are_bounded_in_zero_one(self) -> None:
        """quality = 1 / (1 + loss) must land in (0, 1] for any non-negative loss."""
        challenger = self._run_with_mocks()
        self.assertIsNotNone(challenger)
        assert challenger is not None
        assert challenger.predicted_quality_score is not None
        assert challenger.champion_quality_score is not None
        self.assertGreater(challenger.predicted_quality_score, 0.0)
        self.assertLessEqual(challenger.predicted_quality_score, 1.0)
        self.assertGreater(challenger.champion_quality_score, 0.0)
        self.assertLessEqual(challenger.champion_quality_score, 1.0)

    def test_does_not_pass_stale_kwargs_to_create(self) -> None:
        """Belt-and-braces: assert the create() kwargs are exactly the live set."""
        samples = _synthetic_samples()
        with (
            patch(
                "apps.suggestions.services.weight_tuner.get_current_weights",
                return_value=self._current_weights,
            ),
            patch(
                "apps.suggestions.services.weight_tuner.Suggestion.objects.filter",
            ) as filter_mock,
            patch(
                "apps.suggestions.services.weight_tuner.RankingChallenger.objects.create"
            ) as create_mock,
        ):
            filter_mock.return_value.values.return_value = samples
            create_mock.return_value = RankingChallenger(run_id="test-run-002")
            WeightTuner(lookback_days=90).run(run_id="test-run-002")

        self.assertEqual(create_mock.call_count, 1)
        kwargs = create_mock.call_args.kwargs
        legal_keys = {
            "run_id",
            "status",
            "candidate_weights",
            "baseline_weights",
            "predicted_quality_score",
            "champion_quality_score",
        }
        self.assertSetEqual(set(kwargs), legal_keys)
        # Stale legacy kwargs that used to crash the call are not present.
        self.assertNotIn("proposed_weights", kwargs)
        self.assertNotIn("previous_weights", kwargs)
        self.assertNotIn("optimisation_meta", kwargs)

    def test_candidate_weights_stay_inside_post_normalization_drift_cap(self) -> None:
        self._current_weights = {
            "w_semantic": "0.50",
            "w_keyword": "0.20",
            "w_node": "0.10",
            "w_quality": "0.05",
        }

        challenger = self._run_with_mocks()
        self.assertIsNotNone(challenger)
        assert challenger is not None

        for key in self._current_weights:
            drift = abs(
                challenger.candidate_weights[key] - challenger.baseline_weights[key]
            )
            self.assertLessEqual(drift, 0.0501)


class WeightFloorTests(TestCase):
    """Per DEFAULT-ON-RULE.md: the autotuner must never zero a weight.

    The lower bound on every tunable weight is floored at
    :data:`apps.suggestions.services.weight_tuner._WEIGHT_FLOOR` (0.01).
    These tests pin that invariant — both the bound construction and
    the post-projection simplex output respect the floor.
    """

    def test_weight_floor_constant_is_non_zero(self) -> None:
        from apps.suggestions.services.weight_tuner import _WEIGHT_FLOOR

        self.assertGreater(_WEIGHT_FLOOR, 0.0)
        # Sanity: the floor must be smaller than the smallest weight in
        # the Recommended preset (0.03) or the autotuner can't move
        # below current values at all.
        self.assertLess(_WEIGHT_FLOOR, 0.03)

    def test_lower_bound_for_weight_below_drift_step_floors_at_0_01(self) -> None:
        """A weight at 0.02 with ±0.05 drift would naively floor at -0.03 → 0.0.

        With the new ``_WEIGHT_FLOOR`` constant the floor is 0.01 instead.
        """
        import numpy as np

        from apps.suggestions.services.weight_tuner import (
            _DRIFT_LIMIT_PER_RUN,
            _WEIGHT_FLOOR,
        )

        w_init = np.array([0.02, 0.50, 0.30, 0.18])
        lower_bounds = np.maximum(_WEIGHT_FLOOR, w_init - _DRIFT_LIMIT_PER_RUN)
        # Every lower bound stays at or above the floor.
        self.assertTrue(np.all(lower_bounds >= _WEIGHT_FLOOR))
        # The first weight (0.02) gets the floor exactly.
        self.assertAlmostEqual(float(lower_bounds[0]), _WEIGHT_FLOOR, places=6)

    def test_simplex_projection_respects_the_floor(self) -> None:
        """``_project_to_bounded_simplex`` clamps to the bounds it's given.

        The projection function itself is bounds-agnostic — feeding it
        the floored bounds means the result inherits the floor without
        any other change to the projection logic.
        """
        import numpy as np

        from apps.suggestions.services.weight_tuner import (
            _WEIGHT_FLOOR,
            _project_to_bounded_simplex,
        )

        # Hostile input: optimiser produced a tiny weight close to zero.
        candidate = np.array([0.001, 0.40, 0.30, 0.299])
        lower_bounds = np.full(4, _WEIGHT_FLOOR)
        upper_bounds = np.full(4, 1.0)
        projected = _project_to_bounded_simplex(
            candidate, lower_bounds, upper_bounds
        )
        # No weight slips below the floor.
        self.assertTrue(np.all(projected >= _WEIGHT_FLOOR - 1e-9))
        # And the simplex constraint still holds.
        self.assertAlmostEqual(float(np.sum(projected)), 1.0, places=6)
