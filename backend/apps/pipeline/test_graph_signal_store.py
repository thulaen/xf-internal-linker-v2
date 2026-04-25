"""Tests for W3c — graph_signal_store (picks #29, #36, #30 wiring)."""

from __future__ import annotations

from django.test import TestCase

from apps.pipeline.services.graph_signal_store import (
    DEFAULT_TOP_N,
    KEY_TEMPLATE,
    NEUTRAL_SCORE,
    SIGNAL_HITS_AUTHORITY,
    SIGNAL_PPR,
    SIGNAL_TRUSTRANK,
    GraphSignalSnapshot,
    load_snapshot,
    persist_top_n,
    score_for,
)


class LoadSnapshotTests(TestCase):
    def test_cold_start_returns_none(self) -> None:
        self.assertIsNone(load_snapshot(SIGNAL_HITS_AUTHORITY))

    def test_returns_snapshot_after_persist(self) -> None:
        persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY,
            scores={(1, "thread"): 0.9, (2, "thread"): 0.5},
        )
        snap = load_snapshot(SIGNAL_HITS_AUTHORITY)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.signal, SIGNAL_HITS_AUTHORITY)
        self.assertAlmostEqual(snap.lookup((1, "thread")), 0.9)


class ScoreForTests(TestCase):
    def test_cold_start_returns_neutral(self) -> None:
        self.assertEqual(
            score_for(SIGNAL_PPR, (1, "thread")), NEUTRAL_SCORE
        )

    def test_known_node_returns_persisted_value(self) -> None:
        persist_top_n(
            signal=SIGNAL_PPR,
            scores={(7, "resource"): 0.42},
        )
        self.assertAlmostEqual(score_for(SIGNAL_PPR, (7, "resource")), 0.42)

    def test_unknown_node_returns_neutral(self) -> None:
        persist_top_n(
            signal=SIGNAL_PPR,
            scores={(7, "resource"): 0.42},
        )
        self.assertEqual(
            score_for(SIGNAL_PPR, (999, "thread")), NEUTRAL_SCORE
        )


class PersistTopNTests(TestCase):
    def test_caps_at_top_n(self) -> None:
        # Build a 100-node table with descending scores; persist_top_n=10
        # should keep only the highest 10.
        scores = {(i, "thread"): float(100 - i) for i in range(100)}
        written = persist_top_n(
            signal=SIGNAL_TRUSTRANK, scores=scores, top_n=10
        )
        self.assertEqual(written, 10)
        snap = load_snapshot(SIGNAL_TRUSTRANK)
        self.assertEqual(len(snap.scores), 10)
        # Top-scoring nodes should have been preserved.
        self.assertAlmostEqual(snap.lookup((0, "thread")), 100.0)
        self.assertAlmostEqual(snap.lookup((9, "thread")), 91.0)
        # Lower-scoring nodes drop to neutral.
        self.assertEqual(
            snap.lookup((50, "thread")), NEUTRAL_SCORE
        )

    def test_empty_input_clears_snapshot(self) -> None:
        # Seed with data, then persist empty — old data should be gone.
        persist_top_n(
            signal=SIGNAL_HITS_AUTHORITY,
            scores={(1, "thread"): 0.9},
        )
        self.assertGreater(score_for(SIGNAL_HITS_AUTHORITY, (1, "thread")), NEUTRAL_SCORE)
        persist_top_n(signal=SIGNAL_HITS_AUTHORITY, scores={})
        self.assertEqual(
            score_for(SIGNAL_HITS_AUTHORITY, (1, "thread")), NEUTRAL_SCORE
        )

    def test_full_node_count_recorded(self) -> None:
        scores = {(i, "thread"): float(100 - i) for i in range(50)}
        persist_top_n(signal=SIGNAL_TRUSTRANK, scores=scores, top_n=20)
        snap = load_snapshot(SIGNAL_TRUSTRANK)
        self.assertEqual(snap.full_node_count, 50)
        self.assertEqual(len(snap.scores), 20)

    def test_int_keys_round_trip(self) -> None:
        # Legacy single-pk keys (no content_type) should also work.
        persist_top_n(signal=SIGNAL_PPR, scores={42: 0.7, 99: 0.3})
        self.assertAlmostEqual(score_for(SIGNAL_PPR, 42), 0.7)
        self.assertAlmostEqual(score_for(SIGNAL_PPR, 99), 0.3)


class GraphSignalSnapshotTests(TestCase):
    def test_lookup_translates_tuple_key(self) -> None:
        snap = GraphSignalSnapshot(
            signal="x",
            scores={"5:thread": 0.85},
            fitted_at=None,
            full_node_count=1,
        )
        self.assertAlmostEqual(snap.lookup((5, "thread")), 0.85)

    def test_lookup_returns_neutral_on_miss(self) -> None:
        snap = GraphSignalSnapshot(
            signal="x", scores={}, fitted_at=None, full_node_count=0
        )
        self.assertEqual(snap.lookup((1, "thread")), NEUTRAL_SCORE)
