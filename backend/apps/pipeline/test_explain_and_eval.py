"""Tests for PR-O — Kernel SHAP explainer + Reservoir Sampling."""

from __future__ import annotations

import random

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.reservoir_sampling import (
    Reservoir,
    deterministic_rng,
    fair_shuffle,
    sample,
)
from apps.pipeline.services.shap_explainer import (
    HAS_SHAP,
    Explanation,
    SHAPUnavailable,
    explain,
    top_contributions,
)


# ── Reservoir Sampling ─────────────────────────────────────────────


class ReservoirDataclassTests(SimpleTestCase):
    def test_k_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            Reservoir(k=0)
        with self.assertRaises(ValueError):
            Reservoir(k=-3)

    def test_first_k_items_kept_verbatim(self) -> None:
        reservoir = Reservoir(k=3, _rng=deterministic_rng(seed=0))
        for item in ["a", "b", "c"]:
            reservoir.add(item)
        self.assertEqual(reservoir.snapshot(), ["a", "b", "c"])

    def test_observation_count_tracks_add_calls(self) -> None:
        reservoir = Reservoir(k=2)
        reservoir.extend(range(10))
        self.assertEqual(reservoir.observation_count, 10)
        self.assertEqual(len(reservoir.snapshot()), 2)


class ReservoirSampleTests(SimpleTestCase):
    def test_stream_shorter_than_k_returns_everything(self) -> None:
        got = sample([1, 2, 3], k=5, rng=deterministic_rng(seed=1))
        self.assertEqual(sorted(got), [1, 2, 3])

    def test_empty_stream_returns_empty(self) -> None:
        self.assertEqual(sample([], k=4), [])

    def test_deterministic_under_seed(self) -> None:
        stream = list(range(1000))
        first = sample(stream, k=10, rng=deterministic_rng(seed=42))
        second = sample(stream, k=10, rng=deterministic_rng(seed=42))
        self.assertEqual(first, second)

    def test_uniform_distribution_over_many_trials(self) -> None:
        # Each item should appear in the sample roughly k/n of the time.
        n_items = 50
        k = 5
        trials = 2000
        counts = {i: 0 for i in range(n_items)}
        for trial in range(trials):
            rng = random.Random(trial)
            drawn = sample(range(n_items), k=k, rng=rng)
            for item in drawn:
                counts[item] += 1
        expected = trials * k / n_items
        # Every bucket should be within ~30 % of the expected value
        # across 2000 trials — loose bound so CI doesn't flake.
        for item, count in counts.items():
            self.assertGreater(count, expected * 0.7)
            self.assertLess(count, expected * 1.3)

    def test_k_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            sample(range(10), k=0)


class FairShuffleTests(SimpleTestCase):
    def test_preserves_all_items(self) -> None:
        items = list(range(20))
        shuffled = list(fair_shuffle(items, rng=deterministic_rng(seed=0)))
        self.assertEqual(sorted(shuffled), items)

    def test_deterministic_under_seed(self) -> None:
        items = list(range(20))
        a = list(fair_shuffle(items, rng=deterministic_rng(seed=9)))
        b = list(fair_shuffle(items, rng=deterministic_rng(seed=9)))
        self.assertEqual(a, b)


# ── Kernel SHAP ────────────────────────────────────────────────────


def _linear_model(x: np.ndarray) -> np.ndarray:
    """Simple linear function: 0.4*x0 + 0.3*x1 + 0.2*x2 + 0.1*x3."""
    weights = np.array([0.4, 0.3, 0.2, 0.1])
    return x @ weights


def _linear_background() -> np.ndarray:
    rng = np.random.default_rng(seed=7)
    return rng.uniform(0.0, 1.0, size=(50, 4))


class SHAPExplainerTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if not HAS_SHAP:
            raise RuntimeError("shap library missing — required for PR-O tests")

    def test_returns_explanation_with_contributions_per_feature(self) -> None:
        background = _linear_background()
        subject = np.array([0.8, 0.2, 0.9, 0.1])
        explanation = explain(
            score_fn=_linear_model,
            subject=subject,
            background=background,
            feature_names=["bm25", "pagerank", "freshness", "diversity"],
        )
        self.assertIsInstance(explanation, Explanation)
        self.assertEqual(len(explanation.contributions), 4)

    def test_baseline_plus_shap_equals_prediction(self) -> None:
        # Kernel SHAP's additive guarantee: baseline + Σφ = f(subject).
        background = _linear_background()
        subject = np.array([0.8, 0.2, 0.9, 0.1])
        explanation = explain(
            score_fn=_linear_model,
            subject=subject,
            background=background,
            feature_names=["f0", "f1", "f2", "f3"],
        )
        predicted_direct = float(_linear_model(subject.reshape(1, -1))[0])
        # Allow a loose tolerance — Kernel SHAP's sampling approximation
        # means the additive property holds in expectation, not exactly.
        self.assertAlmostEqual(
            explanation.predicted_value,
            predicted_direct,
            places=2,
        )

    def test_higher_weight_features_get_larger_shap(self) -> None:
        # Our model has weights [0.4, 0.3, 0.2, 0.1]. Holding the
        # feature values equal-ish, the first feature should have
        # the largest absolute SHAP magnitude.
        background = _linear_background()
        subject = np.array([0.9, 0.9, 0.9, 0.9])
        explanation = explain(
            score_fn=_linear_model,
            subject=subject,
            background=background,
            feature_names=["f0", "f1", "f2", "f3"],
            nsamples=500,  # more samples → more stable ordering
        )
        contributions_by_name = {
            c.feature_name: c.shap_value for c in explanation.contributions
        }
        self.assertGreater(
            abs(contributions_by_name["f0"]),
            abs(contributions_by_name["f3"]),
        )

    def test_contributions_sorted_by_absolute_magnitude(self) -> None:
        background = _linear_background()
        subject = np.array([0.9, 0.9, 0.9, 0.9])
        explanation = explain(
            score_fn=_linear_model,
            subject=subject,
            background=background,
            feature_names=["f0", "f1", "f2", "f3"],
        )
        magnitudes = [abs(c.shap_value) for c in explanation.contributions]
        self.assertEqual(magnitudes, sorted(magnitudes, reverse=True))

    def test_feature_value_is_raw_subject_value(self) -> None:
        background = _linear_background()
        subject = np.array([0.11, 0.22, 0.33, 0.44])
        explanation = explain(
            score_fn=_linear_model,
            subject=subject,
            background=background,
            feature_names=["f0", "f1", "f2", "f3"],
        )
        name_to_value = {c.feature_name: c.value for c in explanation.contributions}
        self.assertAlmostEqual(name_to_value["f0"], 0.11)
        self.assertAlmostEqual(name_to_value["f3"], 0.44)

    def test_mismatched_feature_count_rejected(self) -> None:
        background = _linear_background()
        subject = np.array([0.5, 0.5, 0.5, 0.5])
        with self.assertRaises(ValueError):
            explain(
                score_fn=_linear_model,
                subject=subject,
                background=background,
                feature_names=["only", "three", "names"],
            )

    def test_empty_background_rejected(self) -> None:
        with self.assertRaises(ValueError):
            explain(
                score_fn=_linear_model,
                subject=np.array([0.5, 0.5, 0.5, 0.5]),
                background=np.zeros((0, 4)),
                feature_names=["f0", "f1", "f2", "f3"],
            )

    def test_top_contributions_caps_at_n(self) -> None:
        background = _linear_background()
        subject = np.array([0.9, 0.9, 0.9, 0.9])
        explanation = explain(
            score_fn=_linear_model,
            subject=subject,
            background=background,
            feature_names=["f0", "f1", "f2", "f3"],
        )
        self.assertEqual(len(top_contributions(explanation, n=2)), 2)


class SHAPUnavailableTests(SimpleTestCase):
    def test_shap_unavailable_exception_is_distinct(self) -> None:
        # SHAPUnavailable must not collide with the stdlib's ImportError
        # so callers can branch on it without catching every missing
        # import.
        self.assertTrue(issubclass(SHAPUnavailable, RuntimeError))
        self.assertFalse(issubclass(SHAPUnavailable, ImportError))
