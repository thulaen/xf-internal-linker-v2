"""Tests for Platt sigmoid calibration (PR-L #32)."""

from __future__ import annotations

import math
import random

from django.test import SimpleTestCase

from apps.pipeline.services.platt_calibration import (
    PlattCalibration,
    fit,
)


def _synthetic_dataset(n: int = 200, seed: int = 0) -> tuple[list[float], list[int]]:
    """Return a monotone classification problem where higher score → higher P(y=1)."""
    rng = random.Random(seed)
    scores: list[float] = []
    labels: list[int] = []
    for _ in range(n):
        score = rng.gauss(0.0, 1.0)
        # Logistic generating process with known slope = -2, bias = 0.
        true_p = 1.0 / (1.0 + math.exp(-2.0 * score))
        label = 1 if rng.random() < true_p else 0
        scores.append(score)
        labels.append(label)
    return scores, labels


class FitBasicsTests(SimpleTestCase):
    def test_returns_platt_calibration_with_class_counts(self) -> None:
        scores, labels = _synthetic_dataset()
        cal = fit(scores=scores, labels=labels)
        self.assertIsInstance(cal, PlattCalibration)
        self.assertEqual(cal.n_positives + cal.n_negatives, len(labels))

    def test_recovers_monotone_relationship(self) -> None:
        scores, labels = _synthetic_dataset()
        cal = fit(scores=scores, labels=labels)
        p_low = cal.predict(-3.0)
        p_high = cal.predict(3.0)
        # True relationship has slope -2 ⇒ higher score maps to higher P.
        self.assertGreater(p_high, p_low)
        self.assertGreater(p_high, 0.5)
        self.assertLess(p_low, 0.5)

    def test_slope_is_negative_for_increasing_relationship(self) -> None:
        # When higher raw scores mean higher P(y=1), the logistic formula
        # P = 1 / (1 + exp(A*f + B)) requires A < 0.
        scores, labels = _synthetic_dataset()
        cal = fit(scores=scores, labels=labels)
        self.assertLess(cal.slope, 0.0)


class FitValidationTests(SimpleTestCase):
    def test_mismatched_lengths_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fit(scores=[1.0, 2.0], labels=[1])

    def test_empty_inputs_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fit(scores=[], labels=[])

    def test_non_binary_labels_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fit(scores=[0.0, 1.0], labels=[0, 2])

    def test_single_class_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fit(scores=[0.0, 1.0, 2.0], labels=[1, 1, 1])


class PredictTests(SimpleTestCase):
    def test_predict_clamped_in_zero_one(self) -> None:
        cal = PlattCalibration(slope=-2.0, bias=0.0, n_positives=10, n_negatives=10)
        for score in (-1e6, -100, -1, 0, 1, 100, 1e6):
            p = cal.predict(score)
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_predict_many_matches_predict_pointwise(self) -> None:
        cal = PlattCalibration(slope=-1.5, bias=0.3, n_positives=5, n_negatives=5)
        scores = [-2.0, -0.5, 0.0, 0.5, 2.0]
        expected = [cal.predict(s) for s in scores]
        got = cal.predict_many(scores)
        for e, g in zip(expected, got):
            self.assertAlmostEqual(e, g, places=10)

    def test_symmetric_around_zero_logit_is_point_five(self) -> None:
        # logit = A*f + B = 0 ⇒ P = 0.5
        cal = PlattCalibration(slope=-1.0, bias=0.0, n_positives=1, n_negatives=1)
        self.assertAlmostEqual(cal.predict(0.0), 0.5)


class DatasetEdgeCasesTests(SimpleTestCase):
    def test_small_balanced_set_fits(self) -> None:
        scores = [-1.0, -0.5, 0.5, 1.0]
        labels = [0, 0, 1, 1]
        cal = fit(scores=scores, labels=labels)
        # The soft-target smoothing means predictions never saturate at 0 / 1.
        self.assertLess(cal.predict(-10.0), 0.05)
        self.assertGreater(cal.predict(10.0), 0.95)
