"""Unit tests for FR-099 through FR-105 graph-topology ranking signals.

Covers the seven signal-evaluation functions at their per-pair contract level.
The full ranker-integration hot-path tests are a follow-up (same phased
delivery precedent as FR-045 Python-first).

Each test class covers:
- Happy path: signal fires with expected value
- Neutral fallback: cold-start / below-data-floor returns 0.0 with diagnostic
- Disabled: settings.enabled=False returns 0.0
- Edge cases per spec §Edge Cases
"""

from __future__ import annotations

import math
from unittest import TestCase

import numpy as np

from apps.pipeline.services.articulation_point_boost import (
    ArticulationPointCache,
    TAPBSettings,
    evaluate_tapb,
)
from apps.pipeline.services.bridge_edge_redundancy import (
    BERPSettings,
    BridgeEdgeCache,
    evaluate_berp,
)
from apps.pipeline.services.dangling_authority_redistribution import (
    DARBSettings,
    evaluate_darb,
)
from apps.pipeline.services.fr099_fr105_signals import (
    FR099FR105Caches,
    FR099FR105Settings,
    evaluate_all_fr099_fr105,
)
from apps.pipeline.services.host_topic_entropy import (
    HGTESettings,
    HostSiloDistributionCache,
    evaluate_hgte,
)
from apps.pipeline.services.katz_marginal_info import (
    KMIGSettings,
    build_katz_cache_from_edges,
    evaluate_kmig,
)
from apps.pipeline.services.kcore_integration import (
    KCIBSettings,
    KCoreCache,
    evaluate_kcib,
)
from apps.pipeline.services.search_query_alignment import (
    QueryTFIDFCache,
    RSQVASettings,
    evaluate_rsqva,
)


HOST_KEY = (1, "xf_thread")
DEST_KEY = (2, "xf_thread")
OTHER_KEY = (3, "xf_thread")


# ── FR-099 DARB ──────────────────────────────────────────────────────────────
class TestDARB(TestCase):
    def test_max_bonus_at_zero_out_degree(self):
        """Host with full content-value and zero out-degree gets max bonus."""
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=1.0,
            existing_outgoing_counts={HOST_KEY: 0},
            settings=DARBSettings(),
        )
        self.assertAlmostEqual(result.score_component, 1.0, places=6)
        self.assertFalse(result.diagnostics["fallback_triggered"])

    def test_asymptotic_zero_at_high_out_degree(self):
        """Score approaches 0 as out-degree grows (but before saturation)."""
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=1.0,
            existing_outgoing_counts={HOST_KEY: 4},  # below default saturation 5
            settings=DARBSettings(),
        )
        # 1 / (1 + 4) = 0.2
        self.assertAlmostEqual(result.score_component, 0.2, places=6)

    def test_neutral_when_saturated(self):
        """out_degree >= saturation threshold → 0.0 with saturation diagnostic."""
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=0.9,
            existing_outgoing_counts={HOST_KEY: 5},
            settings=DARBSettings(out_degree_saturation=5),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertTrue(result.diagnostics["fallback_triggered"])
        self.assertEqual(result.diagnostics["diagnostic"], "saturated_host")

    def test_neutral_when_below_host_value(self):
        """content_value_score below min_host_value → 0.0."""
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=0.3,
            existing_outgoing_counts={HOST_KEY: 0},
            settings=DARBSettings(min_host_value=0.5),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "below_neutral_host_value")

    def test_neutral_when_host_value_null(self):
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=None,
            existing_outgoing_counts={HOST_KEY: 0},
            settings=DARBSettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "missing_host_value")

    def test_neutral_when_host_value_nan(self):
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=float("nan"),
            existing_outgoing_counts={HOST_KEY: 0},
            settings=DARBSettings(),
        )
        self.assertEqual(result.score_component, 0.0)

    def test_clamps_host_value_to_one(self):
        """Defensive clamp — if a bug produces host_value > 1, we still cap."""
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=1.5,
            existing_outgoing_counts={HOST_KEY: 0},
            settings=DARBSettings(),
        )
        # 1.0 / (1 + 0) = 1.0 (clamped)
        self.assertLessEqual(result.score_component, 1.0)

    def test_neutral_when_disabled(self):
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=1.0,
            existing_outgoing_counts={HOST_KEY: 0},
            settings=DARBSettings(enabled=False),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "disabled")

    def test_neutral_when_out_degree_missing(self):
        result = evaluate_darb(
            host_key=HOST_KEY,
            host_content_value=0.8,
            existing_outgoing_counts=None,
            settings=DARBSettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "missing_out_degree")


# ── FR-100 KMIG ──────────────────────────────────────────────────────────────
class TestKMIG(TestCase):
    def _build_minimal_cache(self, edges: list[tuple[tuple, tuple]]) -> any:
        """Helper: build KatzCache from keys + edges."""
        all_keys = sorted({k for e in edges for k in e})
        node_to_index = {k: i for i, k in enumerate(all_keys)}
        idx_edges = [(node_to_index[a], node_to_index[b]) for a, b in edges]
        return build_katz_cache_from_edges(node_to_index, idx_edges)

    def test_max_bonus_when_disconnected(self):
        """No path host→dest → katz=0 → score=1.0 max bonus."""
        # Need > 100 edges (min_graph_edges default)
        edges = [((i, "x"), (i + 1, "x")) for i in range(100)]
        # Ensure host/dest pair is NOT connected
        edges.append((HOST_KEY, OTHER_KEY))
        edges.append((OTHER_KEY, (99, "x")))
        cache = self._build_minimal_cache(edges)
        result = evaluate_kmig(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,  # DEST_KEY not in any edge → disconnected
            katz_cache=cache,
            settings=KMIGSettings(),
        )
        # DEST_KEY isn't even in the graph → dest_not_in_graph fallback
        self.assertEqual(result.diagnostics["diagnostic"], "dest_not_in_graph")

    def test_low_bonus_when_direct_edge(self):
        """Direct host→dest edge reduces KMIG score."""
        # Need > 100 edges (min_graph_edges default)
        edges = [((i, "x"), (i + 1, "x")) for i in range(100)]
        edges.append((HOST_KEY, DEST_KEY))  # direct edge
        cache = self._build_minimal_cache(edges)
        result = evaluate_kmig(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            katz_cache=cache,
            settings=KMIGSettings(attenuation=0.5),
        )
        # katz_2hop = 0.5 · 1 + 0.25 · 0 = 0.5 → score = 1.0 - 0.5 = 0.5
        self.assertFalse(result.diagnostics["fallback_triggered"])
        self.assertAlmostEqual(result.score_component, 0.5, places=6)
        self.assertEqual(result.diagnostics["direct_edge"], 1)

    def test_neutral_below_min_graph_edges(self):
        edges = [(HOST_KEY, DEST_KEY)]  # 1 edge << 100
        cache = self._build_minimal_cache(edges)
        result = evaluate_kmig(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            katz_cache=cache,
            settings=KMIGSettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "insufficient_graph_data")

    def test_neutral_when_disabled(self):
        result = evaluate_kmig(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            katz_cache=None,
            settings=KMIGSettings(enabled=False),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "disabled")

    def test_neutral_when_cache_missing(self):
        result = evaluate_kmig(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            katz_cache=None,
            settings=KMIGSettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "cold_start_no_graph")


# ── FR-101 TAPB ──────────────────────────────────────────────────────────────
class TestTAPB(TestCase):
    def test_scores_articulation_point(self):
        cache = ArticulationPointCache(
            articulation_point_set=frozenset([HOST_KEY]),
            total_graph_nodes=100,
            articulation_point_count=1,
        )
        result = evaluate_tapb(
            host_key=HOST_KEY,
            articulation_cache=cache,
            settings=TAPBSettings(),
        )
        self.assertEqual(result.score_component, 1.0)
        self.assertTrue(result.diagnostics["is_articulation_point"])

    def test_neutral_for_non_ap(self):
        cache = ArticulationPointCache(
            articulation_point_set=frozenset([OTHER_KEY]),
            total_graph_nodes=100,
            articulation_point_count=1,
        )
        result = evaluate_tapb(
            host_key=HOST_KEY,
            articulation_cache=cache,
            settings=TAPBSettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertFalse(result.diagnostics["is_articulation_point"])

    def test_neutral_below_floor(self):
        cache = ArticulationPointCache(
            articulation_point_set=frozenset([HOST_KEY]),
            total_graph_nodes=10,  # < 50
            articulation_point_count=1,
        )
        result = evaluate_tapb(
            host_key=HOST_KEY,
            articulation_cache=cache,
            settings=TAPBSettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "insufficient_graph_data")

    def test_neutral_when_disabled(self):
        result = evaluate_tapb(
            host_key=HOST_KEY,
            articulation_cache=None,
            settings=TAPBSettings(enabled=False),
        )
        self.assertEqual(result.score_component, 0.0)


# ── FR-102 KCIB ──────────────────────────────────────────────────────────────
class TestKCIB(TestCase):
    def test_boosts_high_to_low(self):
        cache = KCoreCache(
            kcore_number_map={HOST_KEY: 8, DEST_KEY: 2},
            max_kcore=10,
            total_graph_nodes=100,
        )
        result = evaluate_kcib(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            kcore_cache=cache,
            settings=KCIBSettings(),
        )
        # (8 - 2) / 10 = 0.6
        self.assertAlmostEqual(result.score_component, 0.6, places=6)

    def test_neutral_on_low_to_high(self):
        cache = KCoreCache(
            kcore_number_map={HOST_KEY: 2, DEST_KEY: 8},
            max_kcore=10,
            total_graph_nodes=100,
        )
        result = evaluate_kcib(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            kcore_cache=cache,
            settings=KCIBSettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "non_integrating_direction")

    def test_neutral_on_same_core(self):
        cache = KCoreCache(
            kcore_number_map={HOST_KEY: 5, DEST_KEY: 5},
            max_kcore=10,
            total_graph_nodes=100,
        )
        result = evaluate_kcib(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            kcore_cache=cache,
            settings=KCIBSettings(),
        )
        self.assertEqual(result.score_component, 0.0)

    def test_neutral_when_disabled(self):
        result = evaluate_kcib(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            kcore_cache=None,
            settings=KCIBSettings(enabled=False),
        )
        self.assertEqual(result.score_component, 0.0)


# ── FR-103 BERP ──────────────────────────────────────────────────────────────
class TestBERP(TestCase):
    def test_penalty_on_cross_bcc(self):
        cache = BridgeEdgeCache(
            bcc_label_map={HOST_KEY: 1, DEST_KEY: 2},
            bcc_size_map={1: 10, 2: 8},
            total_graph_nodes=100,
        )
        result = evaluate_berp(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            bridge_cache=cache,
            settings=BERPSettings(),
        )
        self.assertEqual(result.score_component, -1.0)
        self.assertTrue(result.diagnostics["would_create_bridge"])

    def test_neutral_when_same_bcc(self):
        cache = BridgeEdgeCache(
            bcc_label_map={HOST_KEY: 1, DEST_KEY: 1},
            bcc_size_map={1: 15},
            total_graph_nodes=100,
        )
        result = evaluate_berp(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            bridge_cache=cache,
            settings=BERPSettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertFalse(result.diagnostics["would_create_bridge"])

    def test_skips_tiny_components(self):
        cache = BridgeEdgeCache(
            bcc_label_map={HOST_KEY: 1, DEST_KEY: 2},
            bcc_size_map={1: 3, 2: 2},  # both < 5
            total_graph_nodes=100,
        )
        result = evaluate_berp(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            bridge_cache=cache,
            settings=BERPSettings(min_component_size=5),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "small_component_skip")

    def test_neutral_when_disabled(self):
        result = evaluate_berp(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            bridge_cache=None,
            settings=BERPSettings(enabled=False),
        )
        self.assertEqual(result.score_component, 0.0)


# ── FR-104 HGTE ──────────────────────────────────────────────────────────────
class TestHGTE(TestCase):
    def test_big_bonus_first_cross_silo(self):
        """Host previously all-silo-1; new link to silo 2 should boost."""
        cache = HostSiloDistributionCache(
            host_silo_counts={HOST_KEY: {1: 5}},
            num_silos=10,
        )
        result = evaluate_hgte(
            host_key=HOST_KEY,
            dest_silo_id=2,
            silo_cache=cache,
            settings=HGTESettings(),
        )
        self.assertGreater(result.score_component, 0.0)
        self.assertFalse(result.diagnostics["fallback_triggered"])

    def test_neutral_on_concentrating_link(self):
        """Host already dominates silo 1; adding another silo-1 link decreases entropy."""
        cache = HostSiloDistributionCache(
            host_silo_counts={HOST_KEY: {1: 10, 2: 1}},
            num_silos=10,
        )
        result = evaluate_hgte(
            host_key=HOST_KEY,
            dest_silo_id=1,
            silo_cache=cache,
            settings=HGTESettings(),
        )
        # Adding to dominant silo can decrease entropy
        self.assertEqual(result.score_component, 0.0)

    def test_neutral_low_out_degree(self):
        cache = HostSiloDistributionCache(
            host_silo_counts={HOST_KEY: {1: 2}},  # out_degree = 2 < 3
            num_silos=10,
        )
        result = evaluate_hgte(
            host_key=HOST_KEY,
            dest_silo_id=2,
            silo_cache=cache,
            settings=HGTESettings(min_host_out_degree=3),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "low_host_out_degree")

    def test_neutral_no_dest_silo(self):
        cache = HostSiloDistributionCache(
            host_silo_counts={HOST_KEY: {1: 5}},
            num_silos=10,
        )
        result = evaluate_hgte(
            host_key=HOST_KEY,
            dest_silo_id=None,
            silo_cache=cache,
            settings=HGTESettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "dest_no_silo")

    def test_safe_on_single_silo(self):
        """Single-silo site (num_silos=1) shouldn't div-by-zero."""
        cache = HostSiloDistributionCache(
            host_silo_counts={HOST_KEY: {1: 5}},
            num_silos=1,
        )
        result = evaluate_hgte(
            host_key=HOST_KEY,
            dest_silo_id=1,
            silo_cache=cache,
            settings=HGTESettings(),
        )
        # No math error; result is 0.0 (entropy flat or decreasing)
        self.assertEqual(result.score_component, 0.0)


# ── FR-105 RSQVA ─────────────────────────────────────────────────────────────
class TestRSQVA(TestCase):
    def _unit_vec(self, vals: list[float]) -> np.ndarray:
        v = np.array(vals, dtype=np.float32)
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def test_max_on_full_overlap(self):
        """Identical L2-normalized vectors → cosine = 1."""
        v = self._unit_vec([1.0, 1.0, 0.0])
        cache = QueryTFIDFCache(
            page_vectors={HOST_KEY: v, DEST_KEY: v.copy()},
            page_query_counts={HOST_KEY: 10, DEST_KEY: 10},
            gsc_days_available=30,
        )
        result = evaluate_rsqva(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            query_cache=cache,
            settings=RSQVASettings(),
        )
        self.assertAlmostEqual(result.score_component, 1.0, places=5)

    def test_near_zero_on_no_overlap(self):
        """Orthogonal vectors → cosine ~ 0."""
        v_host = self._unit_vec([1.0, 0.0, 0.0])
        v_dest = self._unit_vec([0.0, 1.0, 0.0])
        cache = QueryTFIDFCache(
            page_vectors={HOST_KEY: v_host, DEST_KEY: v_dest},
            page_query_counts={HOST_KEY: 10, DEST_KEY: 10},
            gsc_days_available=30,
        )
        result = evaluate_rsqva(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            query_cache=cache,
            settings=RSQVASettings(),
        )
        self.assertAlmostEqual(result.score_component, 0.0, places=5)

    def test_neutral_on_low_query_host(self):
        v = self._unit_vec([1.0, 0.0, 0.0])
        cache = QueryTFIDFCache(
            page_vectors={HOST_KEY: v, DEST_KEY: v.copy()},
            page_query_counts={HOST_KEY: 3, DEST_KEY: 10},  # host < 5
            gsc_days_available=30,
        )
        result = evaluate_rsqva(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            query_cache=cache,
            settings=RSQVASettings(min_queries_per_page=5),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "insufficient_queries_per_page")

    def test_neutral_below_data_floor(self):
        v = self._unit_vec([1.0])
        cache = QueryTFIDFCache(
            page_vectors={HOST_KEY: v, DEST_KEY: v.copy()},
            page_query_counts={HOST_KEY: 10, DEST_KEY: 10},
            gsc_days_available=3,  # < 7
        )
        result = evaluate_rsqva(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            query_cache=cache,
            settings=RSQVASettings(),
        )
        self.assertEqual(result.score_component, 0.0)
        self.assertEqual(result.diagnostics["diagnostic"], "insufficient_gsc_data")

    def test_neutral_when_disabled(self):
        result = evaluate_rsqva(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            query_cache=None,
            settings=RSQVASettings(enabled=False),
        )
        self.assertEqual(result.score_component, 0.0)


# ── Dispatcher (all 7 together) ─────────────────────────────────────────────
class TestFR099FR105Dispatcher(TestCase):
    def test_all_neutral_on_cold_start(self):
        """With no caches and default weights, weighted_contribution = 0."""
        result = evaluate_all_fr099_fr105(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            host_content_value=None,
            dest_silo_id=None,
            existing_outgoing_counts=None,
            caches=FR099FR105Caches(),  # all caches None
            settings=FR099FR105Settings(),
        )
        self.assertEqual(result.weighted_contribution, 0.0)
        # All 7 per-signal scores are 0.0
        for k, v in result.per_signal_scores.items():
            self.assertEqual(v, 0.0, msg=f"expected {k}=0.0")
        # All 7 diagnostics have fallback_triggered=True
        for k, d in result.per_signal_diagnostics.items():
            self.assertTrue(d["fallback_triggered"], msg=f"expected {k} fallback")

    def test_darb_fires_when_cache_present(self):
        """With only DARB input present, only DARB contributes."""
        result = evaluate_all_fr099_fr105(
            host_key=HOST_KEY,
            destination_key=DEST_KEY,
            host_content_value=1.0,
            dest_silo_id=None,
            existing_outgoing_counts={HOST_KEY: 0},
            caches=FR099FR105Caches(),
            settings=FR099FR105Settings(),
        )
        # DARB fires: 1.0 × 0.04 = 0.04 contribution
        self.assertAlmostEqual(result.weighted_contribution, 0.04, places=6)
        self.assertAlmostEqual(result.per_signal_scores["score_darb"], 1.0, places=6)
        # Others stay neutral
        for k in ("score_kmig", "score_tapb", "score_kcib", "score_berp", "score_hgte", "score_rsqva"):
            self.assertEqual(result.per_signal_scores[k], 0.0)

    def test_any_enabled_flag(self):
        settings_all_off = FR099FR105Settings(
            darb=DARBSettings(enabled=False),
            kmig=KMIGSettings(enabled=False),
            tapb=TAPBSettings(enabled=False),
            kcib=KCIBSettings(enabled=False),
            berp=BERPSettings(enabled=False),
            hgte=HGTESettings(enabled=False),
            rsqva=RSQVASettings(enabled=False),
        )
        self.assertFalse(settings_all_off.any_enabled)
        settings_one_on = FR099FR105Settings(darb=DARBSettings(enabled=True))
        # By default all are enabled=True — confirm at least one triggers any_enabled
        self.assertTrue(settings_one_on.any_enabled)
