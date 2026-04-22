"""Tests for Zhai-Lafferty QL with Dirichlet smoothing (PR-K #28)."""

from __future__ import annotations

import math

from django.test import SimpleTestCase

from apps.pipeline.services.query_likelihood import (
    DEFAULT_DIRICHLET_MU,
    CollectionStatistics,
    collection_probability,
    dirichlet_smoothed_probability,
    score_document,
    tokenised_to_counter,
)


def _stats() -> CollectionStatistics:
    return CollectionStatistics(
        collection_term_counts={
            "linker": 100,
            "graph": 200,
            "engine": 150,
            "noise": 50,
        },
        collection_length=1000,
    )


class CollectionProbabilityTests(SimpleTestCase):
    def test_known_term_returns_ratio(self) -> None:
        self.assertAlmostEqual(collection_probability("linker", _stats()), 0.1)

    def test_unseen_term_floored_positive(self) -> None:
        p = collection_probability("missing", _stats())
        self.assertGreater(p, 0.0)
        self.assertLess(p, 1e-6)


class DirichletSmoothedProbabilityTests(SimpleTestCase):
    def test_unseen_in_doc_still_nonzero(self) -> None:
        p = dirichlet_smoothed_probability(
            term="linker",
            document_term_counts={"graph": 2},
            document_length=10,
            statistics=_stats(),
            mu=100.0,
        )
        # Smoothed LM never drops to zero — collection prob carries through.
        self.assertGreater(p, 0.0)

    def test_known_term_pulled_toward_collection_by_mu(self) -> None:
        stats = _stats()
        low_mu = dirichlet_smoothed_probability(
            term="linker",
            document_term_counts={"linker": 5, "noise": 5},
            document_length=10,
            statistics=stats,
            mu=0.0,
        )
        high_mu = dirichlet_smoothed_probability(
            term="linker",
            document_term_counts={"linker": 5, "noise": 5},
            document_length=10,
            statistics=stats,
            mu=10000.0,
        )
        # With μ → ∞, the smoothed prob → collection prob (0.1).
        # With μ = 0, it equals raw doc prob (0.5).
        self.assertAlmostEqual(low_mu, 0.5)
        self.assertLess(high_mu, low_mu)
        self.assertAlmostEqual(high_mu, 0.1, places=1)

    def test_negative_mu_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dirichlet_smoothed_probability(
                term="x",
                document_term_counts={},
                document_length=1,
                statistics=_stats(),
                mu=-1.0,
            )


class ScoreDocumentTests(SimpleTestCase):
    def test_empty_query_scores_zero(self) -> None:
        result = score_document(
            query_term_counts={},
            document_term_counts={"linker": 3},
            document_length=5,
            statistics=_stats(),
        )
        self.assertEqual(result.log_score, 0.0)
        self.assertEqual(result.per_term, {})

    def test_doc_with_more_query_terms_scores_higher(self) -> None:
        stats = _stats()
        rich = score_document(
            query_term_counts={"linker": 1, "graph": 1},
            document_term_counts={"linker": 4, "graph": 4, "engine": 2},
            document_length=10,
            statistics=stats,
        )
        sparse = score_document(
            query_term_counts={"linker": 1, "graph": 1},
            document_term_counts={"engine": 10},
            document_length=10,
            statistics=stats,
        )
        self.assertGreater(rich.log_score, sparse.log_score)

    def test_per_term_sum_equals_log_score(self) -> None:
        result = score_document(
            query_term_counts={"linker": 1, "graph": 2},
            document_term_counts={"linker": 3, "graph": 1, "noise": 1},
            document_length=5,
            statistics=_stats(),
        )
        self.assertAlmostEqual(result.log_score, sum(result.per_term.values()))

    def test_score_is_non_positive(self) -> None:
        # log of a probability ≤ 1.0 → non-positive contribution.
        result = score_document(
            query_term_counts={"linker": 1},
            document_term_counts={"linker": 1},
            document_length=1,
            statistics=_stats(),
        )
        self.assertLessEqual(result.log_score, 0.0)

    def test_default_mu_is_sane(self) -> None:
        # Smoke test — default mu matches the range cited in Zhai-Lafferty.
        self.assertGreater(DEFAULT_DIRICHLET_MU, 500)
        self.assertLess(DEFAULT_DIRICHLET_MU, 3000)


class TokenisedToCounterTests(SimpleTestCase):
    def test_counts_tokens(self) -> None:
        counter = tokenised_to_counter(["a", "b", "a"])
        self.assertEqual(counter["a"], 2)
        self.assertEqual(counter["b"], 1)


class RejectsInvalidCollectionTests(SimpleTestCase):
    def test_zero_collection_length_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CollectionStatistics(
                collection_term_counts={"x": 1},
                collection_length=0,
            )

    def test_collection_probability_matches_formula(self) -> None:
        # P(linker | C) = 100 / 1000 = 0.1
        # log P = log(0.1) ≈ -2.302
        p = collection_probability("linker", _stats())
        self.assertAlmostEqual(math.log(p), math.log(0.1))
