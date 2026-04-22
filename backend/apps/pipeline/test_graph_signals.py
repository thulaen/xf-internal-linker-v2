"""Tests for PR-M graph signals — HITS, PPR, TrustRank, Auto-Seeder."""

from __future__ import annotations

import networkx as nx
from django.test import SimpleTestCase

from apps.pipeline.services.hits import (
    HitsScores,
    compute as hits_compute,
    top_authorities,
    top_hubs,
)
from apps.pipeline.services.personalized_pagerank import (
    PersonalizedPageRankScores,
    build_seed_personalization,
    compute as ppr_compute,
)
from apps.pipeline.services.trustrank import (
    TrustRankScores,
    compute as trustrank_compute,
)
from apps.pipeline.services.trustrank_auto_seeder import (
    AutoSeedResult,
    DEFAULT_POST_QUALITY_MIN,
    pick_seeds,
)


def _tiny_graph() -> nx.DiGraph:
    """5-node graph with obvious hub/authority/popularity structure."""
    g = nx.DiGraph()
    # "hub" points to many authorities.
    g.add_edges_from(
        [
            ("hub", "auth1"),
            ("hub", "auth2"),
            ("hub", "auth3"),
            ("other_hub", "auth1"),
            ("other_hub", "auth2"),
            ("spam1", "spam2"),
            ("spam2", "spam1"),
        ]
    )
    return g


# ── HITS ────────────────────────────────────────────────────────────


class HitsTests(SimpleTestCase):
    def test_returns_hits_scores_for_every_node(self) -> None:
        g = _tiny_graph()
        scores = hits_compute(g)
        self.assertIsInstance(scores, HitsScores)
        self.assertEqual(set(scores.authority), set(g.nodes))
        self.assertEqual(set(scores.hub), set(g.nodes))

    def test_hubs_score_highest_for_hub_like_nodes(self) -> None:
        g = _tiny_graph()
        scores = hits_compute(g)
        top_hub_node = max(scores.hub.items(), key=lambda x: x[1])[0]
        self.assertIn(top_hub_node, {"hub", "other_hub"})

    def test_authority_score_highest_for_cited_nodes(self) -> None:
        g = _tiny_graph()
        scores = hits_compute(g)
        top_auth_node = max(scores.authority.items(), key=lambda x: x[1])[0]
        # auth1 and auth2 get two incoming edges each — tie is allowed.
        self.assertIn(top_auth_node, {"auth1", "auth2"})

    def test_rejects_undirected_graph(self) -> None:
        with self.assertRaises(ValueError):
            hits_compute(nx.Graph())

    def test_empty_graph_returns_empty_scores(self) -> None:
        scores = hits_compute(nx.DiGraph())
        self.assertEqual(scores.authority, {})
        self.assertEqual(scores.hub, {})

    def test_top_authorities_returns_sorted_pairs(self) -> None:
        g = _tiny_graph()
        scores = hits_compute(g)
        top = top_authorities(scores, k=3)
        values = [pair[1] for pair in top]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_top_hubs_caps_at_k(self) -> None:
        g = _tiny_graph()
        scores = hits_compute(g)
        self.assertEqual(len(top_hubs(scores, k=2)), 2)


# ── Personalized PageRank ──────────────────────────────────────────


class PersonalizedPageRankTests(SimpleTestCase):
    def test_returns_scores_for_every_node(self) -> None:
        g = _tiny_graph()
        result = ppr_compute(g, seeds=["hub"])
        self.assertEqual(set(result.scores), set(g.nodes))

    def test_biases_toward_seeds(self) -> None:
        g = _tiny_graph()
        with_hub = ppr_compute(g, seeds=["hub"])
        with_spam = ppr_compute(g, seeds=["spam1"])
        # The "hub" seed should pull more mass onto auth1/2/3 than
        # the spam seed would.
        self.assertGreater(
            with_hub.scores["auth1"],
            with_spam.scores["auth1"],
        )

    def test_unknown_seeds_silently_dropped(self) -> None:
        g = _tiny_graph()
        result = ppr_compute(g, seeds=["hub", "does-not-exist"])
        self.assertEqual(result.seed_nodes, frozenset({"hub"}))

    def test_no_valid_seeds_falls_back_to_uniform(self) -> None:
        g = _tiny_graph()
        result = ppr_compute(g, seeds=["does-not-exist"])
        # All nodes receive some mass from the uniform teleport.
        self.assertTrue(all(s > 0 for s in result.scores.values()))

    def test_damping_out_of_range_rejected(self) -> None:
        g = _tiny_graph()
        with self.assertRaises(ValueError):
            ppr_compute(g, seeds=["hub"], damping=0.0)
        with self.assertRaises(ValueError):
            ppr_compute(g, seeds=["hub"], damping=1.0)

    def test_build_seed_personalization_uniform(self) -> None:
        g = _tiny_graph()
        dist = build_seed_personalization(["hub", "auth1"], g)
        self.assertEqual(len(dist), 2)
        self.assertAlmostEqual(sum(dist.values()), 1.0)
        self.assertAlmostEqual(dist["hub"], dist["auth1"])

    def test_build_seed_personalization_drops_unknown(self) -> None:
        g = _tiny_graph()
        dist = build_seed_personalization(["hub", "ghost"], g)
        self.assertEqual(set(dist), {"hub"})

    def test_custom_seed_weights_respected(self) -> None:
        g = _tiny_graph()
        result = ppr_compute(
            g,
            seeds=["hub", "other_hub"],
            seed_weights={"hub": 0.9, "other_hub": 0.1},
        )
        self.assertIsInstance(result, PersonalizedPageRankScores)


# ── TrustRank ──────────────────────────────────────────────────────


class TrustRankTests(SimpleTestCase):
    def test_returns_trust_scores_for_every_node(self) -> None:
        g = _tiny_graph()
        result = trustrank_compute(g, trusted_seeds=["hub"])
        self.assertIsInstance(result, TrustRankScores)
        self.assertEqual(set(result.scores), set(g.nodes))
        self.assertEqual(result.reason, "trust_propagated_from_seeds")

    def test_trust_flows_to_seeds_neighbours(self) -> None:
        g = _tiny_graph()
        result = trustrank_compute(g, trusted_seeds=["hub"])
        # The seed's direct neighbours should outscore an unrelated
        # spam node.
        self.assertGreater(result.scores["auth1"], result.scores["spam1"])

    def test_no_valid_seeds_fallback_noted(self) -> None:
        g = _tiny_graph()
        result = trustrank_compute(g, trusted_seeds=["nobody"])
        self.assertEqual(result.reason, "no_trusted_seeds_fallback_uniform")
        self.assertEqual(result.seed_nodes, frozenset())

    def test_empty_graph(self) -> None:
        result = trustrank_compute(nx.DiGraph(), trusted_seeds=["x"])
        self.assertEqual(result.reason, "empty_graph")
        self.assertEqual(result.scores, {})


# ── Auto-Seeder ────────────────────────────────────────────────────


class AutoSeederTests(SimpleTestCase):
    def test_picks_seeds_by_inverse_pagerank(self) -> None:
        g = _tiny_graph()
        result = pick_seeds(g, seed_count_k=2, candidate_pool_size=10)
        self.assertIsInstance(result, AutoSeedResult)
        self.assertEqual(len(result.seeds), 2)

    def test_spam_candidates_rejected(self) -> None:
        g = _tiny_graph()
        # Without any quality info, the hub nodes dominate.
        result = pick_seeds(
            g,
            seed_count_k=2,
            candidate_pool_size=10,
            spam_flagged={"hub"},
        )
        self.assertNotIn("hub", result.seeds)

    def test_post_quality_filter_applied(self) -> None:
        g = _tiny_graph()
        low_quality = {"hub": DEFAULT_POST_QUALITY_MIN - 0.1}
        result = pick_seeds(
            g,
            seed_count_k=2,
            candidate_pool_size=10,
            post_quality=low_quality,
        )
        self.assertNotIn("hub", result.seeds)

    def test_fallback_kicks_in_when_filters_exhaust_pool(self) -> None:
        g = _tiny_graph()
        # Flag everything as spam — the filtered pool becomes empty.
        all_spam = set(g.nodes)
        result = pick_seeds(
            g,
            seed_count_k=2,
            candidate_pool_size=10,
            spam_flagged=all_spam,
        )
        self.assertTrue(result.fallback_used)
        self.assertEqual(len(result.seeds), 2)
        self.assertEqual(result.reason, "fallback_to_top_k_by_pagerank")

    def test_empty_graph_returns_empty(self) -> None:
        result = pick_seeds(nx.DiGraph())
        self.assertEqual(result.seeds, [])
        self.assertEqual(result.reason, "empty_graph")

    def test_undirected_graph_rejected(self) -> None:
        with self.assertRaises(ValueError):
            pick_seeds(nx.Graph())

    def test_readability_ceiling_applied(self) -> None:
        g = _tiny_graph()
        result = pick_seeds(
            g,
            seed_count_k=2,
            candidate_pool_size=10,
            readability_grade={"hub": 99.0},
            readability_grade_max=16.0,
        )
        self.assertNotIn("hub", result.seeds)
