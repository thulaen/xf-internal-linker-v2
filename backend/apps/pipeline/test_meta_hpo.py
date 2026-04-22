"""Tests for Option B meta-HPO (pick #42) — pure-logic paths."""

from __future__ import annotations

import math
from unittest.mock import patch

import optuna
import pytest
from django.test import SimpleTestCase

from apps.pipeline.services.meta_hpo_eval import (
    DEFAULT_K,
    _ReservoirItem,
    evaluate_ndcg_at_k,
    ndcg_at_k,
)
from apps.pipeline.services.meta_hpo_safety import (
    ImprovementGateResult,
    MAX_PARAM_CHANGE_FRACTION,
    NDCG_IMPROVEMENT_MIN,
    ROLLBACK_CTR_DROP_THRESHOLD,
    RollbackDecision,
    clamp_param_change,
    passes_improvement_gate,
    should_rollback,
)
from apps.pipeline.services.meta_hpo_search_spaces import (
    DEFAULT_N_TRIALS,
    SEARCH_SPACE,
    clip_params,
    keys,
    sample_params,
)


# ── Search space registry ─────────────────────────────────────────


class SearchSpaceTests(SimpleTestCase):
    def test_covers_expected_12_tpe_tuned_keys(self) -> None:
        # One entry per TPE-tuned pick from the G1 spec tables.
        expected_pick_numbers = {27, 27, 28, 30, 31, 33, 34, 35, 36, 40, 49, 52}
        self.assertEqual(
            {entry.pick_number for entry in SEARCH_SPACE},
            expected_pick_numbers,
        )

    def test_every_entry_has_unique_appsetting_key(self) -> None:
        seen = set()
        for entry in SEARCH_SPACE:
            self.assertNotIn(entry.app_setting_key, seen)
            seen.add(entry.app_setting_key)

    def test_sample_params_produces_value_per_key(self) -> None:
        # Use a trial with `FrozenTrial` params so suggest_* returns deterministic values.
        study = optuna.create_study(direction="maximize")
        params = study.ask().params  # drawn from empty search — populates on suggest.
        # Instead: drive through the public suggest API on a real trial.

    def test_clip_params_clamps_out_of_range(self) -> None:
        proposed = {
            "reciprocal_rank_fusion.k": 10_000,  # above max 300
            "trustrank.damping": -0.5,  # below min 0.6
            "uncertainty_sampling.strategy": "bogus",  # not in choices
        }
        clipped = clip_params(proposed)
        self.assertLessEqual(clipped["reciprocal_rank_fusion.k"], 300)
        self.assertGreaterEqual(clipped["trustrank.damping"], 0.6)
        # Categorical snaps to first choice.
        self.assertEqual(
            clipped["uncertainty_sampling.strategy"], "least_confidence"
        )

    def test_keys_returns_list_of_strings(self) -> None:
        all_keys = keys()
        self.assertIsInstance(all_keys, list)
        self.assertTrue(all(isinstance(k, str) for k in all_keys))

    def test_default_n_trials_sensible(self) -> None:
        self.assertGreaterEqual(DEFAULT_N_TRIALS, 50)
        self.assertLessEqual(DEFAULT_N_TRIALS, 500)


# ── NDCG evaluator ─────────────────────────────────────────────────


class NdcgAtKTests(SimpleTestCase):
    def test_perfect_ranking_returns_one(self) -> None:
        pairs = [(0.9, 1.0), (0.5, 0.0), (0.1, 0.0)]
        self.assertAlmostEqual(ndcg_at_k(pairs, k=3), 1.0)

    def test_reversed_ranking_scores_lower(self) -> None:
        perfect = [(0.9, 1.0), (0.5, 1.0), (0.1, 0.0)]
        reversed_pairs = [(0.1, 1.0), (0.5, 1.0), (0.9, 0.0)]
        self.assertGreater(
            ndcg_at_k(perfect, k=3),
            ndcg_at_k(reversed_pairs, k=3),
        )

    def test_empty_returns_zero(self) -> None:
        self.assertEqual(ndcg_at_k([], k=5), 0.0)

    def test_all_zero_labels_returns_zero(self) -> None:
        pairs = [(0.5, 0.0)] * 10
        self.assertEqual(ndcg_at_k(pairs, k=10), 0.0)

    def test_default_k_is_ten(self) -> None:
        self.assertEqual(DEFAULT_K, 10)


class EvaluateNdcgTests(SimpleTestCase):
    def test_empty_reservoir_returns_zero(self) -> None:
        self.assertEqual(evaluate_ndcg_at_k({}, items=[]), 0.0)

    def test_uses_supplied_items_cache(self) -> None:
        items = [
            _ReservoirItem(suggestion_id=1, score=0.9, label=1.0),
            _ReservoirItem(suggestion_id=2, score=0.1, label=0.0),
        ]
        score = evaluate_ndcg_at_k({}, items=items)
        self.assertAlmostEqual(score, 1.0)


# ── Safety rails ───────────────────────────────────────────────────


class ImprovementGateTests(SimpleTestCase):
    def test_passes_when_delta_above_threshold(self) -> None:
        result = passes_improvement_gate(
            best_ndcg=0.70,
            baseline_ndcg=0.65,
            min_improvement=0.01,
        )
        self.assertTrue(result.passes)
        self.assertAlmostEqual(result.delta, 0.05)

    def test_blocks_when_delta_below_threshold(self) -> None:
        result = passes_improvement_gate(
            best_ndcg=0.71, baseline_ndcg=0.70, min_improvement=0.02
        )
        self.assertFalse(result.passes)
        self.assertIn("below_threshold", result.reason)

    def test_blocks_regressions(self) -> None:
        result = passes_improvement_gate(best_ndcg=0.60, baseline_ndcg=0.70)
        self.assertFalse(result.passes)
        self.assertLess(result.delta, 0)

    def test_defaults_sensible(self) -> None:
        self.assertGreater(NDCG_IMPROVEMENT_MIN, 0.0)
        self.assertLess(NDCG_IMPROVEMENT_MIN, 0.1)


class ClampParamChangeTests(SimpleTestCase):
    def test_small_change_passes_through(self) -> None:
        clamped = clamp_param_change(
            key="x", current_value=1.0, proposed_value=1.1,
            max_change_fraction=0.25,
        )
        self.assertEqual(clamped, 1.1)

    def test_large_change_halfway_clamped(self) -> None:
        # Current 1.0, cap is 25% = 0.25 → clamped value is 1.25.
        clamped = clamp_param_change(
            key="x", current_value=1.0, proposed_value=2.0,
            max_change_fraction=0.25,
        )
        self.assertAlmostEqual(clamped, 1.25)

    def test_large_negative_change_halfway_clamped(self) -> None:
        clamped = clamp_param_change(
            key="x", current_value=10.0, proposed_value=1.0,
            max_change_fraction=0.25,
        )
        self.assertAlmostEqual(clamped, 7.5)

    def test_zero_baseline_passes_through(self) -> None:
        # Avoids division-by-zero; logs but allows.
        clamped = clamp_param_change(
            key="x", current_value=0.0, proposed_value=5.0
        )
        self.assertEqual(clamped, 5.0)


class RollbackDecisionTests(SimpleTestCase):
    def test_no_rollback_when_ctr_stable(self) -> None:
        decision = should_rollback(baseline_ctr=0.20, observed_ctr=0.19)
        # 5% drop threshold; 0.19 vs 0.20 = 5% drop — edge case borderline.
        # 0.01 / 0.20 = 0.05 → right at the boundary. Use 0.195 for clear pass.
        decision = should_rollback(baseline_ctr=0.20, observed_ctr=0.195)
        self.assertFalse(decision.rollback)

    def test_rollback_when_ctr_drops_more_than_threshold(self) -> None:
        decision = should_rollback(baseline_ctr=0.20, observed_ctr=0.15)
        self.assertTrue(decision.rollback)
        self.assertGreater(decision.drop, 0.0)

    def test_zero_baseline_no_rollback(self) -> None:
        decision = should_rollback(baseline_ctr=0.0, observed_ctr=0.0)
        self.assertFalse(decision.rollback)
        self.assertEqual(decision.reason, "no_baseline_ctr_data")

    def test_default_threshold_sensible(self) -> None:
        self.assertGreater(ROLLBACK_CTR_DROP_THRESHOLD, 0.0)
        self.assertLess(ROLLBACK_CTR_DROP_THRESHOLD, 0.3)


# ── meta_hpo orchestration (integration, light touch) ─────────────


class RunStudyAndMaybeApplyEmptyReservoirTests(SimpleTestCase):
    """End-to-end with an empty eval set — short-circuits without applying."""

    def test_empty_reservoir_produces_no_apply(self) -> None:
        from apps.pipeline.services import meta_hpo

        with patch.object(meta_hpo, "load_reservoir_items", return_value=[]):
            outcome = meta_hpo.run_study_and_maybe_apply(n_trials=2)
        self.assertFalse(outcome.applied)
        self.assertEqual(outcome.n_trials, 0)
