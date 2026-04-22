"""Tests for Cormack-Clarke-Büttcher RRF (PR-L #31)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.pipeline.services.reciprocal_rank_fusion import (
    DEFAULT_RRF_K,
    FusedItem,
    fuse,
    fuse_to_ids,
    iter_fused,
    reciprocal_rank_score,
)


class FuseBasicsTests(SimpleTestCase):
    def test_single_ranker_preserves_order(self) -> None:
        ranked = fuse_to_ids({"bm25": ["a", "b", "c"]})
        self.assertEqual(ranked, ["a", "b", "c"])

    def test_doc_in_multiple_lists_wins(self) -> None:
        # "a" is in both lists near the top; should fuse above "b" and "c".
        fused = fuse_to_ids(
            {
                "bm25": ["a", "b", "c"],
                "cosine": ["a", "c", "b"],
            }
        )
        self.assertEqual(fused[0], "a")

    def test_uneven_list_lengths_ok(self) -> None:
        fused = fuse_to_ids(
            {
                "bm25": ["a", "b", "c", "d"],
                "cosine": ["b"],
            }
        )
        # "b" appears top in cosine and 2nd in bm25 → strong boost
        # over "a" which only appears in bm25.
        self.assertIn(fused.index("b"), (0, 1))

    def test_disjoint_lists_preserve_individual_ranks(self) -> None:
        fused = fuse_to_ids(
            {
                "bm25": ["a", "b"],
                "cosine": ["c", "d"],
            }
        )
        self.assertEqual(set(fused), {"a", "b", "c", "d"})
        # Each doc's score is 1/(k+rank); ranks equal → scores equal,
        # tie-broken deterministically (ranker name alphabetical).
        self.assertEqual(fused[0], "a")
        self.assertEqual(fused[1], "c")  # "cosine" alphabetically after "bm25"


class FuseDetailTests(SimpleTestCase):
    def test_contributions_sum_to_score(self) -> None:
        items = fuse(
            {
                "bm25": ["a", "b"],
                "cosine": ["b", "a"],
            }
        )
        for item in items:
            self.assertAlmostEqual(sum(item.contributions.values()), item.score)

    def test_k_changes_score_magnitude(self) -> None:
        high_k = fuse({"r": ["a"]}, k=1000)
        low_k = fuse({"r": ["a"]}, k=1)
        self.assertLess(high_k[0].score, low_k[0].score)

    def test_invalid_k_rejected(self) -> None:
        with self.assertRaises(ValueError):
            fuse({"r": ["a"]}, k=0)
        with self.assertRaises(ValueError):
            fuse({"r": ["a"]}, k=-5)


class FuseDuplicatesAndTopNTests(SimpleTestCase):
    def test_duplicate_doc_in_one_list_only_counted_once(self) -> None:
        items = fuse({"r": ["a", "a", "b"]})
        ranker_contribs = [item.contributions["r"] for item in items]
        # "a" should get rank 1 contribution only, "b" gets rank 3.
        a_item = next(item for item in items if item.doc_id == "a")
        b_item = next(item for item in items if item.doc_id == "b")
        self.assertAlmostEqual(a_item.score, 1.0 / (DEFAULT_RRF_K + 1))
        self.assertAlmostEqual(b_item.score, 1.0 / (DEFAULT_RRF_K + 3))
        self.assertEqual(len(ranker_contribs), 2)

    def test_top_n_truncates(self) -> None:
        fused = fuse_to_ids({"r": ["a", "b", "c", "d"]}, top_n=2)
        self.assertEqual(fused, ["a", "b"])

    def test_empty_rankings_returns_empty(self) -> None:
        self.assertEqual(fuse_to_ids({}), [])


class ReciprocalRankScoreTests(SimpleTestCase):
    def test_position_one_highest(self) -> None:
        s1 = reciprocal_rank_score(position=1)
        s10 = reciprocal_rank_score(position=10)
        self.assertGreater(s1, s10)

    def test_zero_position_rejected(self) -> None:
        with self.assertRaises(ValueError):
            reciprocal_rank_score(position=0)

    def test_default_k_matches_paper(self) -> None:
        self.assertEqual(DEFAULT_RRF_K, 60)


class IterFusedTests(SimpleTestCase):
    def test_tuple_iterable_equivalent_to_dict(self) -> None:
        from_mapping = fuse({"bm25": ["a"], "cosine": ["b"]})
        from_iter = iter_fused([("bm25", ["a"]), ("cosine", ["b"])])
        self.assertEqual(
            [i.doc_id for i in from_mapping],
            [i.doc_id for i in from_iter],
        )


class FusedItemDataclassTests(SimpleTestCase):
    def test_frozen(self) -> None:
        item = FusedItem(doc_id="x", score=0.5, contributions={"r": 0.5})
        with self.assertRaises(Exception):
            item.score = 1.0  # type: ignore[misc]
