"""SimpleTestCase coverage for pure helper functions extracted from services.py.

All tests run without a database (SimpleTestCase). Each class targets one
extracted helper so failures point directly at the broken function.
"""

from __future__ import annotations

import types
from collections import defaultdict
from datetime import date

from django.test import SimpleTestCase

from apps.cooccurrence.services import (
    _build_adjacency_graph,
    _build_cooccurrence_counts,
    _compute_log_likelihood,
    _compute_member_strengths,
    _compute_pair_scores,
    _compute_weighted_score,
    _disabled_co_signal,
    _extract_co_settings,
    _extract_content_signals,
    _extract_signal_weights,
    _fallback_signal_diagnostics,
    _find_connected_components,
    _llr_sigmoid,
    _make_ga4_report_body,
    _process_ga4_rows,
)


class ComputeLogLikelihoodTests(SimpleTestCase):
    def test_zero_total_sessions_returns_zero(self) -> None:
        self.assertEqual(_compute_log_likelihood(5, 10, 8, 0), 0.0)

    def test_positive_association(self) -> None:
        # 20 co-occurrences out of 100 sessions, with A=30 and B=25 marginals.
        result = _compute_log_likelihood(20, 30, 25, 100)
        self.assertGreater(result, 0.0)

    def test_degenerate_margins_return_zero(self) -> None:
        # k22 goes negative → degenerate table → 0.0
        result = _compute_log_likelihood(10, 10, 10, 10)
        self.assertEqual(result, 0.0)


class ComputePairScoresTests(SimpleTestCase):
    def test_jaccard_calculation(self) -> None:
        # co=5, a=10, b=10 → union=15, jaccard=5/15≈0.333
        scores = _compute_pair_scores(5, 10, 10, 100)
        self.assertAlmostEqual(scores["jaccard"], 5 / 15, places=6)

    def test_lift_calculation(self) -> None:
        # p_a=10/100=0.1, p_b=10/100=0.1, p_ab=5/100=0.05 → lift=0.05/0.01=5.0
        scores = _compute_pair_scores(5, 10, 10, 100)
        self.assertAlmostEqual(scores["lift"], 5.0, places=4)

    def test_perfect_overlap_jaccard_is_one(self) -> None:
        # co=a=b → union = a+b-co = co → jaccard = co/co = 1.0
        scores = _compute_pair_scores(5, 5, 5, 100)
        self.assertAlmostEqual(scores["jaccard"], 1.0, places=6)

    def test_lift_fallback_when_product_is_zero(self) -> None:
        # If a_total=0, p_a=0 so lift formula would divide by zero → falls back to 1.0
        # Use a_total=0 via marginal of 0 (technically edge case in production but guarded)
        scores = _compute_pair_scores(1, 1, 1, 1)  # p_a=p_b=1, p_ab=1, lift=1/1=1
        self.assertAlmostEqual(scores["lift"], 1.0, places=4)

    def test_pmi_positive_for_strong_association(self) -> None:
        # joint >> expected → PMI > 0
        scores = _compute_pair_scores(20, 25, 30, 100)
        self.assertGreater(scores["pmi"], 0.0)
        self.assertGreater(scores["npmi"], 0.0)

    def test_all_keys_present(self) -> None:
        scores = _compute_pair_scores(3, 5, 5, 50)
        self.assertSetEqual(
            set(scores.keys()), {"jaccard", "lift", "g2", "pmi", "npmi"}
        )


class BuildCooccurrenceCountsTests(SimpleTestCase):
    def _run(self, session_paths: dict, path_to_id: dict) -> tuple:
        return _build_cooccurrence_counts(session_paths, path_to_id)

    def test_single_item_session_counted_in_marginals_only(self) -> None:
        session_paths = {"s1": {"/a"}}
        path_to_id = {"/a": 1}
        co, marg, processed = self._run(session_paths, path_to_id)
        self.assertEqual(processed, 0)
        self.assertEqual(marg[1], 1)
        self.assertEqual(len(co), 0)

    def test_two_item_session_produces_symmetric_pairs(self) -> None:
        session_paths = {"s1": {"/a", "/b"}}
        path_to_id = {"/a": 1, "/b": 2}
        co, marg, processed = self._run(session_paths, path_to_id)
        self.assertEqual(processed, 1)
        self.assertEqual(co[(1, 2)], 1)
        self.assertEqual(co[(2, 1)], 1)
        self.assertEqual(marg[1], 1)
        self.assertEqual(marg[2], 1)

    def test_three_item_session_produces_three_pair_combinations(self) -> None:
        session_paths = {"s1": {"/a", "/b", "/c"}}
        path_to_id = {"/a": 1, "/b": 2, "/c": 3}
        co, _marg, processed = self._run(session_paths, path_to_id)
        self.assertEqual(processed, 1)
        # C(3,2)=3 pairs, each stored both directions → 6 keys
        self.assertEqual(len(co), 6)

    def test_unknown_path_excluded(self) -> None:
        session_paths = {"s1": {"/a", "/unknown"}}
        path_to_id = {"/a": 1}
        co, marg, processed = self._run(session_paths, path_to_id)
        # Only one known path → single-item session, no pairs
        self.assertEqual(processed, 0)
        self.assertEqual(len(co), 0)

    def test_multiple_sessions_accumulate_counts(self) -> None:
        session_paths = {"s1": {"/a", "/b"}, "s2": {"/a", "/b"}}
        path_to_id = {"/a": 1, "/b": 2}
        co, _marg, processed = self._run(session_paths, path_to_id)
        self.assertEqual(processed, 2)
        self.assertEqual(co[(1, 2)], 2)


class MakeGa4ReportBodyTests(SimpleTestCase):
    def test_structure(self) -> None:
        body = _make_ga4_report_body(date(2026, 1, 1), date(2026, 3, 31), 10_000, 0)
        self.assertEqual(body["dateRanges"][0]["startDate"], "2026-01-01")
        self.assertEqual(body["dateRanges"][0]["endDate"], "2026-03-31")
        self.assertEqual(body["limit"], 10_000)
        self.assertEqual(body["offset"], 0)
        dim_names = [d["name"] for d in body["dimensions"]]
        self.assertIn("sessionId", dim_names)
        self.assertIn("pagePath", dim_names)


class ProcessGa4RowsTests(SimpleTestCase):
    def _make_row(self, session_id: str, page_path: str) -> dict:
        return {"dimensionValues": [{"value": session_id}, {"value": page_path}]}

    def test_adds_path_to_session(self) -> None:
        session_paths: dict = defaultdict(set)
        _process_ga4_rows([self._make_row("abc", "/home")], session_paths)
        self.assertIn("abc", session_paths)
        self.assertIn("/home", session_paths["abc"])

    def test_strips_query_string(self) -> None:
        session_paths: dict = defaultdict(set)
        _process_ga4_rows([self._make_row("s1", "/page?foo=1")], session_paths)
        self.assertIn("/page", session_paths["s1"])

    def test_empty_session_id_skipped(self) -> None:
        session_paths: dict = defaultdict(set)
        _process_ga4_rows([self._make_row("", "/home")], session_paths)
        self.assertEqual(len(session_paths), 0)

    def test_row_with_fewer_than_two_dims_skipped(self) -> None:
        session_paths: dict = defaultdict(set)
        _process_ga4_rows([{"dimensionValues": [{"value": "s1"}]}], session_paths)
        self.assertEqual(len(session_paths), 0)


class LlrSigmoidTests(SimpleTestCase):
    def test_midpoint_returns_half(self) -> None:
        # g2 == beta → exponent = 0 → 1/(1+1) = 0.5
        self.assertAlmostEqual(_llr_sigmoid(10.0, alpha=0.1, beta=10.0), 0.5, places=6)

    def test_large_g2_approaches_one(self) -> None:
        result = _llr_sigmoid(1000.0, alpha=0.1, beta=10.0)
        self.assertGreater(result, 0.99)

    def test_zero_g2_less_than_half(self) -> None:
        # g2=0, beta=10 → exponent positive → output < 0.5
        result = _llr_sigmoid(0.0, alpha=0.1, beta=10.0)
        self.assertLess(result, 0.5)

    def test_clamping_prevents_overflow(self) -> None:
        # exponent of -10000 would overflow without clamping; must not raise
        result = _llr_sigmoid(0.0, alpha=1000.0, beta=10.0)
        self.assertAlmostEqual(result, 0.0, places=3)


class FallbackSignalDiagnosticsTests(SimpleTestCase):
    def test_returns_fallback_as_signal(self) -> None:
        diag = _fallback_signal_diagnostics(0.3)
        self.assertEqual(diag["co_occurrence_signal"], 0.3)

    def test_fallback_used_is_true(self) -> None:
        diag = _fallback_signal_diagnostics(0.5)
        self.assertTrue(diag["co_occurrence_fallback_used"])

    def test_expected_keys_present(self) -> None:
        diag = _fallback_signal_diagnostics(0.5)
        for key in (
            "co_session_count",
            "jaccard_similarity",
            "log_likelihood_score",
            "lift",
        ):
            self.assertIn(key, diag)


class BuildAdjacencyGraphTests(SimpleTestCase):
    def test_undirected_both_directions_added(self) -> None:
        graph = _build_adjacency_graph([(1, 2), (2, 3)])
        self.assertIn(2, graph[1])
        self.assertIn(1, graph[2])
        self.assertIn(3, graph[2])
        self.assertIn(2, graph[3])

    def test_empty_input_returns_empty_dict(self) -> None:
        graph = _build_adjacency_graph([])
        self.assertEqual(len(graph), 0)

    def test_self_loop_allowed(self) -> None:
        graph = _build_adjacency_graph([(1, 1)])
        self.assertIn(1, graph[1])


class FindConnectedComponentsTests(SimpleTestCase):
    def test_two_node_cluster_below_min_filtered(self) -> None:
        graph = {1: {2}, 2: {1}}
        components = _find_connected_components(graph, min_members=3)
        self.assertEqual(components, [])

    def test_three_node_cluster_included(self) -> None:
        graph = {1: {2, 3}, 2: {1, 3}, 3: {1, 2}}
        components = _find_connected_components(graph, min_members=3)
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0], {1, 2, 3})

    def test_two_disjoint_clusters_both_found(self) -> None:
        graph = {1: {2, 3}, 2: {1, 3}, 3: {1, 2}, 4: {5, 6}, 5: {4, 6}, 6: {4, 5}}
        components = _find_connected_components(graph, min_members=3)
        self.assertEqual(len(components), 2)

    def test_empty_graph_returns_empty(self) -> None:
        self.assertEqual(_find_connected_components({}, min_members=2), [])


class ComputeMemberStrengthsTests(SimpleTestCase):
    def test_average_jaccard_over_neighbors(self) -> None:
        all_pairs = {(1, 2): 0.6, (1, 3): 0.4}
        strengths = _compute_member_strengths([1, 2, 3], all_pairs)
        # Node 1: neighbors are 2 (0.6) and 3 (0.4) → avg 0.5
        self.assertAlmostEqual(strengths[1], 0.5, places=6)

    def test_single_member_strength_is_zero(self) -> None:
        strengths = _compute_member_strengths([1], {})
        self.assertEqual(strengths[1], 0.0)

    def test_symmetric_lookup_fallback(self) -> None:
        # Pair stored as (2,1) should still be found for node 1's neighbor 2
        all_pairs = {(2, 1): 0.8}
        strengths = _compute_member_strengths([1, 2], all_pairs)
        self.assertAlmostEqual(strengths[1], 0.8, places=6)


class ExtractCoSettingsTests(SimpleTestCase):
    def test_defaults_when_empty(self) -> None:
        min_co, fallback, enabled, alpha, beta = _extract_co_settings({})
        self.assertEqual(min_co, 5)
        self.assertAlmostEqual(fallback, 0.5)
        self.assertTrue(enabled)
        self.assertAlmostEqual(alpha, 0.1)
        self.assertAlmostEqual(beta, 10.0)

    def test_explicit_values_override_defaults(self) -> None:
        settings = {
            "co_occurrence_min_co_sessions": 10,
            "co_occurrence_fallback_value": 0.3,
            "co_occurrence_signal_enabled": False,
            "co_occurrence.llr_sigmoid_alpha": 0.2,
            "co_occurrence.llr_sigmoid_beta": 5.0,
        }
        min_co, fallback, enabled, alpha, beta = _extract_co_settings(settings)
        self.assertEqual(min_co, 10)
        self.assertAlmostEqual(fallback, 0.3)
        self.assertFalse(enabled)
        self.assertAlmostEqual(alpha, 0.2)
        self.assertAlmostEqual(beta, 5.0)


class ExtractSignalWeightsTests(SimpleTestCase):
    _DEFAULT_SUM = 0.35 + 0.25 + 0.1 + 0.1 + 0.08 + 0.12  # excludes penalty

    def test_defaults_when_empty(self) -> None:
        weights = _extract_signal_weights({})
        self.assertAlmostEqual(weights["w_relevance"], 0.35)
        self.assertAlmostEqual(weights["w_penalty"], 0.5)

    def test_all_seven_keys_present(self) -> None:
        weights = _extract_signal_weights({})
        expected = {
            "w_relevance",
            "w_traffic",
            "w_freshness",
            "w_authority",
            "w_engagement",
            "w_cooccurrence",
            "w_penalty",
        }
        self.assertSetEqual(set(weights.keys()), expected)

    def test_partial_override(self) -> None:
        weights = _extract_signal_weights({"w_relevance": 0.5})
        self.assertAlmostEqual(weights["w_relevance"], 0.5)
        self.assertAlmostEqual(weights["w_traffic"], 0.25)  # default unchanged


class DisabledCoSignalTests(SimpleTestCase):
    def test_first_element_is_fallback(self) -> None:
        signal, _diag = _disabled_co_signal(0.42)
        self.assertAlmostEqual(signal, 0.42)

    def test_fallback_used_true(self) -> None:
        _signal, diag = _disabled_co_signal(0.5)
        self.assertTrue(diag["co_occurrence_fallback_used"])

    def test_signal_in_diagnostics_matches_fallback(self) -> None:
        _signal, diag = _disabled_co_signal(0.7)
        self.assertAlmostEqual(diag["co_occurrence_signal"], 0.7)


class ComputeWeightedScoreTests(SimpleTestCase):
    _WEIGHTS = {
        "w_relevance": 0.35,
        "w_traffic": 0.25,
        "w_freshness": 0.1,
        "w_authority": 0.1,
        "w_engagement": 0.08,
        "w_cooccurrence": 0.12,
        "w_penalty": 0.0,
    }

    def _signals(self, **overrides) -> dict:
        base = {
            "relevance": 0.5,
            "traffic": 0.5,
            "freshness": 0.5,
            "authority": 0.5,
            "engagement": 0.5,
            "co": 0.5,
            "penalty": 0.0,
        }
        base.update(overrides)
        return base

    def test_basic_weighted_sum(self) -> None:
        # All signals=1, penalty_weight=0 → score = sum of positive weights
        signals = self._signals(
            relevance=1.0,
            traffic=1.0,
            freshness=1.0,
            authority=1.0,
            engagement=1.0,
            co=1.0,
            penalty=0.0,
        )
        score = _compute_weighted_score(signals, self._WEIGHTS)
        expected = 0.35 + 0.25 + 0.1 + 0.1 + 0.08 + 0.12
        self.assertAlmostEqual(score, expected, places=6)

    def test_penalty_subtracts(self) -> None:
        weights = {**self._WEIGHTS, "w_penalty": 1.0}
        no_penalty = _compute_weighted_score(self._signals(penalty=0.0), weights)
        with_penalty = _compute_weighted_score(self._signals(penalty=0.5), weights)
        self.assertLess(with_penalty, no_penalty)

    def test_clamps_below_zero(self) -> None:
        weights = {**self._WEIGHTS, "w_penalty": 10.0}
        score = _compute_weighted_score(self._signals(penalty=1.0), weights)
        self.assertEqual(score, 0.0)

    def test_clamps_above_one(self) -> None:
        weights = {**self._WEIGHTS, "w_relevance": 5.0}
        score = _compute_weighted_score(self._signals(relevance=1.0), weights)
        self.assertEqual(score, 1.0)


class ExtractContentSignalsTests(SimpleTestCase):
    def _make_suggestion(self, **dest_attrs) -> object:
        dest = types.SimpleNamespace(**dest_attrs)
        return types.SimpleNamespace(score_semantic=0.8, destination=dest, host=None)

    def test_reads_score_semantic(self) -> None:
        suggestion = self._make_suggestion()
        signals = _extract_content_signals(suggestion)
        self.assertAlmostEqual(signals["relevance"], 0.8)

    def test_fallback_when_dest_attribute_missing(self) -> None:
        suggestion = self._make_suggestion()  # dest has no content_value_score
        signals = _extract_content_signals(suggestion)
        self.assertAlmostEqual(signals["traffic"], 0.5)

    def test_reads_dest_attributes(self) -> None:
        suggestion = self._make_suggestion(
            content_value_score=0.7,
            link_freshness_score=0.6,
            march_2026_pagerank_score=0.4,
            engagement_quality_score=0.9,
        )
        signals = _extract_content_signals(suggestion)
        self.assertAlmostEqual(signals["traffic"], 0.7)
        self.assertAlmostEqual(signals["freshness"], 0.6)
        self.assertAlmostEqual(signals["authority"], 0.4)
        self.assertAlmostEqual(signals["engagement"], 0.9)

    def test_none_score_semantic_falls_back(self) -> None:
        dest = types.SimpleNamespace()
        suggestion = types.SimpleNamespace(
            score_semantic=None, destination=dest, host=None
        )
        signals = _extract_content_signals(suggestion)
        self.assertAlmostEqual(signals["relevance"], 0.5)
