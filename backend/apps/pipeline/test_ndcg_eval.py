"""Tests for the automated NDCG@K eval (Polish.B).

Per the plan:
- Cold-start (< 50 reviewed) → ``sufficient_data=False`` per Sanderson §5.2.
- Mid-data (50-199) → ``sufficient_for_pairwise=False`` but reads.
- Full-data (≥ 200) → both flags True.
- Bootstrap CI bounds the NDCG estimate.
- Per-candidate-origin breakdown surfaces only origins with ≥ basic floor.
"""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.pipeline.services.ndcg_eval import (
    DEFAULT_K,
    SANDERSON_BASIC_FLOOR,
    SANDERSON_PAIRWISE_FLOOR,
    bootstrap_ndcg_ci,
    evaluate,
    evaluate_and_persist,
    load_latest,
    sufficient_data,
)


class _Fixture:
    """Build N reviewed Suggestions with deterministic score-vs-label coupling."""

    @staticmethod
    def make_corpus():
        scope = ScopeItem.objects.create(
            scope_id=99, scope_type="node", title="ndcg-eval"
        )
        host_ci = ContentItem.objects.create(
            content_id=9900,
            content_type="thread",
            title="host",
            scope=scope,
        )
        host_post = Post.objects.create(
            content_item=host_ci, raw_bbcode="x", clean_text="x"
        )
        host_sentence = Sentence.objects.create(
            content_item=host_ci,
            post=host_post,
            text="A host sentence.",
            position=0,
            char_count=18,
            start_char=0,
            end_char=18,
            word_position=0,
        )
        dest_ci = ContentItem.objects.create(
            content_id=9901,
            content_type="thread",
            title="dest",
            scope=scope,
        )
        return scope, host_ci, host_sentence, dest_ci

    @staticmethod
    def make_reviewed_suggestions(
        *,
        host_ci,
        host_sentence,
        dest_ci,
        n: int,
        approved_ratio: float = 0.5,
        score_aligns_with_label: bool = True,
        candidate_origin: str = "semantic",
    ):
        """Bulk-create N reviewed suggestions.

        ``score_aligns_with_label=True`` → high-score rows are mostly
        approved (NDCG should be high). False → randomly approved
        (NDCG ≈ approved_ratio).
        """
        from apps.suggestions.models import PipelineRun, Suggestion

        run = PipelineRun.objects.create()
        rows = []
        approved_count = int(round(n * approved_ratio))
        for i in range(n):
            # Score uniformly in [0, 1]; if alignment is on, label =
            # approved iff in the top approved_count by score.
            score = (n - i) / n  # decreasing
            if score_aligns_with_label:
                status = "approved" if i < approved_count else "rejected"
            else:
                status = (
                    "approved" if i % int(round(1 / approved_ratio)) == 0 else "rejected"
                )
            rows.append(
                Suggestion(
                    pipeline_run=run,
                    destination=dest_ci,
                    host=host_ci,
                    host_sentence=host_sentence,
                    destination_title=f"dest-{i}",
                    host_sentence_text="A host sentence.",
                    anchor_phrase="anchor",
                    anchor_start=0,
                    anchor_end=6,
                    anchor_confidence="strong",
                    score_final=score,
                    status=status,
                    candidate_origin=candidate_origin,
                )
            )
        Suggestion.objects.bulk_create(rows)


class SufficientDataTests(TestCase):
    def test_below_basic_floor_unusable(self) -> None:
        usable, pairwise, _ = sufficient_data(SANDERSON_BASIC_FLOOR - 1)
        self.assertFalse(usable)
        self.assertFalse(pairwise)

    def test_at_basic_floor_usable(self) -> None:
        usable, pairwise, _ = sufficient_data(SANDERSON_BASIC_FLOOR)
        self.assertTrue(usable)
        # Still below pairwise floor.
        self.assertFalse(pairwise)

    def test_at_pairwise_floor_both_true(self) -> None:
        usable, pairwise, _ = sufficient_data(SANDERSON_PAIRWISE_FLOOR)
        self.assertTrue(usable)
        self.assertTrue(pairwise)


class BootstrapCITests(TestCase):
    def test_empty_returns_zeros(self) -> None:
        lo, hi = bootstrap_ndcg_ci([], iterations=10)
        self.assertEqual(lo, 0.0)
        self.assertEqual(hi, 0.0)

    def test_single_pair_returns_zeros(self) -> None:
        lo, hi = bootstrap_ndcg_ci([(0.5, 1.0)], iterations=10)
        self.assertEqual(lo, 0.0)
        self.assertEqual(hi, 0.0)

    def test_perfect_ranking_ci_close_to_one(self) -> None:
        # 10 pairs where score perfectly matches label → NDCG ≈ 1.0
        # → bootstrap CI should be tight around 1.0.
        pairs = [(1.0 - i * 0.05, 1.0 if i < 5 else 0.0) for i in range(10)]
        lo, hi = bootstrap_ndcg_ci(pairs, iterations=200)
        self.assertGreater(lo, 0.9)
        self.assertLessEqual(hi, 1.0 + 1e-9)


class EvaluateTests(TestCase):
    def test_cold_start_returns_insufficient(self) -> None:
        result = evaluate()
        self.assertEqual(result.sample_size, 0)
        self.assertFalse(result.sufficient_data)
        self.assertFalse(result.sufficient_for_pairwise)
        self.assertEqual(result.ndcg, 0.0)
        self.assertIn("Approve more", result.message)

    def test_below_basic_floor_returns_insufficient(self) -> None:
        scope, host, sentence, dest = _Fixture.make_corpus()
        _Fixture.make_reviewed_suggestions(
            host_ci=host,
            host_sentence=sentence,
            dest_ci=dest,
            n=SANDERSON_BASIC_FLOOR - 1,
        )
        result = evaluate()
        self.assertFalse(result.sufficient_data)
        self.assertEqual(result.sample_size, SANDERSON_BASIC_FLOOR - 1)
        self.assertEqual(result.ndcg, 0.0)

    def test_aligned_scores_yield_high_ndcg(self) -> None:
        """With score_final perfectly correlated with label, NDCG ≈ 1.0."""
        scope, host, sentence, dest = _Fixture.make_corpus()
        _Fixture.make_reviewed_suggestions(
            host_ci=host,
            host_sentence=sentence,
            dest_ci=dest,
            n=SANDERSON_BASIC_FLOOR + 50,
            score_aligns_with_label=True,
        )
        result = evaluate()
        self.assertTrue(result.sufficient_data)
        # Confidence band brackets the point estimate.
        self.assertLessEqual(result.confidence_lower, result.ndcg + 1e-6)
        self.assertGreaterEqual(result.confidence_upper, result.ndcg - 1e-6)
        # NDCG is high (perfect alignment under monotone scores).
        self.assertGreater(result.ndcg, 0.9)

    def test_mid_data_flags_pairwise_insufficient(self) -> None:
        scope, host, sentence, dest = _Fixture.make_corpus()
        _Fixture.make_reviewed_suggestions(
            host_ci=host,
            host_sentence=sentence,
            dest_ci=dest,
            n=SANDERSON_BASIC_FLOOR + 5,
        )
        result = evaluate()
        self.assertTrue(result.sufficient_data)
        self.assertFalse(result.sufficient_for_pairwise)
        self.assertIn("wide", result.message)

    def test_full_data_flags_pairwise_ready(self) -> None:
        scope, host, sentence, dest = _Fixture.make_corpus()
        _Fixture.make_reviewed_suggestions(
            host_ci=host,
            host_sentence=sentence,
            dest_ci=dest,
            n=SANDERSON_PAIRWISE_FLOOR + 10,
        )
        result = evaluate()
        self.assertTrue(result.sufficient_data)
        self.assertTrue(result.sufficient_for_pairwise)
        self.assertIn("sufficient", result.message.lower())

    def test_breakdown_by_candidate_origin(self) -> None:
        """Per-origin breakdown only includes origins above the basic floor."""
        scope, host, sentence, dest = _Fixture.make_corpus()
        _Fixture.make_reviewed_suggestions(
            host_ci=host,
            host_sentence=sentence,
            dest_ci=dest,
            n=SANDERSON_BASIC_FLOOR + 30,
            candidate_origin="semantic",
        )
        # 'graph_walk' origin gets only 10 rows — below floor.
        _Fixture.make_reviewed_suggestions(
            host_ci=host,
            host_sentence=sentence,
            dest_ci=dest,
            n=10,
            candidate_origin="graph_walk",
        )
        result = evaluate()
        # 'semantic' has > 50 rows → in breakdown.
        self.assertIn("semantic", result.breakdown_by_candidate_origin)
        # 'graph_walk' has < 50 → excluded.
        self.assertNotIn("graph_walk", result.breakdown_by_candidate_origin)


class PersistAndLoadTests(TestCase):
    def test_load_latest_cold_start_returns_none(self) -> None:
        self.assertIsNone(load_latest())

    def test_persist_round_trip(self) -> None:
        scope, host, sentence, dest = _Fixture.make_corpus()
        _Fixture.make_reviewed_suggestions(
            host_ci=host,
            host_sentence=sentence,
            dest_ci=dest,
            n=SANDERSON_BASIC_FLOOR + 5,
        )
        evaluate_and_persist()
        loaded = load_latest()
        self.assertIsNotNone(loaded)
        self.assertTrue(loaded.sufficient_data)
        self.assertGreaterEqual(loaded.sample_size, SANDERSON_BASIC_FLOOR)
