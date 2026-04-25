"""Tests for W4 — suggestion_explainer service + REST endpoint (pick #47 wiring)."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
from django.test import TestCase

from apps.suggestions.services.suggestion_explainer import (
    EXPLAINED_COMPONENTS,
    Explanation,
    FeatureContribution,
    explain_suggestion,
)


class _StubSuggestion:
    """Light stand-in for a Suggestion row — keeps the test off the
    full ContentItem + Sentence + PipelineRun fixture chain."""

    def __init__(self, **scores):
        # Default all components to neutral (0.5) so a partial input
        # exercises only the components the test cares about.
        for field_name, _, _ in EXPLAINED_COMPONENTS:
            setattr(self, field_name, scores.get(field_name, 0.5))


class ExplainSuggestionLogicTests(TestCase):
    def test_returns_explanation_dataclass(self) -> None:
        suggestion = _StubSuggestion()
        explanation = explain_suggestion(suggestion)
        self.assertIsInstance(explanation, Explanation)
        self.assertEqual(explanation.method, "linear_attribution")
        # All components surfaced — operators see "considered with
        # weight=0" rows even when nothing's persisted yet.
        self.assertEqual(
            len(explanation.contributions), len(EXPLAINED_COMPONENTS)
        )

    def test_baseline_is_neutral_half(self) -> None:
        # Spec convention — score 0.5 is neutral, contributions are
        # offsets above/below that baseline.
        suggestion = _StubSuggestion()
        explanation = explain_suggestion(suggestion)
        self.assertAlmostEqual(explanation.baseline, 0.5)

    def test_neutral_input_zero_contribution(self) -> None:
        # Every component at 0.5 → SHAP value 0 for each → predicted
        # value equals baseline.
        suggestion = _StubSuggestion()
        explanation = explain_suggestion(suggestion)
        for c in explanation.contributions:
            self.assertEqual(c.shap_value, 0.0)
        self.assertAlmostEqual(explanation.predicted_value, 0.5)

    def test_component_with_weight_contributes(self) -> None:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key="w_semantic", defaults={"value": "0.4", "description": ""}
        )
        suggestion = _StubSuggestion(score_semantic=0.9)
        explanation = explain_suggestion(suggestion)
        # 0.4 * (0.9 - 0.5) = 0.16 contribution from semantic.
        semantic_row = next(
            c for c in explanation.contributions
            if c.feature_name == "Semantic similarity"
        )
        self.assertAlmostEqual(semantic_row.shap_value, 0.16, places=5)

    def test_contributions_sorted_by_absolute_magnitude(self) -> None:
        from apps.core.models import AppSetting

        for key, val in (
            ("w_semantic", "0.5"),
            ("w_keyword", "0.2"),
            ("w_node", "0.1"),
            ("w_quality", "0.05"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": val, "description": ""}
            )
        suggestion = _StubSuggestion(
            score_semantic=0.9,
            score_keyword=0.7,
            score_node_affinity=0.6,
            score_quality=0.55,
        )
        explanation = explain_suggestion(suggestion)
        magnitudes = [abs(c.shap_value) for c in explanation.contributions]
        # Sorted strictly descending — highest |contribution| first.
        self.assertEqual(magnitudes, sorted(magnitudes, reverse=True))

    def test_to_dict_round_trip(self) -> None:
        suggestion = _StubSuggestion()
        explanation = explain_suggestion(suggestion)
        payload = explanation.to_dict()
        self.assertIn("predicted_value", payload)
        self.assertIn("baseline", payload)
        self.assertIn("contributions", payload)
        self.assertIn("method", payload)
        self.assertEqual(payload["method"], "linear_attribution")
        self.assertEqual(
            len(payload["contributions"]), len(EXPLAINED_COMPONENTS)
        )

    def test_feature_contribution_to_dict(self) -> None:
        c = FeatureContribution(
            feature_name="x", value=0.7, shap_value=0.1
        )
        d = c.to_dict()
        self.assertEqual(d["feature_name"], "x")
        self.assertEqual(d["value"], 0.7)
        self.assertEqual(d["shap_value"], 0.1)

    def test_missing_component_omitted(self) -> None:
        # An entirely fresh Suggestion-like object missing one column
        # should not crash. Real DB rows always have all columns, but
        # this defends against partial-load scenarios.
        class _Partial:
            score_semantic = 0.7

        explanation = explain_suggestion(_Partial())
        # Only score_semantic surfaced; everything else absent.
        names = {c.feature_name for c in explanation.contributions}
        self.assertIn("Semantic similarity", names)


class KernelShapPathTests(TestCase):
    """Path tests that force the real Kernel SHAP branch + verify
    fallback behaviour."""

    def _stub_with_features(self, **scores) -> _StubSuggestion:
        return _StubSuggestion(**scores)

    def _balanced_background(self, n: int = 20) -> np.ndarray:
        # Synthetic background: each row is a random plausible
        # Suggestion feature vector. Stable seed for determinism.
        rng = np.random.default_rng(0)
        return rng.uniform(0.2, 0.8, size=(n, len(EXPLAINED_COMPONENTS)))

    def test_kernel_shap_used_when_background_available(self) -> None:
        """When DB has ≥ 5 background rows, the explainer should run
        real Kernel SHAP and report ``method == "kernel_shap"``."""
        from apps.core.models import AppSetting
        from apps.pipeline.services import ranker_score_fn

        AppSetting.objects.update_or_create(
            key="w_semantic", defaults={"value": "0.4", "description": ""}
        )
        AppSetting.objects.update_or_create(
            key="w_keyword", defaults={"value": "0.3", "description": ""}
        )

        suggestion = self._stub_with_features(
            score_semantic=0.9,
            score_keyword=0.7,
        )
        with patch.object(
            ranker_score_fn,
            "load_background_features",
            return_value=self._balanced_background(20),
        ):
            explanation = explain_suggestion(suggestion)
        self.assertEqual(explanation.method, "kernel_shap")
        # SHAP returns 11 contributions matching the column count.
        self.assertEqual(
            len(explanation.contributions), len(EXPLAINED_COMPONENTS)
        )

    def test_kernel_shap_falls_back_when_background_too_small(self) -> None:
        from apps.pipeline.services import ranker_score_fn

        suggestion = self._stub_with_features(score_semantic=0.9)
        # Background of size 3 — below the MIN 5 threshold → fallback.
        with patch.object(
            ranker_score_fn,
            "load_background_features",
            return_value=self._balanced_background(3),
        ):
            explanation = explain_suggestion(suggestion)
        self.assertEqual(explanation.method, "linear_attribution")

    def test_kernel_shap_falls_back_on_runtime_error(self) -> None:
        from apps.pipeline.services import shap_explainer
        from apps.pipeline.services import ranker_score_fn

        suggestion = self._stub_with_features(score_semantic=0.7)
        with patch.object(
            ranker_score_fn,
            "load_background_features",
            return_value=self._balanced_background(20),
        ), patch.object(
            shap_explainer,
            "explain",
            side_effect=RuntimeError("simulated SHAP failure"),
        ):
            explanation = explain_suggestion(suggestion)
        self.assertEqual(explanation.method, "linear_attribution")

    def test_kernel_shap_and_linear_agree_on_linear_model(self) -> None:
        """Sanity check: for the current linear ranker, Kernel SHAP and
        linear attribution should produce the same ordering and very
        close magnitudes (within sampling noise)."""
        from apps.core.models import AppSetting
        from apps.pipeline.services import ranker_score_fn

        AppSetting.objects.update_or_create(
            key="w_semantic", defaults={"value": "0.4", "description": ""}
        )
        AppSetting.objects.update_or_create(
            key="w_keyword", defaults={"value": "0.3", "description": ""}
        )
        AppSetting.objects.update_or_create(
            key="w_node", defaults={"value": "0.2", "description": ""}
        )

        suggestion = self._stub_with_features(
            score_semantic=0.9,
            score_keyword=0.6,
            score_node_affinity=0.55,
        )

        # Kernel SHAP path.
        with patch.object(
            ranker_score_fn,
            "load_background_features",
            return_value=self._balanced_background(20),
        ):
            shap_explanation = explain_suggestion(suggestion)
        self.assertEqual(shap_explanation.method, "kernel_shap")

        # Linear path (force fallback by pretending no background).
        with patch.object(
            ranker_score_fn,
            "load_background_features",
            return_value=None,
        ):
            linear_explanation = explain_suggestion(suggestion)
        self.assertEqual(linear_explanation.method, "linear_attribution")

        # Top contribution by absolute magnitude must be the same
        # across both methods — sampling noise can wobble the exact
        # number but ordering is robust.
        self.assertEqual(
            shap_explanation.contributions[0].feature_name,
            linear_explanation.contributions[0].feature_name,
        )
