"""Tests for the FR-239 standalone MMR rerank helper in slate_diversity.py.

Covers `mmr_rerank_keys` and `_pick_next_mmr_index` — the
key-shape-agnostic variant used at Stage-1 retrieval (where
``ScoredCandidate`` doesn't exist yet). Distinct from the FR-015
final-stage MMR over ``ScoredCandidate`` objects, which has its own
integration coverage via the broader ranker tests.

Source of truth for the expected behaviour: Carbonell & Goldstein
(1998), SIGIR §3 — defines MMR as
  λ · Sim(q, d) − (1−λ) · max_{d'∈S} Sim(d, d').
"""

from __future__ import annotations

import numpy as np
from django.test import SimpleTestCase

from apps.pipeline.services.slate_diversity import (
    STAGE1_MMR_LAMBDA_DEFAULT,
    STAGE1_OVERFETCH_MULTIPLIER_DEFAULT,
    _pick_next_mmr_index,
    mmr_rerank_keys,
)


def _unit(*vals: float) -> np.ndarray:
    """Return an L2-unit vector."""
    v = np.asarray(vals, dtype=np.float32)
    return (v / np.linalg.norm(v)).astype(np.float32)


class MmrRerankKeysTests(SimpleTestCase):
    """``mmr_rerank_keys`` selects k diverse picks per Carbonell 1998 §3."""

    def test_empty_input_returns_empty(self):
        # Edge case: zero candidates short-circuits before any math.
        self.assertEqual(mmr_rerank_keys([], {}, k=5), [])

    def test_returns_input_unchanged_when_k_exceeds_candidates(self):
        # Edge case: less than k candidates → MMR has nothing to compress;
        # returns the input order verbatim (still a fresh list).
        scored = [("a", 0.9), ("b", 0.5)]
        emb = {"a": _unit(1.0, 0.0), "b": _unit(0.0, 1.0)}
        out = mmr_rerank_keys(scored, emb, k=5)
        self.assertEqual(out, scored)
        # Caller may mutate the result without affecting the input.
        self.assertIsNot(out, scored)

    def test_first_pick_is_highest_relevance(self):
        # Carbonell 1998 §3: the first pick is unconditional argmax of
        # relevance — no diversity term yet because S is empty.
        scored = [("a", 0.9), ("b", 0.6), ("c", 0.3)]
        emb = {
            "a": _unit(1.0, 0.0),
            "b": _unit(0.0, 1.0),
            "c": _unit(-1.0, 0.0),
        }
        out = mmr_rerank_keys(scored, emb, k=2)
        self.assertEqual(out[0][0], "a")

    def test_pure_relevance_at_lambda_1_degenerates_to_score_sort(self):
        # λ=1 zeros the diversity term → output is just descending score.
        scored = [("a", 0.9), ("b", 0.6), ("c", 0.3)]
        emb = {k: _unit(1.0, 0.0) for k in ("a", "b", "c")}
        out = mmr_rerank_keys(scored, emb, k=3, lambda_=1.0)
        self.assertEqual([k for k, _ in out], ["a", "b", "c"])

    def test_pure_diversity_at_lambda_0_picks_dissimilar_second(self):
        # λ=0 zeros the relevance term → second pick is the candidate
        # least similar to the first pick. With first=a (along x-axis),
        # the orthogonal "b" should win over the duplicate "a-prime".
        scored = [("a", 0.9), ("a-prime", 0.85), ("b", 0.5)]
        emb = {
            "a": _unit(1.0, 0.0),
            "a-prime": _unit(1.0, 0.01),  # near-duplicate of a
            "b": _unit(0.0, 1.0),         # orthogonal
        }
        out = mmr_rerank_keys(scored, emb, k=2, lambda_=0.0)
        self.assertEqual(out[0][0], "a")
        self.assertEqual(out[1][0], "b")

    def test_default_lambda_is_balanced_carbonell_value(self):
        # The default constant is the Carbonell 1998 / Drosou 2010
        # balanced setting. Lock it in so an accidental edit would be
        # caught.
        self.assertEqual(STAGE1_MMR_LAMBDA_DEFAULT, 0.7)

    def test_default_overfetch_multiplier_is_2x(self):
        # Carbonell 1998 §3: "retrieve at least 2× to give MMR room".
        self.assertEqual(STAGE1_OVERFETCH_MULTIPLIER_DEFAULT, 2)

    def test_balanced_lambda_picks_diverse_second_over_near_duplicate(self):
        # With λ=0.7 and a near-duplicate candidate at score 0.85 vs an
        # orthogonal candidate at score 0.5, the orthogonal one should
        # still win second slot because the duplicate's diversity
        # penalty is huge:
        #   duplicate: 0.7 * 0.85 - 0.3 * 0.9999 ≈ 0.595 - 0.300 = 0.295
        #   orthogon : 0.7 * 0.50 - 0.3 * 0      = 0.350 - 0     = 0.350
        scored = [("a", 0.9), ("a-prime", 0.85), ("b", 0.5)]
        emb = {
            "a": _unit(1.0, 0.0),
            "a-prime": _unit(1.0, 0.01),
            "b": _unit(0.0, 1.0),
        }
        out = mmr_rerank_keys(scored, emb, k=2, lambda_=0.7)
        self.assertEqual([k for k, _ in out], ["a", "b"])

    def test_missing_embedding_treated_as_fully_diverse(self):
        # Adversarial: a candidate without an embedding entry. The
        # contract is "fall back to relevance-only" — max_sim is treated
        # as 0 so the candidate isn't penalised for diversity. This
        # avoids dropping legitimate candidates due to a stale lookup.
        scored = [("a", 0.9), ("missing", 0.85), ("b", 0.3)]
        emb = {
            "a": _unit(1.0, 0.0),
            "b": _unit(1.0, 0.0),
            # "missing" intentionally absent
        }
        out = mmr_rerank_keys(scored, emb, k=2, lambda_=0.7)
        # Second slot: "missing" beats "b" because it has 0 diversity
        # penalty and a much higher relevance.
        self.assertEqual(out[1][0], "missing")

    def test_zero_size_embedding_treated_like_missing(self):
        # Edge case: an empty array (size 0) is the documented sentinel
        # for "no embedding" in the Stage-1 path.
        scored = [("a", 0.9), ("empty", 0.85), ("b", 0.3)]
        emb = {
            "a": _unit(1.0, 0.0),
            "empty": np.zeros(0, dtype=np.float32),
            "b": _unit(1.0, 0.0),
        }
        out = mmr_rerank_keys(scored, emb, k=2, lambda_=0.7)
        self.assertEqual(out[1][0], "empty")

    def test_score_column_preserves_original_relevance_not_mmr(self):
        # Spec contract: the returned score is the original relevance,
        # not the MMR composite. Callers that need the MMR value can
        # recompute it from the input.
        scored = [("a", 0.9), ("b", 0.5)]
        emb = {"a": _unit(1.0, 0.0), "b": _unit(0.0, 1.0)}
        out = mmr_rerank_keys(scored, emb, k=2, lambda_=0.7)
        scores = {k: s for k, s in out}
        self.assertAlmostEqual(scores["a"], 0.9, places=6)
        self.assertAlmostEqual(scores["b"], 0.5, places=6)


class PickNextMmrIndexTests(SimpleTestCase):
    """Inner ``_pick_next_mmr_index`` returns the argmax of the MMR formula."""

    def test_argmax_is_returned(self):
        # With λ=1 the helper degenerates to argmax of relevance.
        candidates = [("a", 0.5), ("b", 0.9), ("c", 0.3)]
        emb = {k: _unit(1.0, 0.0) for k in ("a", "b", "c")}
        idx = _pick_next_mmr_index(
            candidates=candidates,
            selected_embeddings=[],
            embedding_lookup=emb,
            lambda_=1.0,
        )
        self.assertEqual(idx, 1)  # "b" has the highest relevance

    def test_zero_selected_embeddings_yields_max_sim_zero(self):
        # No selected embeddings → max_sim defaults to 0 → MMR
        # degenerates to λ·relevance.
        candidates = [("a", 0.5), ("b", 0.9)]
        emb = {"a": _unit(1.0, 0.0), "b": _unit(0.0, 1.0)}
        idx = _pick_next_mmr_index(
            candidates=candidates,
            selected_embeddings=[],
            embedding_lookup=emb,
            lambda_=0.5,
        )
        self.assertEqual(idx, 1)  # "b" at 0.5*0.9 > "a" at 0.5*0.5

    def test_diversity_penalty_demotes_similar_candidate(self):
        # Selected has unit vector along x. Candidate "a" is also along
        # x (high similarity → penalised). Candidate "b" is orthogonal
        # (zero similarity → not penalised). With λ=0.5 and equal
        # relevance, "b" wins.
        selected_embs = [_unit(1.0, 0.0)]
        candidates = [("a", 0.6), ("b", 0.6)]
        emb = {"a": _unit(1.0, 0.0), "b": _unit(0.0, 1.0)}
        idx = _pick_next_mmr_index(
            candidates=candidates,
            selected_embeddings=selected_embs,
            embedding_lookup=emb,
            lambda_=0.5,
        )
        self.assertEqual(idx, 1)
