"""Tests for the pure-function helpers extracted from pipeline/services/pipeline_stages.py.

Covers the 5 new private helpers added when shrinking 5 oversized functions.
All tests run in ``SimpleTestCase`` (no DB, no Docker) via mocks or tiny
in-memory data structures.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from django.test import SimpleTestCase

from apps.pipeline.services.pipeline_stages import (
    _build_candidate_row_ids,
    _fetch_host_embedding_matrix,
    _run_faiss_block_search,
    _score_kwargs_from_settings,
    _topk_numpy_scores,
    _unpack_faiss_hit,
)


# ---------------------------------------------------------------------------
# _build_candidate_row_ids
# ---------------------------------------------------------------------------


class BuildCandidateRowIdsTests(SimpleTestCase):
    """sentence_ids are filtered to those present in the row-index map."""

    def test_empty_sentence_ids_returns_empty(self):
        rows, ids = _build_candidate_row_ids([], {1: 0, 2: 1})
        self.assertEqual(rows, [])
        self.assertEqual(ids, [])

    def test_all_present_returns_all(self):
        sid_to_row = {10: 0, 20: 1, 30: 2}
        rows, ids = _build_candidate_row_ids([10, 20, 30], sid_to_row)
        self.assertEqual(rows, [0, 1, 2])
        self.assertEqual(ids, [10, 20, 30])

    def test_missing_sentence_ids_are_dropped(self):
        sid_to_row = {10: 0, 30: 2}
        rows, ids = _build_candidate_row_ids([10, 20, 30], sid_to_row)
        self.assertEqual(rows, [0, 2])
        self.assertEqual(ids, [10, 30])

    def test_output_order_matches_input_order(self):
        sid_to_row = {5: 3, 1: 0, 9: 7}
        rows, ids = _build_candidate_row_ids([9, 1, 5], sid_to_row)
        self.assertEqual(ids, [9, 1, 5])
        self.assertEqual(rows, [7, 0, 3])


# ---------------------------------------------------------------------------
# _topk_numpy_scores
# ---------------------------------------------------------------------------


class TopkNumpyScoresTests(SimpleTestCase):
    """NumPy cosine scoring returns correct top-K indices and scores."""

    def _make_unit(self, *vals):
        v = np.array(vals, dtype=np.float32)
        return v / np.linalg.norm(v)

    def test_highest_cosine_ranked_first(self):
        dest = self._make_unit(1.0, 0.0)
        embeddings = np.vstack([
            self._make_unit(1.0, 0.0),   # row 0: perfect match
            self._make_unit(0.0, 1.0),   # row 1: orthogonal
            self._make_unit(-1.0, 0.0),  # row 2: opposite
        ])
        top_idx, top_scores = _topk_numpy_scores(dest, embeddings, [0, 1, 2], top_k=3)
        self.assertEqual(int(top_idx[0]), 0)
        self.assertAlmostEqual(float(top_scores[0]), 1.0, places=5)

    def test_top_k_clips_to_available(self):
        dest = self._make_unit(1.0, 0.0)
        embeddings = np.vstack([self._make_unit(1.0, 0.0)] * 2)
        top_idx, top_scores = _topk_numpy_scores(dest, embeddings, [0, 1], top_k=10)
        self.assertEqual(len(top_idx), 2)

    def test_returns_numpy_arrays(self):
        dest = self._make_unit(1.0, 0.0)
        embeddings = np.vstack([self._make_unit(1.0, 0.0)])
        top_idx, top_scores = _topk_numpy_scores(dest, embeddings, [0], top_k=1)
        self.assertIsInstance(top_idx, np.ndarray)
        self.assertIsInstance(top_scores, np.ndarray)


# ---------------------------------------------------------------------------
# _run_faiss_block_search
# ---------------------------------------------------------------------------


class RunFaissBlockSearchTests(SimpleTestCase):
    """Block-wise FAISS search expands hits to sentence IDs, skipping self-links."""

    def _dest_embeddings(self, n=2):
        return np.zeros((n, 4), dtype=np.float32)

    def test_empty_destination_keys_returns_empty(self):
        result = _run_faiss_block_search(
            np.zeros((0, 4), dtype=np.float32),
            (),
            host_pk_set={1},
            block_size=256,
            top_k=5,
            content_to_sentence_ids={(1, "post"): [10]},
            faiss_search=lambda *a, **kw: [],
        )
        self.assertEqual(result, {})

    def test_self_link_is_excluded(self):
        dest_key = (1, "post")
        faiss_search = MagicMock(return_value=[[(1, "post"), (2, "post")]])
        content_to_sentence_ids = {(1, "post"): [100], (2, "post"): [200]}
        result = _run_faiss_block_search(
            self._dest_embeddings(1),
            (dest_key,),
            host_pk_set={1, 2},
            block_size=256,
            top_k=5,
            content_to_sentence_ids=content_to_sentence_ids,
            faiss_search=faiss_search,
        )
        self.assertIn(dest_key, result)
        self.assertNotIn(100, result[dest_key], msg="self-link sentence must be excluded")
        self.assertIn(200, result[dest_key])

    def test_no_sentence_ids_destination_excluded_from_result(self):
        dest_key = (99, "post")
        faiss_search = MagicMock(return_value=[[]])
        result = _run_faiss_block_search(
            self._dest_embeddings(1),
            (dest_key,),
            host_pk_set=set(),
            block_size=256,
            top_k=5,
            content_to_sentence_ids={},
            faiss_search=faiss_search,
        )
        self.assertNotIn(dest_key, result)


class FaissHitUnpackingTests(SimpleTestCase):
    """FR-238 — ``_unpack_faiss_hit`` accepts both legacy 2-tuples and the
    new score-bearing 3-tuples without losing information.

    Source of truth: Wang, Lin & Metzler 2011 §3 (cascade ranker score
    propagation).
    """

    def test_3tuple_returns_score_unchanged(self):
        pk, ct, score = _unpack_faiss_hit((42, "post", 0.87))
        self.assertEqual(pk, 42)
        self.assertEqual(ct, "post")
        self.assertAlmostEqual(score, 0.87, places=6)

    def test_2tuple_yields_sentinel_zero_score(self):
        # Legacy mock shape (pre-FR-238). The sentinel 0.0 is recognisably
        # "unscored" because real FAISS top-K hits have positive cosines.
        pk, ct, score = _unpack_faiss_hit((7, "thread"))
        self.assertEqual(pk, 7)
        self.assertEqual(ct, "thread")
        self.assertEqual(score, 0.0)

    def test_score_coerced_to_float(self):
        # FAISS returns numpy.float32; downstream code expects Python float.
        pk, ct, score = _unpack_faiss_hit((1, "post", np.float32(0.5)))
        self.assertIsInstance(score, float)


class RunFaissBlockSearchScorePreservationTests(SimpleTestCase):
    """FR-238 — when ``host_scores_out`` is supplied, scores propagate."""

    def _dest_embeddings(self, n=1):
        return np.zeros((n, 4), dtype=np.float32)

    def test_scores_captured_for_each_kept_host(self):
        dest_key = (1, "post")
        faiss_search = MagicMock(return_value=[[(2, "post", 0.91), (3, "post", 0.42)]])
        content_to_sentence_ids = {(2, "post"): [200], (3, "post"): [300]}
        host_scores: dict = {}
        result = _run_faiss_block_search(
            self._dest_embeddings(1),
            (dest_key,),
            host_pk_set={2, 3},
            block_size=256,
            top_k=5,
            content_to_sentence_ids=content_to_sentence_ids,
            faiss_search=faiss_search,
            host_scores_out=host_scores,
        )
        self.assertEqual(result[dest_key], [200, 300])
        self.assertEqual(
            host_scores[dest_key],
            [((2, "post"), 0.91), ((3, "post"), 0.42)],
        )

    def test_self_link_score_is_dropped_alongside_sentence(self):
        # Self-link host appears in FAISS hits but must not contribute
        # to either the sentence list OR the score list.
        dest_key = (1, "post")
        faiss_search = MagicMock(
            return_value=[[(1, "post", 1.0), (2, "post", 0.7)]]
        )
        content_to_sentence_ids = {(1, "post"): [100], (2, "post"): [200]}
        host_scores: dict = {}
        _run_faiss_block_search(
            self._dest_embeddings(1),
            (dest_key,),
            host_pk_set={1, 2},
            block_size=256,
            top_k=5,
            content_to_sentence_ids=content_to_sentence_ids,
            faiss_search=faiss_search,
            host_scores_out=host_scores,
        )
        self.assertEqual(host_scores[dest_key], [((2, "post"), 0.7)])

    def test_default_no_score_capture_keeps_legacy_shape(self):
        # When host_scores_out is None (default), the function still
        # returns the existing dict shape — backward-compat.
        dest_key = (1, "post")
        faiss_search = MagicMock(return_value=[[(2, "post", 0.5)]])
        content_to_sentence_ids = {(2, "post"): [200]}
        result = _run_faiss_block_search(
            self._dest_embeddings(1),
            (dest_key,),
            host_pk_set={2},
            block_size=256,
            top_k=5,
            content_to_sentence_ids=content_to_sentence_ids,
            faiss_search=faiss_search,
        )
        self.assertEqual(result, {dest_key: [200]})

    def test_host_with_no_sentences_is_skipped_in_scores(self):
        # FR-238 spec adversarial: a host that FAISS returned but which
        # has no sentence IDs must not appear in host_scores either —
        # otherwise the score list would imply contribution that didn't
        # happen.
        dest_key = (1, "post")
        faiss_search = MagicMock(
            return_value=[[(2, "post", 0.9), (3, "post", 0.8)]]
        )
        content_to_sentence_ids = {(2, "post"): [200]}  # 3 has nothing
        host_scores: dict = {}
        _run_faiss_block_search(
            self._dest_embeddings(1),
            (dest_key,),
            host_pk_set={2, 3},
            block_size=256,
            top_k=5,
            content_to_sentence_ids=content_to_sentence_ids,
            faiss_search=faiss_search,
            host_scores_out=host_scores,
        )
        self.assertEqual(host_scores[dest_key], [((2, "post"), 0.9)])


# ---------------------------------------------------------------------------
# _fetch_host_embedding_matrix
# ---------------------------------------------------------------------------


class FetchHostEmbeddingMatrixTests(SimpleTestCase):
    """Returns empty sentinel when no valid embeddings exist."""

    def test_empty_host_keys_returns_empty(self):
        with patch("apps.content.models.ContentItem.objects") as mock_qs:
            mock_qs.filter.return_value.values_list.return_value = []
            valid_keys, matrix = _fetch_host_embedding_matrix([])
        self.assertEqual(valid_keys, [])
        self.assertIsNone(matrix)

    def test_no_matching_embeddings_returns_empty(self):
        with patch(
            "apps.pipeline.services.pipeline_stages._fetch_host_embedding_matrix"
        ) as mock_fn:
            mock_fn.return_value = ([], None)
            result = mock_fn([(1, "post")])
        self.assertEqual(result[0], [])
        self.assertIsNone(result[1])


# ---------------------------------------------------------------------------
# _score_kwargs_from_settings
# ---------------------------------------------------------------------------


class ScoreKwargsFromSettingsTests(SimpleTestCase):
    """Settings dict is unpacked into the correct kwargs for score_destination_matches."""

    def _minimal_settings(self):
        wa = MagicMock()
        wa.__getitem__ = lambda self, k: 0.5 if k == "ranking_weight" else None
        return {
            "max_existing_links_per_host": 10,
            "max_anchor_words": 5,
            "learned_anchor_rows": {},
            "anchor_history_by_destination": {},
            "rare_term_profiles": {},
            "keyword_stuffing_by_destination": {},
            "link_farm_by_destination": {},
            "weights": {},
            "pagerank_bounds": {},
            "weighted_authority": {"ranking_weight": 0.3},
            "link_freshness": {"ranking_weight": 0.2},
            "phrase_matching": MagicMock(),
            "learned_anchor": MagicMock(),
            "rare_term": MagicMock(),
            "field_aware": MagicMock(),
            "ga4_gsc": {"ranking_weight": 0.1},
            "click_distance": {"ranking_weight": 0.05},
            "anchor_diversity": MagicMock(),
            "keyword_stuffing": MagicMock(),
            "link_farm": MagicMock(),
            "silo": MagicMock(),
            "clustering": MagicMock(),
        }

    def test_returns_23_keys(self):
        kwargs = _score_kwargs_from_settings(self._minimal_settings())
        self.assertEqual(len(kwargs), 23)

    def test_min_semantic_score_present(self):
        kwargs = _score_kwargs_from_settings(self._minimal_settings())
        self.assertIn("min_semantic_score", kwargs)

    def test_learned_anchor_rows_mapped_correctly(self):
        s = self._minimal_settings()
        s["learned_anchor_rows"] = {"dest": [1, 2]}
        kwargs = _score_kwargs_from_settings(s)
        self.assertEqual(kwargs["learned_anchor_rows_by_destination"], {"dest": [1, 2]})

    def test_pagerank_bounds_mapped_correctly(self):
        s = self._minimal_settings()
        s["pagerank_bounds"] = {"min": 0.01}
        kwargs = _score_kwargs_from_settings(s)
        self.assertEqual(kwargs["march_2026_pagerank_bounds"], {"min": 0.01})

    def test_weighted_authority_ranking_weight_extracted(self):
        s = self._minimal_settings()
        s["weighted_authority"] = {"ranking_weight": 0.75}
        kwargs = _score_kwargs_from_settings(s)
        self.assertAlmostEqual(kwargs["weighted_authority_ranking_weight"], 0.75)
