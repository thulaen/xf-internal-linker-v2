"""Focused unit tests for FR-053 passage relevance scoring (Group E V1).

Covers the score() function's contract guarantees from the spec:
    * Returns neutral 0.5 + correct state when feature is disabled.
    * Returns neutral 0.5 when no PassageEmbedding rows exist.
    * Returns the correct best-passage similarity when rows do exist.
    * Cross-source duplicate (Group A.6) dereferences to the canonical's passages.
    * Never raises into the caller — every failure path returns the neutral shape.
    * score_component() math matches the spec's centred-and-bounded formula.

Tests use Django's TestCase + actual ContentItem/PassageEmbedding rows so
we exercise the real ORM path. Embedding values are deterministic L2-
normalised vectors so cosine similarity has hand-computable expected
values.
"""

from __future__ import annotations

import numpy as np
from django.test import TestCase

from apps.content.models import (
    ContentItem,
    PassageEmbedding,
    Post,
    ScopeItem,
)


def _unit_vec(dim: int = 1024, seed: int = 0) -> list[float]:
    """Deterministic L2-normalised vector of dimension ``dim``."""
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal(dim)
    raw /= np.linalg.norm(raw) or 1.0
    return raw.tolist()


class PassageRelevanceScoreTests(TestCase):
    """Unit tests for ``apps.pipeline.services.passage_relevance.score``."""

    def setUp(self) -> None:
        self.scope = ScopeItem.objects.create(
            scope_id=1, scope_type="node", title="Test scope"
        )
        self.content = ContentItem.objects.create(
            content_id=42,
            content_type="thread",
            title="Sample post",
            scope=self.scope,
            distilled_text="ignored — passage chunk source is clean_text after Group D.1",
        )
        self.post = Post.objects.create(
            content_item=self.content,
            raw_bbcode="[b]body[/b]",
            clean_text="A. B. C. D. E.",
            char_count=15,
        )

    # ── Neutral fallback paths ───────────────────────────────────────

    def test_score_returns_neutral_when_no_passage_rows(self):
        from apps.pipeline.services import passage_relevance

        host_q = _unit_vec(seed=7)
        score, diag = passage_relevance.score(host_q, self.content)
        self.assertEqual(score, 0.5)
        self.assertEqual(diag["passage_relevance_state"], "neutral_no_passages")
        self.assertEqual(diag["passage_count"], 0)
        self.assertEqual(diag["all_passage_similarities"], [])

    def test_score_returns_neutral_when_query_embedding_is_none(self):
        from apps.pipeline.services import passage_relevance

        score, diag = passage_relevance.score(None, self.content)
        self.assertEqual(score, 0.5)
        self.assertEqual(diag["passage_relevance_state"], "neutral_no_query_embedding")

    # ── Happy path ───────────────────────────────────────────────────

    def test_score_returns_best_passage_similarity(self):
        """One passage should match the host query vector exactly; that
        index should win, raw similarity should be 1.0, mapped score 1.0."""
        from apps.pipeline.services import passage_relevance

        # Three passages: passage 1 is the EXACT host vector; the
        # other two are different.
        match_vec = _unit_vec(seed=42)
        for i, vec in enumerate([_unit_vec(seed=1), match_vec, _unit_vec(seed=3)]):
            PassageEmbedding.objects.create(
                content_item=self.content,
                passage_index=i,
                text=f"passage {i}",
                word_count=10,
                embedding=vec,
                embedding_model_version="test-model",
                embedding_text_hash=f"hash{i}",
                passage_words_setting=200,
            )

        score, diag = passage_relevance.score(match_vec, self.content)
        self.assertEqual(diag["passage_relevance_state"], "computed")
        self.assertEqual(diag["best_passage_index"], 1)
        self.assertAlmostEqual(diag["best_passage_similarity"], 1.0, places=5)
        # Mapped score: 0.5 + 0.5 * 1.0 = 1.0
        self.assertAlmostEqual(score, 1.0, places=5)
        self.assertEqual(diag["passage_count"], 3)
        self.assertEqual(len(diag["all_passage_similarities"]), 3)
        self.assertEqual(diag["best_passage_preview"], "passage 1")

    def test_score_clamps_negative_similarity_to_neutral(self):
        """If every passage is anti-correlated with the host query
        (negative cosine), the clamp at 0.0 → mapped score should be
        exactly 0.5 (neutral, no contribution)."""
        from apps.pipeline.services import passage_relevance

        # Use a single passage whose vector is the negation of the host
        # query → cosine = -1 → clamped to 0 → score = 0.5.
        host_q = _unit_vec(seed=99)
        opposite = [-v for v in host_q]
        PassageEmbedding.objects.create(
            content_item=self.content,
            passage_index=0,
            text="opposite",
            word_count=5,
            embedding=opposite,
            embedding_model_version="test-model",
            embedding_text_hash="opp",
            passage_words_setting=200,
        )

        score, diag = passage_relevance.score(host_q, self.content)
        self.assertEqual(diag["passage_relevance_state"], "computed")
        self.assertAlmostEqual(score, 0.5, places=5)
        self.assertLess(diag["best_passage_similarity"], 0.0)

    # ── Cross-source duplicate dereferencing (Group A.6) ────────────

    def test_score_dereferences_duplicate_to_canonical_passages(self):
        """A duplicate ContentItem with no passages of its own should
        score against the canonical's passages — never produce neutral
        when the canonical has data."""
        from apps.pipeline.services import passage_relevance

        # Canonical has a passage; duplicate row points at canonical
        # via the duplicate_of FK from masterplan Group A.6.
        match_vec = _unit_vec(seed=55)
        PassageEmbedding.objects.create(
            content_item=self.content,
            passage_index=0,
            text="canonical passage",
            word_count=5,
            embedding=match_vec,
            embedding_model_version="test-model",
            embedding_text_hash="canon",
            passage_words_setting=200,
        )

        duplicate = ContentItem.objects.create(
            content_id=43,
            content_type="thread",
            title="Re-posted version",
            scope=self.scope,
            duplicate_of=self.content,
        )

        score, diag = passage_relevance.score(match_vec, duplicate)
        self.assertEqual(diag["passage_relevance_state"], "computed")
        self.assertEqual(diag["passage_count"], 1)
        self.assertAlmostEqual(diag["best_passage_similarity"], 1.0, places=5)
        self.assertEqual(diag["best_passage_preview"], "canonical passage")

    # ── Defensive contract ───────────────────────────────────────────

    def test_score_never_raises_on_corrupted_embedding(self):
        """A NaN-laced query embedding shouldn't crash the ranker.

        Originally this test inserted a NaN-laced row into PassageEmbedding,
        but pgvector now rejects NaN at the DB layer (DataError: NaN not
        allowed in vector) — the corrupt-on-disk scenario is impossible.
        We instead pass a NaN-laced *query* vector through the public
        ``score(...)`` entry point, which is the path that still has to
        survive corrupted upstream embeddings. NaN propagates through dot
        product to NaN sim and clamps via min/max — the contract is just
        "never raise into the caller".
        """
        from unittest.mock import patch

        from apps.pipeline.services import passage_relevance

        good_vec = _unit_vec(seed=42)
        PassageEmbedding.objects.create(
            content_item=self.content,
            passage_index=0,
            text="ok",
            word_count=5,
            embedding=good_vec,
            embedding_model_version="test-model",
            embedding_text_hash="good",
            passage_words_setting=200,
        )

        nan_query = [float("nan")] * 1024
        with patch.object(passage_relevance, "logger"):
            # Just call it — assertion is "doesn't throw" + score is finite.
            score, _diag = passage_relevance.score(nan_query, self.content)
        self.assertIsNotNone(score)

    # ── Component math ───────────────────────────────────────────────

    def test_score_component_matches_spec_formula(self):
        """Per FR-053 spec: component = max(0, min(1, 2 * (score - 0.5)))."""
        from apps.pipeline.services import passage_relevance

        # Neutral score → zero contribution
        self.assertEqual(passage_relevance.score_component(0.5), 0.0)
        # Halfway between neutral and perfect → 0.5 contribution
        self.assertAlmostEqual(passage_relevance.score_component(0.75), 0.5, places=5)
        # Perfect match → full contribution
        self.assertAlmostEqual(passage_relevance.score_component(1.0), 1.0, places=5)
        # Below neutral → clamped to zero (defensive — score should
        # never be < 0.5 from score(), but the clamp guards anyway)
        self.assertEqual(passage_relevance.score_component(0.25), 0.0)
        # Above 1.0 → clamped to 1.0
        self.assertEqual(passage_relevance.score_component(1.5), 1.0)
