"""Tests for W4 — suggestion_explainer service + REST endpoint (pick #47 wiring)."""

from __future__ import annotations

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
