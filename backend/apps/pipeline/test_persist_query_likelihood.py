"""Integration test for pick #28 — QL-Dirichlet wiring into Suggestion writes.

Proof point: ``_build_suggestion_records`` populates
``Suggestion.score_query_likelihood`` from the same ``KeywordBaseline``
the keyword-stuffing detector already builds (no duplicate corpus
walk). When no baseline is supplied, the score stays at 0.0.

The QL helper is reused as-is — we only wire it through.
"""

from __future__ import annotations

from django.test import TestCase

from apps.content.models import ContentItem, Post, ScopeItem, Sentence
from apps.pipeline.services.pipeline_persist import _build_suggestion_records
from apps.pipeline.services.ranker import ScoredCandidate


class QueryLikelihoodWiringTests(TestCase):
    def setUp(self) -> None:
        from apps.suggestions.models import PipelineRun

        self.scope = ScopeItem.objects.create(
            scope_id=12, scope_type="node", title="ql-test"
        )
        self.dest = ContentItem.objects.create(
            content_id=901,
            content_type="thread",
            title="QL destination",
            scope=self.scope,
            distilled_text=(
                "internal links matter for SEO. "
                "Adding internal links across topical pages improves rankings."
            ),
        )
        self.host = ContentItem.objects.create(
            content_id=902,
            content_type="thread",
            title="QL host",
            scope=self.scope,
        )
        self.host_post = Post.objects.create(
            content_item=self.host, raw_bbcode="x", clean_text="x"
        )
        self.host_sentence = Sentence.objects.create(
            content_item=self.host,
            post=self.host_post,
            text="Internal links across pages matter for rankings.",
            position=0,
            char_count=49,
            start_char=0,
            end_char=49,
            word_position=0,
        )
        self.run = PipelineRun.objects.create()

    def _candidate(self) -> ScoredCandidate:
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
            score_final=0.7,
            anchor_phrase="internal links",
            anchor_start=0,
            anchor_end=14,
            anchor_confidence="strong",
            phrase_match_diagnostics={},
            learned_anchor_diagnostics={},
            rare_term_diagnostics={},
            field_aware_diagnostics={},
            cluster_diagnostics={},
            explore_exploit_diagnostics={},
            click_distance_diagnostics={},
        )

    def _build(self, *, keyword_baseline=None) -> list:
        return _build_suggestion_records(
            run=self.run,
            valid_candidates=[self._candidate()],
            content_items={
                self.dest.content_id: self.dest,
                self.host.content_id: self.host,
            },
            sentences={self.host_sentence.pk: self.host_sentence},
            keyword_baseline=keyword_baseline,
        )

    def test_score_zero_without_baseline(self) -> None:
        """No baseline → ``score_query_likelihood`` stays at 0.0 (cold start)."""
        records = self._build(keyword_baseline=None)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].score_query_likelihood, 0.0)

    def test_score_negative_with_baseline(self) -> None:
        """A real baseline yields a negative QL log-score (sum of log-probs ≤ 0)."""
        from apps.pipeline.services.keyword_stuffing import build_keyword_baseline
        from apps.pipeline.services.pipeline_data import (
            _load_content_records as _real_loader,  # noqa: F401 (proves the import path is real)
        )
        from apps.pipeline.services.ranker import ContentRecord

        # Build a tiny KeywordBaseline directly from a couple of in-memory
        # ContentRecords — the same shape the production loader produces.
        recs = {
            (1, "thread"): ContentRecord(
                content_id=1,
                content_type="thread",
                title="t1",
                distilled_text=("internal linking helps users find related content"),
                scope_id=0,
                scope_type="",
                parent_id=None,
                parent_type="",
                grandparent_id=None,
                grandparent_type="",
                silo_group_id=None,
                silo_group_name="",
                reply_count=0,
                march_2026_pagerank_score=0.0,
                link_freshness_score=0.5,
                primary_post_char_count=0,
                tokens=frozenset(
                    {"internal", "linking", "users", "related", "content"}
                ),
            ),
            (2, "thread"): ContentRecord(
                content_id=2,
                content_type="thread",
                title="t2",
                distilled_text=("topical pages matter for rankings and seo"),
                scope_id=0,
                scope_type="",
                parent_id=None,
                parent_type="",
                grandparent_id=None,
                grandparent_type="",
                silo_group_id=None,
                silo_group_name="",
                reply_count=0,
                march_2026_pagerank_score=0.0,
                link_freshness_score=0.5,
                primary_post_char_count=0,
                tokens=frozenset({"topical", "pages", "matter", "rankings", "seo"}),
            ),
        }
        baseline = build_keyword_baseline(recs)
        self.assertGreater(baseline.total_terms, 0)

        records = self._build(keyword_baseline=baseline)
        self.assertEqual(len(records), 1)
        # QL is a sum of log-probabilities → strictly ≤ 0. We only
        # assert it's non-zero (i.e. the wiring fired) and ≤ 0.
        self.assertLessEqual(records[0].score_query_likelihood, 0.0)
        self.assertNotEqual(records[0].score_query_likelihood, 0.0)

    def test_score_zero_when_baseline_total_terms_zero(self) -> None:
        """An empty corpus baseline still yields 0.0 (no crash, no fake score)."""
        from apps.pipeline.services.keyword_stuffing import KeywordBaseline

        empty = KeywordBaseline(
            term_counts={}, total_terms=0, doc_count=0, vocab_size=1
        )
        records = self._build(keyword_baseline=empty)
        self.assertEqual(records[0].score_query_likelihood, 0.0)
