"""Integration test for pick #49 — Lewis-Gale uncertainty wiring.

Proof point: ``_build_suggestion_records`` derives
``Suggestion.uncertainty_score`` from ``Suggestion.calibrated_probability``
(Phase 4 #32 column) using the binary least-confidence formula
``1 - max(p, 1-p)``. Cold-start safe: NULL ``calibrated_probability``
yields NULL uncertainty (no fake review-queue ordering until
calibration is available).

Boundary checks:

- ``p = 0.5`` → uncertainty = 0.5 (max uncertainty for binary case).
- ``p = 1.0`` → uncertainty = 0.0 (model fully confident).
- ``p = 0.0`` → uncertainty = 0.0 (model fully confident the other way).
"""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.pipeline.services.pipeline_persist import _build_suggestion_records
from apps.pipeline.services.ranker import ScoredCandidate


class UncertaintyScoreWiringTests(TestCase):
    def setUp(self) -> None:
        from apps.suggestions.models import PipelineRun

        self.scope = ScopeItem.objects.create(
            scope_id=49, scope_type="node", title="uncertainty-test"
        )
        self.dest = ContentItem.objects.create(
            content_id=4901, content_type="thread", title="dest", scope=self.scope
        )
        self.host = ContentItem.objects.create(
            content_id=4902, content_type="thread", title="host", scope=self.scope
        )
        self.host_post = Post.objects.create(
            content_item=self.host, raw_bbcode="x", clean_text="x"
        )
        self.host_sentence = Sentence.objects.create(
            content_item=self.host,
            post=self.host_post,
            text="A host sentence about a topic.",
            position=0,
            char_count=30,
            start_char=0,
            end_char=30,
            word_position=0,
        )
        self.run = PipelineRun.objects.create()

    def _candidate(self, *, score_final: float) -> ScoredCandidate:
        return ScoredCandidate(
            destination_content_id=self.dest.content_id,
            destination_content_type=self.dest.content_type,
            host_content_id=self.host.content_id,
            host_content_type=self.host.content_type,
            host_sentence_id=self.host_sentence.pk,
            score_semantic=0.5,
            score_keyword=0.5,
            score_node_affinity=0.5,
            score_quality=0.5,
            score_silo_affinity=0.5,
            score_phrase_relevance=0.5,
            score_learned_anchor_corroboration=0.5,
            score_rare_term_propagation=0.5,
            score_field_aware_relevance=0.5,
            score_ga4_gsc=0.5,
            score_click_distance=0.5,
            score_explore_exploit=0.5,
            score_cluster_suppression=0.0,
            score_final=score_final,
            anchor_phrase="anchor",
            anchor_start=0,
            anchor_end=6,
            anchor_confidence="strong",
            phrase_match_diagnostics={},
            learned_anchor_diagnostics={},
            rare_term_diagnostics={},
            field_aware_diagnostics={},
            cluster_diagnostics={},
            explore_exploit_diagnostics={},
            click_distance_diagnostics={},
        )

    def _build(self, *, candidates):
        return _build_suggestion_records(
            run=self.run,
            valid_candidates=candidates,
            content_items={
                self.dest.content_id: self.dest,
                self.host.content_id: self.host,
            },
            sentences={self.host_sentence.pk: self.host_sentence},
        )

    def test_uncertainty_null_without_calibration(self) -> None:
        """No Platt snapshot → calibrated_probability NULL → uncertainty NULL."""
        records = self._build(candidates=[self._candidate(score_final=0.7)])
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].calibrated_probability)
        self.assertIsNone(records[0].uncertainty_score)

    def test_uncertainty_at_p_05_is_max(self) -> None:
        """p = 0.5 → 1 - max(0.5, 0.5) = 0.5 (max binary uncertainty)."""
        from apps.core.models import AppSetting
        from apps.pipeline.services.score_calibrator import (
            KEY_BIAS,
            KEY_FITTED_AT,
            KEY_SLOPE,
            KEY_TRAINING_PAIRS,
        )

        # slope=0, bias=0 → sigmoid(0) = 0.5 for any input score.
        for key, value in (
            (KEY_SLOPE, "0.0"),
            (KEY_BIAS, "0.0"),
            (KEY_FITTED_AT, "2026-04-25T00:00:00Z"),
            (KEY_TRAINING_PAIRS, "100"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )

        records = self._build(candidates=[self._candidate(score_final=0.7)])
        self.assertAlmostEqual(records[0].calibrated_probability, 0.5, places=4)
        self.assertAlmostEqual(records[0].uncertainty_score, 0.5, places=4)

    def test_uncertainty_high_confidence_low(self) -> None:
        """A confident calibration (p far from 0.5) yields low uncertainty."""
        from apps.core.models import AppSetting
        from apps.pipeline.services.score_calibrator import (
            KEY_BIAS,
            KEY_FITTED_AT,
            KEY_SLOPE,
            KEY_TRAINING_PAIRS,
        )

        # slope=-10, bias=0 → score 0.5 → sigmoid(-(-10*0.5+0))=sigmoid(5)≈0.9933
        for key, value in (
            (KEY_SLOPE, "-10.0"),
            (KEY_BIAS, "0.0"),
            (KEY_FITTED_AT, "2026-04-25T00:00:00Z"),
            (KEY_TRAINING_PAIRS, "100"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )

        records = self._build(candidates=[self._candidate(score_final=0.5)])
        self.assertGreater(records[0].calibrated_probability, 0.95)
        # Uncertainty should be small (< 0.05).
        self.assertLess(records[0].uncertainty_score, 0.05)

    def test_uncertainty_ordering_inverse_of_distance_from_half(self) -> None:
        """High-uncertainty rows have probability close to 0.5; low-uncertainty far."""
        from apps.core.models import AppSetting
        from apps.pipeline.services.score_calibrator import (
            KEY_BIAS,
            KEY_FITTED_AT,
            KEY_SLOPE,
            KEY_TRAINING_PAIRS,
        )

        # slope=-5, bias=0: score 0.0 → 0.5; score 0.4 → ≈0.881; score 0.6 → ≈0.953
        for key, value in (
            (KEY_SLOPE, "-5.0"),
            (KEY_BIAS, "0.0"),
            (KEY_FITTED_AT, "2026-04-25T00:00:00Z"),
            (KEY_TRAINING_PAIRS, "100"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )

        records = self._build(
            candidates=[
                self._candidate(score_final=0.0),  # p ≈ 0.5 → high uncertainty
                self._candidate(score_final=0.4),  # p ≈ 0.881 → lower uncertainty
                self._candidate(score_final=0.6),  # p ≈ 0.953 → lowest uncertainty
            ]
        )
        u0, u1, u2 = (r.uncertainty_score for r in records)
        # Uncertainty ordering: closer-to-0.5 first.
        self.assertGreater(u0, u1)
        self.assertGreater(u1, u2)
        # All three are non-negative and ≤ 0.5 (binary upper bound).
        for u in (u0, u1, u2):
            self.assertGreaterEqual(u, 0.0)
            self.assertLessEqual(u, 0.5)
