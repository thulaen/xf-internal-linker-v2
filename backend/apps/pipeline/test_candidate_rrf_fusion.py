"""Tests for W3d — candidate_rrf_fusion service (pick #31 wiring)."""

from __future__ import annotations

from django.test import TestCase

from apps.pipeline.services.candidate_rrf_fusion import (
    DEFAULT_GRAPH_SIGNALS,
    FusionResult,
    fuse_candidates,
)
from apps.pipeline.services.graph_signal_store import (
    SIGNAL_HITS_AUTHORITY,
    SIGNAL_TRUSTRANK,
    persist_top_n,
)


class FuseCandidatesPrimaryOnlyTests(TestCase):
    def test_single_ranker_preserves_order(self) -> None:
        result = fuse_candidates({"semantic": ["a", "b", "c"]})
        self.assertIsInstance(result, FusionResult)
        self.assertEqual([item.doc_id for item in result.fused], ["a", "b", "c"])
        self.assertEqual(result.contributing_rankers, ["semantic"])
        self.assertEqual(result.graph_signals_used, [])

    def test_multiple_rankers_fuse_to_consensus(self) -> None:
        result = fuse_candidates(
            {
                "semantic": ["a", "b", "c"],
                "bm25": ["a", "c", "b"],
            }
        )
        # "a" appears top in both → highest fused score.
        self.assertEqual(result.fused[0].doc_id, "a")

    def test_empty_rankings_returns_empty(self) -> None:
        result = fuse_candidates({})
        self.assertEqual(result.fused, [])
        self.assertEqual(result.contributing_rankers, [])

    def test_top_n_truncates_output(self) -> None:
        result = fuse_candidates(
            {"semantic": ["a", "b", "c", "d", "e"]},
            top_n=2,
        )
        self.assertEqual(len(result.fused), 2)


class FuseCandidatesWithGraphSignalsTests(TestCase):
    def test_graph_signals_off_by_default(self) -> None:
        # Even with persisted graph data, default behaviour ignores
        # the store unless include_graph_signals=True.
        persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY,
            scores={(1, "thread"): 0.9, (2, "thread"): 0.5},
        )
        result = fuse_candidates({"semantic": [(1, "thread")]})
        self.assertEqual(result.graph_signals_used, [])
        self.assertEqual(result.contributing_rankers, ["semantic"])

    def test_graph_signals_injected_when_requested(self) -> None:
        persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY,
            scores={(1, "thread"): 0.9, (2, "thread"): 0.5},
        )
        result = fuse_candidates(
            {"semantic": [(2, "thread"), (1, "thread")]},
            include_graph_signals=True,
            graph_signals=[SIGNAL_HITS_AUTHORITY],
        )
        self.assertIn(SIGNAL_HITS_AUTHORITY, result.graph_signals_used)
        self.assertIn(f"graph:{SIGNAL_HITS_AUTHORITY}", result.contributing_rankers)
        # (1, "thread") wins because semantic ranks it 2nd while HITS
        # ranks it 1st — fused score lifts it above (2, "thread") which
        # only ranks well in semantic.
        self.assertEqual(result.fused[0].doc_id, (1, "thread"))

    def test_graph_signal_skipped_when_store_empty(self) -> None:
        # No persist call → graph store is empty for this signal.
        result = fuse_candidates(
            {"semantic": [(1, "thread"), (2, "thread")]},
            include_graph_signals=True,
            graph_signals=[SIGNAL_TRUSTRANK],
        )
        # No graph rankings spliced — only the primary ranker counts.
        self.assertEqual(result.graph_signals_used, [])
        self.assertEqual(result.contributing_rankers, ["semantic"])

    def test_candidate_universe_restricts_graph_rankings(self) -> None:
        persist_top_n(
            signal=SIGNAL_TRUSTRANK,
            scores={
                (1, "thread"): 0.9,
                (99, "resource"): 0.95,  # not in universe
                (2, "thread"): 0.4,
            },
        )
        result = fuse_candidates(
            {"semantic": [(1, "thread"), (2, "thread")]},
            include_graph_signals=True,
            graph_signals=[SIGNAL_TRUSTRANK],
            candidate_universe=[(1, "thread"), (2, "thread")],
        )
        # The "out-of-universe" id (99) should NOT appear in the fused
        # output even though it's the top-scoring node in TrustRank.
        fused_ids = {item.doc_id for item in result.fused}
        self.assertEqual(fused_ids, {(1, "thread"), (2, "thread")})

    def test_default_graph_signals_constant(self) -> None:
        # Sanity check that the default tuple covers HITS authority,
        # PPR, and TrustRank (the three readable graph signals from
        # W3c). Keeps the fusion's "include_graph_signals=True" sane
        # by default without operator config.
        from apps.pipeline.services.graph_signal_store import (
            SIGNAL_HITS_AUTHORITY,
            SIGNAL_PPR,
            SIGNAL_TRUSTRANK,
        )

        self.assertIn(SIGNAL_HITS_AUTHORITY, DEFAULT_GRAPH_SIGNALS)
        self.assertIn(SIGNAL_PPR, DEFAULT_GRAPH_SIGNALS)
        self.assertIn(SIGNAL_TRUSTRANK, DEFAULT_GRAPH_SIGNALS)
