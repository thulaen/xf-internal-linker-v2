"""Tests for PR-P review-layer helpers — picks #49, #50, #52."""

from __future__ import annotations

import random

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.adaptive_conformal_inference import (
    DEFAULT_CLIP_MAX,
    DEFAULT_CLIP_MIN,
    DEFAULT_LEARNING_RATE_GAMMA,
    DEFAULT_TARGET_ALPHA,
    DEFAULT_WINDOW_SIZE,
    AdaptiveConformalInference,
)
from apps.pipeline.services.conformal_prediction import (
    ConformalCalibration,
    ConformalInterval,
    coverage_indicator,
    fit as conformal_fit,
    observed_coverage,
)
from apps.pipeline.services.uncertainty_sampling import (
    DEFAULT_STRATEGY,
    Strategy,
    UncertaintyScore,
    rank_by_uncertainty,
    score as uncertainty_score,
)


# ── Uncertainty Sampling (#49) ─────────────────────────────────────


class UncertaintySamplingTests(SimpleTestCase):
    def test_least_confidence_orders_low_max_probability_first(self) -> None:
        probs = [
            [0.9, 0.05, 0.05],  # confident — uncertainty 0.1
            [0.5, 0.3, 0.2],  # uncertain — uncertainty 0.5
            [0.7, 0.15, 0.15],  # middle — uncertainty 0.3
        ]
        order = rank_by_uncertainty(probs, strategy="least_confidence")
        self.assertEqual(order, [1, 2, 0])

    def test_margin_orders_smallest_gap_first(self) -> None:
        probs = [
            [0.9, 0.05, 0.05],  # margin 0.85
            [0.45, 0.44, 0.11],  # margin 0.01 — most uncertain
            [0.7, 0.2, 0.1],  # margin 0.5
        ]
        order = rank_by_uncertainty(probs, strategy="margin")
        self.assertEqual(order[0], 1)

    def test_entropy_orders_most_symmetric_first(self) -> None:
        probs = [
            [0.9, 0.05, 0.05],
            [1 / 3, 1 / 3, 1 / 3],  # maximum entropy
            [0.7, 0.2, 0.1],
        ]
        order = rank_by_uncertainty(probs, strategy="entropy")
        self.assertEqual(order[0], 1)

    def test_accepts_binary_scalar_probabilities(self) -> None:
        # Scalar-prob input (binary positive-class probability) expands
        # to (P, 1-P) pairs internally.
        scalars = [0.5, 0.9, 0.1]
        order = rank_by_uncertainty(scalars, strategy="least_confidence")
        self.assertEqual(order[0], 0)  # 0.5 is the most uncertain

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(rank_by_uncertainty([]), [])
        self.assertEqual(uncertainty_score([]), [])

    def test_unknown_strategy_raises(self) -> None:
        with self.assertRaises(ValueError):
            rank_by_uncertainty([[0.5, 0.5]], strategy="bogus")

    def test_margin_requires_two_classes(self) -> None:
        with self.assertRaises(ValueError):
            rank_by_uncertainty(np.array([[1.0]]), strategy="margin")

    def test_score_returns_per_row_dataclass(self) -> None:
        probs = [[0.5, 0.5], [0.9, 0.1]]
        scores = uncertainty_score(probs, strategy="least_confidence")
        self.assertEqual(len(scores), 2)
        self.assertIsInstance(scores[0], UncertaintyScore)
        self.assertGreater(scores[0].uncertainty, scores[1].uncertainty)

    def test_default_strategy_matches_enum(self) -> None:
        self.assertEqual(DEFAULT_STRATEGY, Strategy.LEAST_CONFIDENCE.value)

    def test_stable_tie_break(self) -> None:
        # Two rows have identical probabilities; argsort must preserve
        # input order so the review queue is deterministic.
        probs = [[0.5, 0.5], [0.5, 0.5], [0.9, 0.1]]
        order = rank_by_uncertainty(probs, strategy="least_confidence")
        self.assertEqual(order, [0, 1, 2])


# ── Conformal Prediction (#50) ─────────────────────────────────────


class ConformalPredictionTests(SimpleTestCase):
    def test_fit_returns_calibration_dataclass(self) -> None:
        rng = random.Random(0)
        scores = [rng.gauss(0.0, 1.0) for _ in range(200)]
        labels = [s + rng.gauss(0.0, 0.1) for s in scores]
        cal = conformal_fit(
            calibration_scores=scores, calibration_labels=labels, alpha=0.1
        )
        self.assertIsInstance(cal, ConformalCalibration)
        self.assertEqual(cal.calibration_set_size, 200)
        self.assertAlmostEqual(cal.alpha, 0.1)
        self.assertGreater(cal.half_width, 0.0)

    def test_predict_interval_bounds_predicted(self) -> None:
        rng = random.Random(1)
        scores = [rng.gauss(0.0, 1.0) for _ in range(200)]
        labels = [s + rng.gauss(0.0, 0.1) for s in scores]
        cal = conformal_fit(
            calibration_scores=scores, calibration_labels=labels, alpha=0.1
        )
        interval = cal.predict_interval(0.5)
        self.assertIsInstance(interval, ConformalInterval)
        self.assertAlmostEqual(interval.predicted, 0.5)
        self.assertAlmostEqual(interval.lower, 0.5 - cal.half_width)
        self.assertAlmostEqual(interval.upper, 0.5 + cal.half_width)

    def test_observed_coverage_close_to_target(self) -> None:
        # Monte Carlo: on synthetic exchangeable data, observed coverage
        # should be within a few % of the target (1 − α) = 0.9.
        rng = random.Random(42)
        n_calib = 500
        calib_scores = [rng.gauss(0.0, 1.0) for _ in range(n_calib)]
        calib_labels = [s + rng.gauss(0.0, 0.1) for s in calib_scores]
        cal = conformal_fit(
            calibration_scores=calib_scores,
            calibration_labels=calib_labels,
            alpha=0.1,
        )
        test_scores = [rng.gauss(0.0, 1.0) for _ in range(1000)]
        test_labels = [s + rng.gauss(0.0, 0.1) for s in test_scores]
        intervals = [cal.predict_interval(s) for s in test_scores]
        cov = observed_coverage(intervals=intervals, true_labels=test_labels)
        self.assertGreater(cov, 0.85)
        self.assertLess(cov, 0.95)

    def test_alpha_outside_range_rejected(self) -> None:
        with self.assertRaises(ValueError):
            conformal_fit(calibration_scores=[1.0], calibration_labels=[1.0], alpha=0.0)
        with self.assertRaises(ValueError):
            conformal_fit(calibration_scores=[1.0], calibration_labels=[1.0], alpha=1.0)

    def test_empty_calibration_rejected(self) -> None:
        with self.assertRaises(ValueError):
            conformal_fit(calibration_scores=[], calibration_labels=[])

    def test_mismatched_shape_rejected(self) -> None:
        with self.assertRaises(ValueError):
            conformal_fit(calibration_scores=[1.0, 2.0], calibration_labels=[1.0])

    def test_coverage_indicator_boundary_inclusive(self) -> None:
        interval = ConformalInterval(
            predicted=0.5, lower=0.4, upper=0.6, half_width=0.1, alpha=0.1
        )
        self.assertTrue(
            coverage_indicator(predicted=0.5, true_label=0.4, interval=interval)
        )
        self.assertTrue(
            coverage_indicator(predicted=0.5, true_label=0.6, interval=interval)
        )
        self.assertFalse(
            coverage_indicator(predicted=0.5, true_label=0.65, interval=interval)
        )


# ── Adaptive Conformal Inference (#52) ─────────────────────────────


class AdaptiveConformalInferenceTests(SimpleTestCase):
    def test_defaults_sensible(self) -> None:
        self.assertEqual(DEFAULT_TARGET_ALPHA, 0.10)
        self.assertGreater(DEFAULT_LEARNING_RATE_GAMMA, 0.0)
        self.assertGreater(DEFAULT_WINDOW_SIZE, 0)
        self.assertLess(DEFAULT_CLIP_MIN, DEFAULT_CLIP_MAX)

    def test_warmup_keeps_initial_alpha(self) -> None:
        aci = AdaptiveConformalInference(window_size=10)
        # Feed 4 observations — below half-window threshold. α shouldn't move.
        for _ in range(4):
            aci.update(True)
        self.assertAlmostEqual(aci.current_alpha, aci.target_alpha)

    def test_under_coverage_pushes_alpha_up(self) -> None:
        aci = AdaptiveConformalInference(
            window_size=20,
            learning_rate_gamma=0.5,  # bigger gamma for visible movement
        )
        # Feed 20 miss-everything outcomes — miscoverage 100 %, target 10 %.
        # α should climb toward clip_max.
        for _ in range(20):
            aci.update(False)
        self.assertGreater(aci.current_alpha, aci.target_alpha)

    def test_over_coverage_pushes_alpha_down(self) -> None:
        aci = AdaptiveConformalInference(
            window_size=20,
            learning_rate_gamma=0.5,
            target_alpha=0.20,  # start above clip_min so α has room to descend
        )
        for _ in range(20):
            aci.update(True)  # 100 % coverage → miscoverage 0 < target
        self.assertLess(aci.current_alpha, aci.target_alpha)

    def test_clip_prevents_runaway(self) -> None:
        aci = AdaptiveConformalInference(
            window_size=10,
            learning_rate_gamma=10.0,  # pathological γ
        )
        for _ in range(100):
            aci.update(False)
        self.assertLessEqual(aci.current_alpha, DEFAULT_CLIP_MAX)

    def test_observations_and_observed_coverage(self) -> None:
        aci = AdaptiveConformalInference(window_size=10)
        self.assertEqual(aci.observations, 0)
        for was_covered in [True, True, False, True, False]:
            aci.update(was_covered)
        self.assertEqual(aci.observations, 5)
        self.assertAlmostEqual(aci.observed_coverage, 3 / 5)

    def test_snapshot_round_trip(self) -> None:
        aci = AdaptiveConformalInference(window_size=10)
        for _ in range(5):
            aci.update(True)
        snapshot = aci.snapshot()
        self.assertIn("current_alpha", snapshot)
        self.assertIn("observed_coverage", snapshot)
        self.assertEqual(snapshot["observations"], 5.0)

    def test_invalid_inputs_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdaptiveConformalInference(target_alpha=0.0)
        with self.assertRaises(ValueError):
            AdaptiveConformalInference(learning_rate_gamma=0.0)
        with self.assertRaises(ValueError):
            AdaptiveConformalInference(window_size=0)
        with self.assertRaises(ValueError):
            AdaptiveConformalInference(clip_min=0.5, clip_max=0.2)
        with self.assertRaises(ValueError):
            AdaptiveConformalInference(target_alpha=0.05, clip_min=0.1, clip_max=0.5)
