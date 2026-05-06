"""Tests for impact_engine.py pure-function helpers.

All tests use SimpleTestCase — no database or Docker required.
Covers: BayesianTrendAttributor._compute_control_trend, ._run_monte_carlo,
.compute_uplift (public API), _score_candidate_distance, _compute_query_lift.
"""

from __future__ import annotations

import numpy as np
from django.test import SimpleTestCase

from apps.analytics.impact_engine import (
    BayesianTrendAttributor,
    _compute_query_lift,
    _score_candidate_distance,
)

_SEED = 42


class TestComputeControlTrend(SimpleTestCase):
    """_compute_control_trend returns a Laplace-smoothed CTR trend factor."""

    def setUp(self):
        self.attr = BayesianTrendAttributor()

    def test_stable_control_returns_one(self):
        t = self.attr._compute_control_trend(100, 1000, 100, 1000)
        self.assertAlmostEqual(t, 1.0, places=3)

    def test_doubling_clicks_yields_gt_one(self):
        t = self.attr._compute_control_trend(100, 1000, 200, 1000)
        self.assertGreater(t, 1.0)

    def test_zero_impressions_safe(self):
        # Laplace smoothing prevents ZeroDivisionError: base=1/1, post=51/101
        t = self.attr._compute_control_trend(0, 0, 50, 100)
        self.assertAlmostEqual(t, 51 / 101, places=4)


class TestRunMonteCarlo(SimpleTestCase):
    """_run_monte_carlo returns a probability in [0, 1]."""

    def setUp(self):
        self.attr = BayesianTrendAttributor()

    def test_high_prob_when_clicks_jump(self):
        np.random.seed(_SEED)
        p = self.attr._run_monte_carlo(10, 1000, 100, 1000, trend=1.0)
        self.assertGreater(p, 0.90)

    def test_low_prob_when_clicks_drop(self):
        np.random.seed(_SEED)
        p = self.attr._run_monte_carlo(100, 1000, 10, 1000, trend=1.0)
        self.assertLess(p, 0.10)

    def test_near_half_when_clicks_equal(self):
        np.random.seed(_SEED)
        p = self.attr._run_monte_carlo(50, 1000, 50, 1000, trend=1.0)
        self.assertAlmostEqual(p, 0.5, delta=0.12)


class TestScoreCandidateDistance(SimpleTestCase):
    """_score_candidate_distance computes normalized Euclidean distance."""

    def test_identical_candidate_zero_distance(self):
        cand = {"clicks": 100.0, "impressions": 1000.0, "ctr": 0.1, "average_position": 5.0}
        d = _score_candidate_distance(cand, 100.0, 1000.0, 0.1, 5.0)
        self.assertAlmostEqual(d, 0.0, places=6)

    def test_different_candidate_positive_distance(self):
        cand = {"clicks": 10.0, "impressions": 100.0, "ctr": 0.05, "average_position": 10.0}
        d = _score_candidate_distance(cand, 100.0, 1000.0, 0.1, 5.0)
        self.assertGreater(d, 0.0)

    def test_none_values_handled(self):
        cand = {"clicks": None, "impressions": None, "ctr": None, "average_position": None}
        d = _score_candidate_distance(cand, 0.0, 0.0, 0.0, 0.0)
        self.assertGreaterEqual(d, 0.0)


class TestComputeQueryLift(SimpleTestCase):
    """_compute_query_lift returns normalized click lift as a percentage."""

    def test_doubling_clicks_is_100_pct(self):
        self.assertAlmostEqual(_compute_query_lift(10, 20, 1.0), 100.0, places=2)

    def test_zero_baseline_nonzero_post_is_100(self):
        self.assertEqual(_compute_query_lift(0, 10, 1.0), 100.0)

    def test_zero_both_is_zero(self):
        self.assertEqual(_compute_query_lift(0, 0, 1.0), 0.0)

    def test_control_multiplier_applied(self):
        # c_base=10, multiplier=1.5 → normalized=15; c_post=15 → lift=0 %
        self.assertAlmostEqual(_compute_query_lift(10, 15, 1.5), 0.0, places=2)


class TestBayesianTrendAttributorComputeUplift(SimpleTestCase):
    """compute_uplift public API — full integration of the Bayesian model."""

    def setUp(self):
        self.attr = BayesianTrendAttributor()

    def test_positive_reward_when_clicks_jump(self):
        np.random.seed(_SEED)
        result = self.attr.compute_uplift(
            target_clicks_base=10, target_imps_base=1000,
            target_clicks_post=100, target_imps_post=1000,
            control_clicks_base=10, control_imps_base=1000,
            control_clicks_post=10, control_imps_post=1000,
        )
        self.assertEqual(result["reward_label"], "positive")
        self.assertGreater(result["probability_of_uplift"], 0.90)

    def test_negative_reward_when_clicks_drop(self):
        np.random.seed(_SEED)
        result = self.attr.compute_uplift(
            target_clicks_base=100, target_imps_base=1000,
            target_clicks_post=10, target_imps_post=1000,
            control_clicks_base=100, control_imps_base=1000,
            control_clicks_post=100, control_imps_post=1000,
        )
        self.assertEqual(result["reward_label"], "negative")

    def test_inconclusive_with_few_clicks(self):
        np.random.seed(_SEED)
        result = self.attr.compute_uplift(
            target_clicks_base=1, target_imps_base=10,
            target_clicks_post=1, target_imps_post=10,
            control_clicks_base=1, control_imps_base=10,
            control_clicks_post=1, control_imps_post=10,
        )
        self.assertIn(result["reward_label"], ["inconclusive", "neutral"])

    def test_result_keys_present(self):
        np.random.seed(_SEED)
        result = self.attr.compute_uplift(
            target_clicks_base=10, target_imps_base=100,
            target_clicks_post=15, target_imps_post=100,
            control_clicks_base=10, control_imps_base=100,
            control_clicks_post=10, control_imps_post=100,
        )
        for key in ("probability_of_uplift", "lift_clicks_pct", "reward_label", "site_trend"):
            self.assertIn(key, result)
