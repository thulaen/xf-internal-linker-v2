"""Integration test for pick #32 — Platt calibration wiring into Suggestion writes.

Proof point: ``_build_suggestion_records`` populates
``Suggestion.calibrated_probability`` from the persisted Platt
snapshot when one exists, and leaves it NULL when no snapshot has
been fitted yet (the cold-start case the Explain panel UI already
expects).

The snapshot is loaded **once** per call (not per row) so a 1000-
candidate batch costs one AppSetting query, not 1000.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.content.models import ContentItem, ScopeItem, Sentence, Post
from apps.pipeline.services.pipeline_persist import _build_suggestion_records
from apps.pipeline.services.ranker import ScoredCandidate


class _PipelineRunStub:
    """Minimal stand-in for the ``PipelineRun`` foreign key.

    Only the constructor reads ``.pk`` / ``.id`` indirectly through
    Django's FK assignment, so we use a real PipelineRun.
    """


class PlattCalibrationWiringTests(TestCase):
    def setUp(self) -> None:
        from apps.suggestions.models import PipelineRun

        self.scope = ScopeItem.objects.create(
            scope_id=11, scope_type="node", title="platt-test"
        )
        self.dest = ContentItem.objects.create(
            content_id=801, content_type="thread", title="Dest", scope=self.scope
        )
        self.host = ContentItem.objects.create(
            content_id=802, content_type="thread", title="Host", scope=self.scope
        )
        # Sentence requires a Post.
        self.host_post = Post.objects.create(
            content_item=self.host, raw_bbcode="x", clean_text="x"
        )
        self.host_sentence = Sentence.objects.create(
            content_item=self.host,
            post=self.host_post,
            text="Some host sentence about the topic.",
            position=0,
            char_count=37,
            start_char=0,
            end_char=37,
            word_position=0,
        )
        self.run = PipelineRun.objects.create()

    def _candidate(self, *, score_final: float = 0.7) -> ScoredCandidate:
        # Build a minimum-viable ScoredCandidate. Most diagnostic
        # fields are unused by _build_suggestion_records — the only
        # things it reads are score_*, anchor_*, and IDs.
        return ScoredCandidate(
            destination_content_id=self.dest.content_id,
            destination_content_type=self.dest.content_type,
            host_content_id=self.host.content_id,
            host_content_type=self.host.content_type,
            host_sentence_id=self.host_sentence.pk,
            score_semantic=0.8,
            score_keyword=0.6,
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
            anchor_phrase="link",
            anchor_start=0,
            anchor_end=4,
            anchor_confidence="strong",
            phrase_match_diagnostics={},
            learned_anchor_diagnostics={},
            rare_term_diagnostics={},
            field_aware_diagnostics={},
            cluster_diagnostics={},
            explore_exploit_diagnostics={},
            click_distance_diagnostics={},
        )

    def _build(self, candidates: list[ScoredCandidate]) -> list:
        return _build_suggestion_records(
            run=self.run,
            valid_candidates=candidates,
            content_items={
                self.dest.content_id: self.dest,
                self.host.content_id: self.host,
            },
            sentences={self.host_sentence.pk: self.host_sentence},
        )

    def test_calibrated_probability_null_without_snapshot(self) -> None:
        """Cold start — no Platt snapshot persisted → NULL on every row."""
        # No AppSetting populated → load_snapshot returns None.
        records = self._build([self._candidate(score_final=0.7)])
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0].calibrated_probability)

    def test_calibrated_probability_populated_from_snapshot(self) -> None:
        """A persisted snapshot drives a real probability for every row."""
        from apps.core.models import AppSetting
        from apps.pipeline.services.score_calibrator import (
            KEY_BIAS,
            KEY_FITTED_AT,
            KEY_SLOPE,
            KEY_TRAINING_PAIRS,
        )

        # Persist a known Platt snapshot via the four canonical
        # AppSetting keys the W3a fit-job writes. Slope = -5, bias = 0
        # → sigmoid uses ``A*f + B`` in the denominator, so score 0.5
        # → 1/(1+exp(-2.5)) ≈ 0.924; score 0.0 → 1/(1+exp(0)) = 0.5.
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
            [
                self._candidate(score_final=0.5),
                self._candidate(score_final=0.0),
            ]
        )
        self.assertEqual(len(records), 2)
        self.assertIsNotNone(records[0].calibrated_probability)
        self.assertAlmostEqual(records[0].calibrated_probability, 0.924, places=2)
        # Score 0.0 → sigmoid(0) = 0.5.
        self.assertAlmostEqual(records[1].calibrated_probability, 0.5, places=2)

    def test_snapshot_loaded_once_per_call(self) -> None:
        """A 3-candidate batch causes exactly one snapshot load, not three."""
        from apps.pipeline.services import score_calibrator

        # Stub the loader to return a usable snapshot but count calls.
        snapshot = score_calibrator.CalibrationSnapshot(
            slope=-2.0, bias=0.0, fitted_at=None, training_pairs=10
        )
        with patch.object(
            score_calibrator,
            "load_snapshot",
            return_value=snapshot,
        ) as load_mock:
            records = self._build(
                [
                    self._candidate(score_final=0.3),
                    self._candidate(score_final=0.5),
                    self._candidate(score_final=0.7),
                ]
            )
        self.assertEqual(load_mock.call_count, 1)
        self.assertEqual(len(records), 3)
        # Each row got a calibrated probability.
        for r in records:
            self.assertIsNotNone(r.calibrated_probability)
            self.assertGreaterEqual(r.calibrated_probability, 0.0)
            self.assertLessEqual(r.calibrated_probability, 1.0)
