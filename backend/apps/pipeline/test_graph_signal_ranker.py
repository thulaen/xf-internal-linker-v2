"""Tests for W3c — graph_signal_ranker (live ranker integration of picks #29 / #30 / #36).

Two layers of tests:

1. **Unit tests** (no DB) — exercise ``GraphSignalRanker`` math and the
   ``build_graph_signal_ranker`` factory's None paths via injected stubs.

2. **Integration test** (DB-backed via Django ``TestCase``) — persist a
   real HITS-authority snapshot and prove that
   :func:`apps.pipeline.services.ranker.score_destination_matches`
   honours it: the per-candidate ``score_final`` rises by exactly
   ``weight × (score − 0.5)`` when the ranker is wired.

The integration test is the proof point that closes the W3c loop —
before this slice the snapshot was persisted but never read by the
live ranker.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.pipeline.services.graph_signal_ranker import (
    GraphSignalRanker,
    build_graph_signal_ranker,
)
from apps.pipeline.services.graph_signal_store import (
    GraphSignalSnapshot,
    NEUTRAL_SCORE,
    SIGNAL_HITS_AUTHORITY,
    SIGNAL_PPR,
    SIGNAL_TRUSTRANK,
    persist_top_n,
)
from apps.pipeline.services.ranker import (
    ContentRecord,
    SentenceRecord,
    SentenceSemanticMatch,
    score_destination_matches,
)


# ── Helpers ────────────────────────────────────────────────────────


def _snapshot(signal: str, scores: dict[str, float]) -> GraphSignalSnapshot:
    """In-memory snapshot — no DB round-trip."""
    return GraphSignalSnapshot(
        signal=signal,
        scores=scores,
        fitted_at=None,
        full_node_count=len(scores),
    )


def _content_record(*, content_id: int) -> ContentRecord:
    return ContentRecord(
        content_id=content_id,
        content_type="thread",
        title=f"Item {content_id}",
        distilled_text="Topic body",
        scope_id=content_id,
        scope_type="node",
        parent_id=None,
        parent_type="",
        grandparent_id=None,
        grandparent_type="",
        silo_group_id=None,
        silo_group_name="",
        reply_count=5,
        march_2026_pagerank_score=0.0,
        link_freshness_score=0.5,
        content_value_score=0.0,
        primary_post_char_count=500,
        tokens=frozenset({"topic", str(content_id)}),
    )


# ── Unit tests on GraphSignalRanker math ───────────────────────────


class GraphSignalRankerMathTests(SimpleTestCase):
    """Pure math — no DB. Inject snapshots directly."""

    def test_contribution_zero_with_no_snapshots(self) -> None:
        ranker = GraphSignalRanker(weights={SIGNAL_HITS_AUTHORITY: 0.10})
        self.assertEqual(ranker.contribution((1, "thread")), 0.0)

    def test_contribution_zero_with_zero_weight(self) -> None:
        ranker = GraphSignalRanker(
            weights={SIGNAL_HITS_AUTHORITY: 0.0},
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"1:thread": 0.9}
                )
            },
        )
        self.assertEqual(ranker.contribution((1, "thread")), 0.0)

    def test_contribution_zero_at_neutral_score(self) -> None:
        # score == 0.5 is the project-wide neutral baseline → contribution = 0
        ranker = GraphSignalRanker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"1:thread": 0.5}
                )
            },
        )
        self.assertAlmostEqual(ranker.contribution((1, "thread")), 0.0)

    def test_contribution_positive_above_neutral(self) -> None:
        # 0.10 * (0.9 - 0.5) = 0.04
        ranker = GraphSignalRanker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"1:thread": 0.9}
                )
            },
        )
        self.assertAlmostEqual(ranker.contribution((1, "thread")), 0.04, places=6)

    def test_contribution_negative_below_neutral(self) -> None:
        # 0.10 * (0.1 - 0.5) = -0.04
        ranker = GraphSignalRanker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"1:thread": 0.1}
                )
            },
        )
        self.assertAlmostEqual(ranker.contribution((1, "thread")), -0.04, places=6)

    def test_contribution_sums_across_signals(self) -> None:
        # HITS: 0.10 * (0.9 - 0.5) = 0.04
        # PPR:  0.05 * (0.7 - 0.5) = 0.01
        # Trust: 0.0 — disabled, no contribution
        ranker = GraphSignalRanker(
            weights={
                SIGNAL_HITS_AUTHORITY: 0.10,
                SIGNAL_PPR: 0.05,
                SIGNAL_TRUSTRANK: 0.0,
            },
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"1:thread": 0.9}
                ),
                SIGNAL_PPR: _snapshot(SIGNAL_PPR, {"1:thread": 0.7}),
                SIGNAL_TRUSTRANK: _snapshot(SIGNAL_TRUSTRANK, {"1:thread": 0.95}),
            },
        )
        self.assertAlmostEqual(ranker.contribution((1, "thread")), 0.05, places=6)

    def test_unknown_node_returns_neutral_per_signal(self) -> None:
        # Node not in any snapshot → all signals neutral → contribution 0
        ranker = GraphSignalRanker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"42:thread": 0.9}
                )
            },
        )
        self.assertAlmostEqual(ranker.contribution((999, "thread")), 0.0)

    def test_per_signal_scores_returns_neutral_for_missing(self) -> None:
        ranker = GraphSignalRanker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"1:thread": 0.9}
                )
            },
        )
        scores = ranker.per_signal_scores((1, "thread"))
        self.assertAlmostEqual(scores[SIGNAL_HITS_AUTHORITY], 0.9)
        # PPR / TrustRank not in snapshots → neutral
        self.assertEqual(scores[SIGNAL_PPR], NEUTRAL_SCORE)
        self.assertEqual(scores[SIGNAL_TRUSTRANK], NEUTRAL_SCORE)

    def test_is_active_true_when_signal_has_weight_and_snapshot(self) -> None:
        ranker = GraphSignalRanker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"1:thread": 0.9}
                )
            },
        )
        self.assertTrue(ranker.is_active)

    def test_is_active_false_when_zero_weight(self) -> None:
        ranker = GraphSignalRanker(
            weights={SIGNAL_HITS_AUTHORITY: 0.0},
            snapshots={
                SIGNAL_HITS_AUTHORITY: _snapshot(
                    SIGNAL_HITS_AUTHORITY, {"1:thread": 0.9}
                )
            },
        )
        self.assertFalse(ranker.is_active)


# ── Factory tests using injected loader stubs ──────────────────────


class BuildGraphSignalRankerTests(SimpleTestCase):
    def test_returns_none_when_disabled(self) -> None:
        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
            enabled=False,
            load_snapshot_fn=lambda s: _snapshot(s, {"1:thread": 0.9}),
        )
        self.assertIsNone(ranker)

    def test_returns_none_when_all_weights_zero(self) -> None:
        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.0, SIGNAL_PPR: 0.0},
            load_snapshot_fn=lambda s: _snapshot(s, {"1:thread": 0.9}),
        )
        self.assertIsNone(ranker)

    def test_returns_none_when_no_snapshots_persisted(self) -> None:
        # Loader returns None for every signal → cold start
        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10, SIGNAL_PPR: 0.05},
            load_snapshot_fn=lambda s: None,
        )
        self.assertIsNone(ranker)

    def test_skips_zero_weight_signals(self) -> None:
        # Only HITS has a non-zero weight, so only HITS snapshot should be loaded
        loaded: list[str] = []

        def stub_loader(signal: str) -> GraphSignalSnapshot | None:
            loaded.append(signal)
            return _snapshot(signal, {"1:thread": 0.9})

        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10, SIGNAL_PPR: 0.0},
            load_snapshot_fn=stub_loader,
        )
        self.assertIsNotNone(ranker)
        self.assertEqual(loaded, [SIGNAL_HITS_AUTHORITY])

    def test_returns_ranker_when_at_least_one_snapshot_exists(self) -> None:
        def stub_loader(signal: str) -> GraphSignalSnapshot | None:
            if signal == SIGNAL_HITS_AUTHORITY:
                return _snapshot(signal, {"1:thread": 0.9})
            return None  # PPR cold

        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10, SIGNAL_PPR: 0.05},
            load_snapshot_fn=stub_loader,
        )
        self.assertIsNotNone(ranker)
        # Only HITS snapshot is wired
        self.assertIn(SIGNAL_HITS_AUTHORITY, ranker.snapshots)
        self.assertNotIn(SIGNAL_PPR, ranker.snapshots)

    def test_loader_exception_skips_signal_without_failing(self) -> None:
        def stub_loader(signal: str) -> GraphSignalSnapshot | None:
            if signal == SIGNAL_PPR:
                raise RuntimeError("simulated load failure")
            return _snapshot(signal, {"1:thread": 0.9})

        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10, SIGNAL_PPR: 0.05},
            load_snapshot_fn=stub_loader,
        )
        self.assertIsNotNone(ranker)
        # HITS still loaded; PPR silently skipped
        self.assertIn(SIGNAL_HITS_AUTHORITY, ranker.snapshots)
        self.assertNotIn(SIGNAL_PPR, ranker.snapshots)


# ── Integration with score_destination_matches (the proof point) ───


class GraphSignalRankerIntegrationTests(TestCase):
    """End-to-end: persist a snapshot, run the ranker, prove score_final lifts.

    This is what closes the W3c read-API loop: before this slice the
    HITS / PPR / TrustRank snapshots persisted by the W1 jobs were
    silently ignored by the live ranker.
    """

    def setUp(self) -> None:
        self.weights = {
            "w_semantic": 1.0,
            "w_keyword": 0.0,
            "w_node": 0.0,
            "w_quality": 0.0,
        }
        self.march_2026_pagerank_bounds = (0.0, 1.0)
        self.destination = _content_record(content_id=10)
        self.host = _content_record(content_id=20)
        self.records = {
            self.destination.key: self.destination,
            self.host.key: self.host,
        }
        self.sentence_records = {
            20: SentenceRecord(
                sentence_id=20,
                content_id=20,
                content_type="thread",
                text="Useful sentence about a topic",
                char_count=80,
                tokens=frozenset({"topic"}),
            )
        }
        self.matches = [SentenceSemanticMatch(20, "thread", 20, 0.8)]

    def _score(self, *, graph_signal_ranker: GraphSignalRanker | None = None) -> float:
        scored = score_destination_matches(
            self.destination,
            self.matches,
            content_records=self.records,
            sentence_records=self.sentence_records,
            existing_links=set(),
            weights=self.weights,
            march_2026_pagerank_bounds=self.march_2026_pagerank_bounds,
            graph_signal_ranker=graph_signal_ranker,
        )
        self.assertEqual(len(scored), 1)
        return scored[0].score_final

    def test_no_ranker_means_no_contribution(self) -> None:
        # Default kwarg = None → behaviour unchanged from pre-W3c.
        baseline = self._score(graph_signal_ranker=None)
        # Sanity — at least non-zero given semantic 0.8 with weight 1.0.
        self.assertGreater(baseline, 0.0)

    def test_high_authority_destination_gets_positive_lift(self) -> None:
        # Persist HITS authority of 0.9 for the destination.
        persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY,
            scores={self.destination.key: 0.9},
        )
        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
        )
        self.assertIsNotNone(ranker)

        baseline = self._score(graph_signal_ranker=None)
        boosted = self._score(graph_signal_ranker=ranker)

        # Expected lift: 0.10 * (0.9 - 0.5) = 0.04
        self.assertAlmostEqual(boosted - baseline, 0.04, places=4)

    def test_low_authority_destination_gets_negative_pull(self) -> None:
        # Persist HITS authority of 0.1 for the destination — well below
        # the 0.5 neutral baseline → contribution should be negative.
        persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY,
            scores={self.destination.key: 0.1},
        )
        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
        )
        self.assertIsNotNone(ranker)

        baseline = self._score(graph_signal_ranker=None)
        suppressed = self._score(graph_signal_ranker=ranker)

        # Expected pull: 0.10 * (0.1 - 0.5) = -0.04
        self.assertAlmostEqual(suppressed - baseline, -0.04, places=4)

    def test_cold_start_destination_unchanged(self) -> None:
        # No snapshot persisted → build_graph_signal_ranker returns None
        # (no signal has both weight and snapshot) → no contribution.
        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
        )
        self.assertIsNone(ranker)

        # Baseline still works; passing None means the ranker is a no-op.
        baseline = self._score(graph_signal_ranker=None)
        self.assertGreater(baseline, 0.0)

    def test_destination_outside_top_n_falls_to_neutral(self) -> None:
        # Persist authority for a different node; ours is outside the
        # top-N → snap.lookup returns NEUTRAL_SCORE (0.5) → contribution 0.
        persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY,
            scores={(99, "thread"): 0.95},
        )
        ranker = build_graph_signal_ranker(
            weights={SIGNAL_HITS_AUTHORITY: 0.10},
        )
        self.assertIsNotNone(ranker)

        baseline = self._score(graph_signal_ranker=None)
        boosted = self._score(graph_signal_ranker=ranker)

        # Our destination is not in the snapshot → contribution = 0
        self.assertAlmostEqual(boosted, baseline, places=4)

    def test_combined_signals_sum_correctly(self) -> None:
        # Persist all three signals for our destination.
        persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY,
            scores={self.destination.key: 0.9},  # +0.10 * 0.4 = 0.04
        )
        persist_top_n(
            signal=SIGNAL_PPR,
            scores={self.destination.key: 0.7},  # +0.05 * 0.2 = 0.01
        )
        persist_top_n(
            signal=SIGNAL_TRUSTRANK,
            scores={self.destination.key: 0.6},  # +0.03 * 0.1 = 0.003
        )
        ranker = build_graph_signal_ranker(
            weights={
                SIGNAL_HITS_AUTHORITY: 0.10,
                SIGNAL_PPR: 0.05,
                SIGNAL_TRUSTRANK: 0.03,
            },
        )
        self.assertIsNotNone(ranker)

        baseline = self._score(graph_signal_ranker=None)
        boosted = self._score(graph_signal_ranker=ranker)

        # 0.10*0.4 + 0.05*0.2 + 0.03*0.1 = 0.053
        self.assertAlmostEqual(boosted - baseline, 0.053, places=4)
