"""Tests for pick #50 split-conformal end-to-end wiring.

Three concerns:

1. **Producer fits and persists** the four AppSetting rows when the
   reviewed-Suggestion calibration set passes the minimum size.
2. **Cold-start path** returns ``None`` when too few pairs exist,
   keeping the consumer-side bounds NULL.
3. **Consumer wires through** ``_build_suggestion_records`` so per-
   row ``confidence_lower_bound`` / ``upper_bound`` are populated
   when a snapshot exists, and stay NULL when it doesn't.
"""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.pipeline.services.conformal_predictor import (
    KEY_ALPHA,
    KEY_CALIBRATION_SET_SIZE,
    KEY_FITTED_AT,
    KEY_HALF_WIDTH,
    MIN_CALIBRATION_PAIRS,
    fit_and_persist_from_history,
    load_snapshot,
)
from apps.pipeline.services.pipeline_persist import _build_suggestion_records
from apps.pipeline.services.ranker import ScoredCandidate


class _Fixture:
    @staticmethod
    def make_history_pairs(*, n_positive: int, n_negative: int):
        """Create reviewed Suggestions for a calibration set.

        Reuses one host sentence + a single destination so the rows
        differ only in score_final / status — keeps the test compact.
        """
        from apps.suggestions.models import PipelineRun, Suggestion

        scope = ScopeItem.objects.create(scope_id=50, scope_type="node", title="cnf")
        host = ContentItem.objects.create(
            content_id=5000, content_type="thread", title="host", scope=scope
        )
        host_post = Post.objects.create(
            content_item=host, raw_bbcode="x", clean_text="x"
        )
        host_sentence = Sentence.objects.create(
            content_item=host,
            post=host_post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )
        dest = ContentItem.objects.create(
            content_id=5001, content_type="thread", title="dest", scope=scope
        )
        run = PipelineRun.objects.create()

        # Use a spread of score_final values so the conformal quantile
        # is non-trivial (real production data has variance; degenerate
        # all-equal scores would yield half_width=0).
        for i in range(n_positive):
            Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host,
                host_sentence=host_sentence,
                destination_title="dest",
                host_sentence_text="A host sentence.",
                anchor_phrase="anchor",
                anchor_start=0,
                anchor_end=6,
                anchor_confidence="strong",
                score_final=0.7 + 0.005 * (i % 20),
                status="approved",
            )
        for i in range(n_negative):
            Suggestion.objects.create(
                pipeline_run=run,
                destination=dest,
                host=host,
                host_sentence=host_sentence,
                destination_title="dest",
                host_sentence_text="A host sentence.",
                anchor_phrase="anchor",
                anchor_start=0,
                anchor_end=6,
                anchor_confidence="strong",
                score_final=0.3 + 0.005 * (i % 20),
                status="rejected",
            )
        return scope, host, host_sentence, dest, run


class ConformalProducerTests(TestCase):
    def test_cold_start_returns_none_below_minimum(self) -> None:
        """Fewer than ``MIN_CALIBRATION_PAIRS`` reviewed → no fit."""
        _Fixture.make_history_pairs(n_positive=5, n_negative=5)
        self.assertLess(10, MIN_CALIBRATION_PAIRS)

        snapshot = fit_and_persist_from_history()
        self.assertIsNone(snapshot)
        # No AppSetting rows written.
        from apps.core.models import AppSetting

        self.assertFalse(AppSetting.objects.filter(key=KEY_ALPHA).exists())

    def test_fit_persists_four_appsetting_rows(self) -> None:
        """A fit writes alpha / half_width / size / fitted_at."""
        _Fixture.make_history_pairs(n_positive=20, n_negative=20)
        # 40 ≥ MIN_CALIBRATION_PAIRS=30
        snapshot = fit_and_persist_from_history()
        self.assertIsNotNone(snapshot)

        loaded = load_snapshot()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.calibration_set_size, 40)
        self.assertGreater(loaded.half_width, 0.0)
        self.assertEqual(loaded.alpha, 0.10)
        self.assertIsNotNone(loaded.fitted_at)

        # All four canonical keys exist.
        from apps.core.models import AppSetting

        for key in (KEY_ALPHA, KEY_HALF_WIDTH, KEY_CALIBRATION_SET_SIZE, KEY_FITTED_AT):
            self.assertTrue(AppSetting.objects.filter(key=key).exists())

    def test_load_snapshot_cold_start_returns_none(self) -> None:
        """No fit yet → ``load_snapshot`` returns None."""
        self.assertIsNone(load_snapshot())


class ConformalConsumerWiringTests(TestCase):
    def setUp(self) -> None:
        from apps.suggestions.models import PipelineRun

        self.scope = ScopeItem.objects.create(
            scope_id=51, scope_type="node", title="cnf-consumer"
        )
        self.dest = ContentItem.objects.create(
            content_id=5101, content_type="thread", title="dest", scope=self.scope
        )
        self.host = ContentItem.objects.create(
            content_id=5102, content_type="thread", title="host", scope=self.scope
        )
        self.host_post = Post.objects.create(
            content_item=self.host, raw_bbcode="x", clean_text="x"
        )
        self.host_sentence = Sentence.objects.create(
            content_item=self.host,
            post=self.host_post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )
        self.run = PipelineRun.objects.create()

    def _candidate(self, *, score_final: float = 0.5) -> ScoredCandidate:
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

    def _build(self):
        return _build_suggestion_records(
            run=self.run,
            valid_candidates=[self._candidate(score_final=0.6)],
            content_items={
                self.dest.content_id: self.dest,
                self.host.content_id: self.host,
            },
            sentences={self.host_sentence.pk: self.host_sentence},
        )

    def test_bounds_null_without_calibration(self) -> None:
        """Cold start → both bounds NULL."""
        records = self._build()
        self.assertIsNone(records[0].confidence_lower_bound)
        self.assertIsNone(records[0].confidence_upper_bound)

    def test_bounds_populated_after_fit(self) -> None:
        """A persisted snapshot drives both bounds for every row."""
        from apps.core.models import AppSetting

        # Persist a known snapshot directly via AppSetting.
        for key, value in (
            (KEY_ALPHA, "0.10"),
            (KEY_HALF_WIDTH, "0.15"),
            (KEY_CALIBRATION_SET_SIZE, "100"),
            (KEY_FITTED_AT, "2026-04-25T00:00:00Z"),
        ):
            AppSetting.objects.update_or_create(
                key=key, defaults={"value": value, "description": ""}
            )

        records = self._build()
        # score_final=0.6 ± 0.15 → [0.45, 0.75]
        self.assertAlmostEqual(records[0].confidence_lower_bound, 0.45, places=4)
        self.assertAlmostEqual(records[0].confidence_upper_bound, 0.75, places=4)
