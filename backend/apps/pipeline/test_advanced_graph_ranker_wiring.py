"""Tests for FR-260 to FR-265 ranker and pipeline wiring."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.content.models import ContentItem
from apps.graph.models import GraphSignalRun, NodeGraphSignal
from apps.pipeline.services.advanced_graph_signals import (
    AdvancedGraphSignalsEvaluation,
    AdvancedGraphSignalsSettings,
    ICPCSettings,
    SBMASettings,
)
from apps.pipeline.services.pipeline_data import _build_advanced_graph_signals_caches
from apps.pipeline.services.ranker import score_destination_matches
from apps.pipeline.services.ranker_types import (
    ContentRecord,
    SentenceRecord,
    SentenceSemanticMatch,
)


def _record(content_id: int, *, silo_group_id: int | None = 1) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        content_type="thread",
        title=f"Page {content_id}",
        distilled_text="Detailed page text about the shared topic.",
        scope_id=content_id,
        scope_type="node",
        parent_id=None,
        parent_type="",
        grandparent_id=None,
        grandparent_type="",
        silo_group_id=silo_group_id,
        silo_group_name="Main" if silo_group_id else "",
        reply_count=0,
        march_2026_pagerank_score=0.0,
        link_freshness_score=0.5,
        primary_post_char_count=400,
        tokens=frozenset({"shared", "topic"}),
    )


def _sentence(sentence_id: int, host_id: int) -> SentenceRecord:
    return SentenceRecord(
        sentence_id=sentence_id,
        content_id=host_id,
        content_type="thread",
        text="This source sentence has enough useful detail about the shared topic.",
        char_count=67,
        tokens=frozenset({"shared", "topic"}),
    )


class AdvancedGraphCacheBuilderTests(TestCase):
    def test_icpc_cache_uses_current_graph_snapshot_degrees(self):
        items = [
            ContentItem.objects.create(content_id=i, content_type="thread")
            for i in range(1, 12)
        ]
        run = GraphSignalRun.objects.create(
            graph_hash="hash",
            signal_version="v1",
            node_count=11,
            edge_count=3,
            status=GraphSignalRun.STATUS_CURRENT,
        )
        for item in items[:10]:
            NodeGraphSignal.objects.create(
                run=run,
                content_item=item,
                community_id=7,
                icpc_local_indegree=2 if item == items[0] else 0,
                icpc_global_indegree=3 if item == items[0] else 0,
            )
        NodeGraphSignal.objects.create(run=run, content_item=items[10], community_id=8)
        records = {
            (item.pk, "thread"): _record(item.pk)
            for item in (items[0], items[1], items[2], items[10])
        }

        caches = _build_advanced_graph_signals_caches(
            content_records=records,
            advanced_graph_signals_settings=AdvancedGraphSignalsSettings(
                icpc=ICPCSettings(min_community_size=10)
            ),
            progress_fn=lambda *_args, **_kwargs: None,
        )

        if caches is None:
            self.fail("Expected advanced graph signal caches to be built.")
        dest_index = caches.node_to_index[(items[0].pk, "thread")]
        self.assertEqual(caches.global_degrees[dest_index], 3)
        self.assertEqual(caches.local_degrees[dest_index], 2)

    def test_sbma_cache_uses_current_graph_snapshot_blocks(self):
        host = ContentItem.objects.create(content_id=21, content_type="thread")
        dest = ContentItem.objects.create(content_id=22, content_type="thread")
        run = GraphSignalRun.objects.create(
            graph_hash="hash",
            signal_version="v1",
            node_count=2,
            edge_count=1,
            status=GraphSignalRun.STATUS_CURRENT,
            sbma_matrix_json={"0:1": 0.75},
        )
        NodeGraphSignal.objects.create(
            run=run,
            content_item=host,
            community_id=1,
            sbma_block_id=0,
        )
        NodeGraphSignal.objects.create(
            run=run,
            content_item=dest,
            community_id=2,
            sbma_block_id=1,
        )
        records = {
            (host.pk, "thread"): _record(host.pk),
            (dest.pk, "thread"): _record(dest.pk),
        }

        caches = _build_advanced_graph_signals_caches(
            content_records=records,
            advanced_graph_signals_settings=AdvancedGraphSignalsSettings(
                sbma=SBMASettings(num_blocks=2)
            ),
            progress_fn=lambda *_args, **_kwargs: None,
        )

        if caches is None:
            self.fail("Expected advanced graph signal caches to be built.")
        host_index = caches.node_to_index[(host.pk, "thread")]
        dest_index = caches.node_to_index[(dest.pk, "thread")]
        self.assertEqual(caches.node_blocks[host_index], 0)
        self.assertEqual(caches.node_blocks[dest_index], 1)
        self.assertEqual(caches.block_transition_matrix[(0, 1)], 0.75)


class AdvancedGraphRankerWiringTests(TestCase):
    def test_ranker_adds_advanced_graph_scores_and_uses_host_silo(self):
        destination = _record(100, silo_group_id=1)
        same_host = _record(200, silo_group_id=1)
        cross_host = _record(300, silo_group_id=2)
        records = {
            destination.key: destination,
            same_host.key: same_host,
            cross_host.key: cross_host,
        }
        sentences = {
            1: _sentence(1, same_host.content_id),
            2: _sentence(2, cross_host.content_id),
        }
        matches = [
            SentenceSemanticMatch(same_host.content_id, "thread", 1, 0.8),
            SentenceSemanticMatch(cross_host.content_id, "thread", 2, 0.8),
        ]
        evals = [
            AdvancedGraphSignalsEvaluation(
                weighted_contribution=0.11,
                per_signal_scores={"score_icpc": 0.7},
                per_signal_diagnostics={"icpc_diagnostics": {"score": 0.7}},
            ),
            AdvancedGraphSignalsEvaluation(
                weighted_contribution=0.13,
                per_signal_scores={"score_icpc": 0.9},
                per_signal_diagnostics={"icpc_diagnostics": {"score": 0.9}},
            ),
        ]

        with patch(
            "apps.pipeline.services.advanced_graph_signals."
            "evaluate_advanced_graph_signals_batch",
            return_value=evals,
        ) as mock_eval:
            scored = score_destination_matches(
                destination,
                matches,
                content_records=records,
                sentence_records=sentences,
                existing_links=set(),
                weights={
                    "w_semantic": 1.0,
                    "w_keyword": 0.0,
                    "w_node": 0.0,
                    "w_quality": 0.0,
                },
                march_2026_pagerank_bounds=(0.0, 1.0),
                advanced_graph_signals_caches=object(),
                advanced_graph_signals_settings=AdvancedGraphSignalsSettings(),
            )

        self.assertEqual(mock_eval.call_args.args[3], [False, True])
        by_host = {candidate.host_content_id: candidate for candidate in scored}
        self.assertAlmostEqual(by_host[200].score_icpc, 0.7)
        self.assertEqual(by_host[200].icpc_diagnostics, {"score": 0.7})
        self.assertAlmostEqual(by_host[300].score_icpc, 0.9)
