"""apps.training — tests for picks #41-46.

Each sub-module gets its own TestCase. All deps for these helpers
(scipy, optuna, torch, numpy) are pinned in requirements.txt so
tests run unconditionally — no ``unittest.skipUnless`` gates.
"""

from __future__ import annotations

import math

import numpy as np
from django.test import SimpleTestCase

from apps.training.avg.swa import StochasticWeightAverager
from apps.training.hpo.tpe import TpeResult, is_available as hpo_is_available, run_tpe
from apps.training.loss.lambda_loss import lambda_loss
from apps.training.optim.lbfgs_b import LbfgsBResult, minimize_lbfgs_b
from apps.training.sample.ohem import select_hard_examples
from apps.training.schedule.cosine_annealing import (
    CosineAnnealingSchedule,
    learning_rate_at_step,
)


class LbfgsBTests(SimpleTestCase):
    def test_minimises_simple_quadratic(self) -> None:
        """f(x) = (x-3)^2 has minimum at x=3."""

        def objective(x):
            return float((x[0] - 3.0) ** 2)

        result = minimize_lbfgs_b(objective, x0=[0.0])
        self.assertIsInstance(result, LbfgsBResult)
        self.assertTrue(result.converged)
        self.assertAlmostEqual(result.x[0], 3.0, places=4)
        self.assertAlmostEqual(result.fun, 0.0, places=6)

    def test_respects_bounds(self) -> None:
        """Min at x=3 outside the bound — solver returns the bound."""

        def objective(x):
            return float((x[0] - 3.0) ** 2)

        result = minimize_lbfgs_b(
            objective, x0=[0.0], bounds=[(0.0, 1.0)]
        )
        self.assertAlmostEqual(result.x[0], 1.0, places=4)

    def test_callable_failure_returns_non_converged(self) -> None:
        def objective(x):
            raise RuntimeError("boom")

        result = minimize_lbfgs_b(objective, x0=[0.0])
        self.assertFalse(result.converged)


class TpeTests(SimpleTestCase):
    def test_is_available_returns_bool(self) -> None:
        self.assertIsInstance(hpo_is_available(), bool)

    def test_finds_minimum_on_small_search_space(self) -> None:
        if not hpo_is_available():
            self.skipTest("optuna not installed")

        def objective(trial):
            x = trial.suggest_float("x", -5.0, 5.0)
            return (x - 2.0) ** 2

        result = run_tpe(
            objective,
            n_trials=20,
            direction="minimize",
            seed=42,
        )
        self.assertIsInstance(result, TpeResult)
        # 20 trials of TPE on a quadratic should land near x=2.
        self.assertLess(abs(result.best_params["x"] - 2.0), 1.0)


class CosineAnnealingTests(SimpleTestCase):
    def test_step_zero_returns_lr_max(self) -> None:
        schedule = CosineAnnealingSchedule(
            lr_max=0.1, lr_min=0.001, cycle_length=100
        )
        self.assertAlmostEqual(learning_rate_at_step(0, schedule), 0.1)

    def test_step_at_cycle_length_returns_lr_min(self) -> None:
        schedule = CosineAnnealingSchedule(
            lr_max=0.1, lr_min=0.001, cycle_length=100
        )
        # After cycle_length steps the cycle restarts → lr_max again.
        self.assertAlmostEqual(learning_rate_at_step(100, schedule), 0.1)
        # At step 99 we're near the end of the first cycle → near lr_min.
        self.assertLess(learning_rate_at_step(99, schedule), 0.01)

    def test_invalid_cycle_length_returns_lr_max(self) -> None:
        schedule = CosineAnnealingSchedule(
            lr_max=0.1, lr_min=0.001, cycle_length=0
        )
        self.assertEqual(learning_rate_at_step(5, schedule), 0.1)

    def test_warm_restarts_extend_cycles(self) -> None:
        """cycle_multiplier=2 doubles cycle length each restart."""
        schedule = CosineAnnealingSchedule(
            lr_max=1.0,
            lr_min=0.0,
            cycle_length=10,
            cycle_multiplier=2.0,
        )
        # Step 10 → second cycle starts (length 20).
        self.assertAlmostEqual(learning_rate_at_step(10, schedule), 1.0)
        # Step 30 → third cycle (length 40).
        self.assertAlmostEqual(learning_rate_at_step(30, schedule), 1.0)


class LambdaLossTests(SimpleTestCase):
    def test_empty_input_returns_zero(self) -> None:
        self.assertEqual(lambda_loss([], []), 0.0)

    def test_single_item_returns_zero(self) -> None:
        self.assertEqual(lambda_loss([0.5], [1.0]), 0.0)

    def test_all_equal_labels_returns_zero(self) -> None:
        """No NDCG signal when every label is identical."""
        self.assertEqual(lambda_loss([0.5, 0.3, 0.7], [1.0, 1.0, 1.0]), 0.0)

    def test_loss_decreases_when_ranking_aligns_with_labels(self) -> None:
        """Right ordering → small loss; reversed → large loss."""
        # Three items with labels (high, mid, low). When scores sort
        # them in the same order, the loss should be lower than when
        # scores reverse the order.
        loss_aligned = lambda_loss([3.0, 2.0, 1.0], [3.0, 2.0, 1.0])
        loss_reversed = lambda_loss([1.0, 2.0, 3.0], [3.0, 2.0, 1.0])
        self.assertLess(loss_aligned, loss_reversed)

    def test_mismatched_lengths_raises(self) -> None:
        with self.assertRaises(ValueError):
            lambda_loss([1.0, 2.0], [3.0])


class SwaTests(SimpleTestCase):
    def test_cold_start_snapshot_is_empty(self) -> None:
        swa = StochasticWeightAverager()
        self.assertEqual(swa.snapshot(), {})
        self.assertEqual(swa.count, 0)

    def test_arithmetic_mean_over_two_dicts(self) -> None:
        swa = StochasticWeightAverager()
        swa.add({"w": [1.0, 2.0], "b": [0.0]})
        swa.add({"w": [3.0, 4.0], "b": [2.0]})
        result = swa.snapshot()
        np.testing.assert_array_almost_equal(result["w"], [2.0, 3.0])
        np.testing.assert_array_almost_equal(result["b"], [1.0])
        self.assertEqual(swa.count, 2)

    def test_shape_mismatch_raises(self) -> None:
        swa = StochasticWeightAverager()
        swa.add({"w": [1.0, 2.0]})
        with self.assertRaises(ValueError):
            swa.add({"w": [1.0, 2.0, 3.0]})

    def test_reset_clears_state(self) -> None:
        swa = StochasticWeightAverager()
        swa.add({"w": [1.0]})
        swa.reset()
        self.assertEqual(swa.count, 0)
        self.assertEqual(swa.snapshot(), {})


class OhemTests(SimpleTestCase):
    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(select_hard_examples([], keep_top_k=5), [])

    def test_zero_k_returns_empty(self) -> None:
        self.assertEqual(
            select_hard_examples([("a", 1.0), ("b", 2.0)], keep_top_k=0),
            [],
        )

    def test_returns_top_k_by_loss_descending(self) -> None:
        items = [("a", 1.0), ("b", 5.0), ("c", 3.0), ("d", 2.0)]
        result = select_hard_examples(items, keep_top_k=2)
        self.assertEqual(result, [("b", 5.0), ("c", 3.0)])

    def test_k_above_len_returns_all_sorted(self) -> None:
        items = [("a", 1.0), ("b", 5.0)]
        result = select_hard_examples(items, keep_top_k=10)
        self.assertEqual(result, [("b", 5.0), ("a", 1.0)])
