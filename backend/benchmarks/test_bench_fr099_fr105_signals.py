"""Benchmarks for FR-099 through FR-105 graph-topology signals.

Measures per-candidate eval cost for all 7 signals at 3 input sizes
(10 / 100 / 500 candidates), per BLC §1.4 mandatory benchmark rule.

Per-candidate hot-path target: < 50 ms / 500 candidates (Python).
Precompute targets documented in each FR spec §Hardware Budget.

Run with:
    pytest backend/benchmarks/test_bench_fr099_fr105_signals.py --benchmark-only
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

_ext_dir = str(Path(__file__).resolve().parent.parent / "extensions")
if _ext_dir not in sys.path:
    sys.path.insert(0, _ext_dir)

import django  # noqa: E402

django.setup()

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from apps.pipeline.services.articulation_point_boost import (  # noqa: E402
    ArticulationPointCache,
    TAPBSettings,
    evaluate_tapb,
)
from apps.pipeline.services.bridge_edge_redundancy import (  # noqa: E402
    BERPSettings,
    BridgeEdgeCache,
    evaluate_berp,
)
from apps.pipeline.services.dangling_authority_redistribution import (  # noqa: E402
    DARBSettings,
    evaluate_darb,
)
from apps.pipeline.services.fr099_fr105_signals import (  # noqa: E402
    FR099FR105Caches,
    FR099FR105Settings,
    evaluate_all_fr099_fr105,
)
from apps.pipeline.services.host_topic_entropy import (  # noqa: E402
    HGTESettings,
    HostSiloDistributionCache,
    evaluate_hgte,
)
from apps.pipeline.services.katz_marginal_info import (  # noqa: E402
    KMIGSettings,
    build_katz_cache_from_edges,
    evaluate_kmig,
)
from apps.pipeline.services.kcore_integration import (  # noqa: E402
    KCIBSettings,
    KCoreCache,
    evaluate_kcib,
)
from apps.pipeline.services.search_query_alignment import (  # noqa: E402
    QueryTFIDFCache,
    RSQVASettings,
    evaluate_rsqva,
)


SIZES = [10, 100, 500]


def _make_pairs(n: int):
    return [((i, "thread"), (i + n, "thread")) for i in range(n)]


def _make_out_counts(n: int):
    return {(i, "thread"): (i % 10) for i in range(2 * n)}


@pytest.mark.parametrize("n", SIZES)
def test_bench_darb(benchmark, n):
    """FR-099 DARB: O(1) per candidate — should be <1 ms even at 500 cands."""
    pairs = _make_pairs(n)
    out_counts = _make_out_counts(n)
    settings = DARBSettings()

    def run():
        for host_key, _dest_key in pairs:
            evaluate_darb(
                host_key=host_key,
                host_content_value=0.7,
                existing_outgoing_counts=out_counts,
                settings=settings,
            )

    benchmark(run)


@pytest.mark.parametrize("n", SIZES)
def test_bench_kmig(benchmark, n):
    """FR-100 KMIG: O(1) sparse lookup per candidate post-precompute."""
    # Build a sparse graph: 2n nodes, ~3n edges (enough to exceed min_graph_edges=100 at n>=50)
    all_keys = [(i, "thread") for i in range(2 * n)]
    node_to_index = {k: i for i, k in enumerate(all_keys)}
    # Chain edges + a few cross-links
    edges = [(i, i + 1) for i in range(2 * n - 1)]
    edges += [(i, (i + 3) % (2 * n)) for i in range(0, 2 * n, 2)]
    cache = build_katz_cache_from_edges(node_to_index, edges)
    pairs = _make_pairs(n)
    settings = KMIGSettings(min_graph_edges=10)  # lower floor for bench

    def run():
        for host_key, dest_key in pairs:
            evaluate_kmig(
                host_key=host_key,
                destination_key=dest_key,
                katz_cache=cache,
                settings=settings,
            )

    benchmark(run)


@pytest.mark.parametrize("n", SIZES)
def test_bench_tapb(benchmark, n):
    """FR-101 TAPB: O(1) frozenset membership per candidate."""
    ap_set = frozenset([(i, "thread") for i in range(0, n, 5)])
    cache = ArticulationPointCache(
        articulation_point_set=ap_set,
        total_graph_nodes=max(100, 2 * n),
        articulation_point_count=len(ap_set),
    )
    pairs = _make_pairs(n)
    settings = TAPBSettings()

    def run():
        for host_key, _ in pairs:
            evaluate_tapb(
                host_key=host_key,
                articulation_cache=cache,
                settings=settings,
            )

    benchmark(run)


@pytest.mark.parametrize("n", SIZES)
def test_bench_kcib(benchmark, n):
    """FR-102 KCIB: O(1) two dict lookups + one subtract per candidate."""
    kcore_map = {(i, "thread"): (i % 10) for i in range(2 * n)}
    cache = KCoreCache(
        kcore_number_map=kcore_map,
        max_kcore=10,
        total_graph_nodes=max(100, 2 * n),
    )
    pairs = _make_pairs(n)
    settings = KCIBSettings()

    def run():
        for host_key, dest_key in pairs:
            evaluate_kcib(
                host_key=host_key,
                destination_key=dest_key,
                kcore_cache=cache,
                settings=settings,
            )

    benchmark(run)


@pytest.mark.parametrize("n", SIZES)
def test_bench_berp(benchmark, n):
    """FR-103 BERP: O(1) two dict lookups + one comparison per candidate."""
    bcc_label_map = {(i, "thread"): (i % 7) for i in range(2 * n)}
    bcc_size_map = {i: max(5, n // 7) for i in range(7)}
    cache = BridgeEdgeCache(
        bcc_label_map=bcc_label_map,
        bcc_size_map=bcc_size_map,
        total_graph_nodes=max(100, 2 * n),
    )
    pairs = _make_pairs(n)
    settings = BERPSettings()

    def run():
        for host_key, dest_key in pairs:
            evaluate_berp(
                host_key=host_key,
                destination_key=dest_key,
                bridge_cache=cache,
                settings=settings,
            )

    benchmark(run)


@pytest.mark.parametrize("n", SIZES)
def test_bench_hgte(benchmark, n):
    """FR-104 HGTE: O(silo_count) per candidate — ~20 silos max."""
    host_silo_counts = {
        (i, "thread"): {j: (i % (j + 1) + 1) for j in range(1, 6)}
        for i in range(2 * n)
    }
    cache = HostSiloDistributionCache(
        host_silo_counts=host_silo_counts,
        num_silos=10,
    )
    pairs = _make_pairs(n)
    settings = HGTESettings()

    def run():
        for host_key, _ in pairs:
            evaluate_hgte(
                host_key=host_key,
                dest_silo_id=7,
                silo_cache=cache,
                settings=settings,
            )

    benchmark(run)


@pytest.mark.parametrize("n", SIZES)
def test_bench_rsqva(benchmark, n):
    """FR-105 RSQVA: O(vocab_size) dot product per candidate. 1024-dim dense here."""
    rng = np.random.default_rng(seed=42)

    def _unit(v):
        nrm = float(np.linalg.norm(v))
        return (v / nrm).astype(np.float32) if nrm > 0 else v.astype(np.float32)

    page_vectors = {
        (i, "thread"): _unit(rng.random(1024).astype(np.float32))
        for i in range(2 * n)
    }
    cache = QueryTFIDFCache(
        page_vectors=page_vectors,
        page_query_counts={k: 20 for k in page_vectors},
        gsc_days_available=30,
    )
    pairs = _make_pairs(n)
    settings = RSQVASettings()

    def run():
        for host_key, dest_key in pairs:
            evaluate_rsqva(
                host_key=host_key,
                destination_key=dest_key,
                query_cache=cache,
                settings=settings,
            )

    benchmark(run)


@pytest.mark.parametrize("n", SIZES)
def test_bench_dispatcher_combined(benchmark, n):
    """All 7 signals combined per-candidate via the dispatcher.

    BLC §6.1 budget: < 50 ms / 500 candidates Python hot-path.
    Expected combined cost: ~5-10 ms / 500 candidates on target machine.
    """
    pairs = _make_pairs(n)
    out_counts = _make_out_counts(n)
    caches = FR099FR105Caches()  # cold start — exercises fallback paths
    settings = FR099FR105Settings()

    def run():
        for host_key, dest_key in pairs:
            evaluate_all_fr099_fr105(
                host_key=host_key,
                destination_key=dest_key,
                host_content_value=0.7,
                dest_silo_id=3,
                existing_outgoing_counts=out_counts,
                caches=caches,
                settings=settings,
            )

    benchmark(run)
