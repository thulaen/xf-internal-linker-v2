"""Tests for the Rocchio / Lavrenko-Croft BoW query expander (PR-K #27)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.pipeline.services.query_expansion_bow import (
    DEFAULT_ALPHA,
    DEFAULT_BETA,
    ExpandedQuery,
    ExpansionTerm,
    build_expanded_query,
    expand,
    rank_expansion_terms,
)


def _docs() -> list[dict[str, int]]:
    """Three pseudo-relevant docs about `linker` with various extras."""
    return [
        {"linker": 3, "engine": 2, "graph": 1, "recall": 1, "spurious": 1},
        {"linker": 2, "engine": 1, "graph": 2, "precision": 1},
        {"linker": 4, "engine": 3, "graph": 2, "freshness": 1},
    ]


class RankExpansionTermsTests(SimpleTestCase):
    def test_drops_query_terms_and_stopwords(self) -> None:
        terms = rank_expansion_terms(
            _docs(),
            query_terms={"linker"},
            stopwords=frozenset({"spurious"}),
            min_document_frequency=1,
        )
        got = {t.term for t in terms}
        self.assertNotIn("linker", got)
        self.assertNotIn("spurious", got)

    def test_respects_min_document_frequency(self) -> None:
        terms = rank_expansion_terms(
            _docs(),
            query_terms={"linker"},
            min_document_frequency=3,
        )
        # Only terms that appear in all 3 docs survive.
        surviving = {t.term for t in terms}
        self.assertEqual(surviving, {"engine", "graph"})

    def test_ranked_descending_by_score(self) -> None:
        terms = rank_expansion_terms(
            _docs(),
            query_terms={"linker"},
            top_terms=5,
            min_document_frequency=1,
        )
        scores = [t.score for t in terms]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_empty_corpus_returns_empty_list(self) -> None:
        terms = rank_expansion_terms([], query_terms={"anything"})
        self.assertEqual(terms, [])

    def test_top_terms_caps_output(self) -> None:
        terms = rank_expansion_terms(
            _docs(),
            query_terms={"linker"},
            top_terms=1,
            min_document_frequency=1,
        )
        self.assertEqual(len(terms), 1)


class BuildExpandedQueryTests(SimpleTestCase):
    def test_original_query_weighted_by_alpha(self) -> None:
        expanded = build_expanded_query(
            {"linker": 1.0, "graph": 0.5},
            expansion_terms=[],
            alpha=2.0,
            beta=0.0,
        )
        self.assertAlmostEqual(expanded.weights["linker"], 2.0)
        self.assertAlmostEqual(expanded.weights["graph"], 1.0)

    def test_expansion_terms_weighted_by_beta(self) -> None:
        expanded = build_expanded_query(
            {},
            expansion_terms=[ExpansionTerm("engine", score=0.8, document_frequency=3)],
            alpha=0.0,
            beta=0.5,
        )
        self.assertAlmostEqual(expanded.weights["engine"], 0.4)

    def test_shared_term_sums_alpha_and_beta_contributions(self) -> None:
        expanded = build_expanded_query(
            {"engine": 1.0},
            expansion_terms=[ExpansionTerm("engine", score=0.4, document_frequency=3)],
            alpha=1.0,
            beta=0.5,
        )
        # 1.0 * 1.0 + 0.5 * 0.4 = 1.2
        self.assertAlmostEqual(expanded.weights["engine"], 1.2)

    def test_negative_weights_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_expanded_query({"x": 1.0}, expansion_terms=[], alpha=-0.1)
        with self.assertRaises(ValueError):
            build_expanded_query({"x": 1.0}, expansion_terms=[], beta=-0.1)

    def test_non_positive_original_weights_dropped(self) -> None:
        expanded = build_expanded_query(
            {"linker": 1.0, "ghost": 0.0},
            expansion_terms=[],
        )
        self.assertNotIn("ghost", expanded.weights)
        self.assertIn("linker", expanded.weights)


class ExpandConvenienceTests(SimpleTestCase):
    def test_roundtrip_defaults_produce_expanded_bag(self) -> None:
        result = expand(
            original_query_weights={"linker": 1.0},
            pseudo_relevant_docs=_docs(),
            top_terms=3,
            min_document_frequency=2,
        )
        self.assertIsInstance(result, ExpandedQuery)
        self.assertIn("linker", result.weights)
        # Common co-occurring terms "engine" and "graph" should appear.
        self.assertTrue({"engine", "graph"}.issubset(result.weights))

    def test_alpha_beta_defaults_are_sensible(self) -> None:
        # Smoke test that the module exposes usable defaults.
        self.assertGreater(DEFAULT_ALPHA, 0)
        self.assertGreater(DEFAULT_BETA, 0)
        self.assertLessEqual(DEFAULT_BETA, DEFAULT_ALPHA)
