"""Benchmarks for 52-pick Score & Rank helpers — FR-230 / G6.

Covered shipped helpers:
- `apps.pipeline.services.query_expansion_bow`    — pick #27 (PR-K)
- `apps.pipeline.services.query_likelihood`       — pick #28 (PR-K)
- `apps.pipeline.services.reciprocal_rank_fusion` — pick #31 (PR-L)
- `apps.pipeline.services.platt_calibration`      — pick #32 (PR-L)
- `apps.pipeline.services.hits`                   — pick #29 (PR-M)
- `apps.pipeline.services.personalized_pagerank`  — pick #36 (PR-M)
- `apps.pipeline.services.trustrank`              — pick #30 (PR-M)
- `apps.pipeline.services.trustrank_auto_seeder`  — pick #51 (PR-M)
"""

from __future__ import annotations

import random

import numpy as np
import pytest


def _random_graph(n_nodes: int, avg_out_degree: int, seed: int):
    import networkx as nx

    rng = random.Random(seed)
    g = nx.DiGraph()
    g.add_nodes_from(range(n_nodes))
    for src in range(n_nodes):
        k = rng.randint(max(1, avg_out_degree - 2), avg_out_degree + 2)
        for _ in range(k):
            dst = rng.randrange(n_nodes)
            if dst != src:
                g.add_edge(src, dst)
    return g


# ── Query Expansion BoW (#27) ─────────────────────────────────────


def _qe_workload(query_weights, docs):
    from apps.pipeline.services.query_expansion_bow import expand

    expand(
        original_query_weights=query_weights,
        pseudo_relevant_docs=docs,
        top_terms=10,
    )


def test_bench_query_expansion_small(benchmark):
    query = {"search": 1.0, "relevance": 0.5}
    docs = [{f"term-{i}": 2 + i % 5 for i in range(100)} for _ in range(10)]
    benchmark(_qe_workload, query, docs)


def test_bench_query_expansion_medium(benchmark):
    query = {"search": 1.0, "relevance": 0.5}
    docs = [{f"term-{i}": 2 + i % 5 for i in range(1000)} for _ in range(30)]
    benchmark(_qe_workload, query, docs)


def test_bench_query_expansion_large(benchmark):
    query = {"search": 1.0, "relevance": 0.5}
    docs = [{f"term-{i}": 2 + i % 5 for i in range(10_000)} for _ in range(100)]
    benchmark(_qe_workload, query, docs)


# ── QL-Dirichlet (#28) ────────────────────────────────────────────


def _ql_batch(stats, queries_and_docs):
    from apps.pipeline.services.query_likelihood import score_document

    for q, d_counts, d_len in queries_and_docs:
        score_document(
            query_term_counts=q,
            document_term_counts=d_counts,
            document_length=d_len,
            statistics=stats,
            mu=2000.0,
        )


@pytest.fixture
def collection_stats():
    from apps.pipeline.services.query_likelihood import CollectionStatistics

    rng = random.Random(0)
    counts = {f"t-{i}": rng.randint(1, 1000) for i in range(10_000)}
    length = sum(counts.values())
    return CollectionStatistics(collection_term_counts=counts, collection_length=length)


def test_bench_ql_small(benchmark, collection_stats):
    pairs = [({"t-1": 1, "t-2": 1}, {"t-1": 5, "t-10": 3}, 20)] * 100
    benchmark(_ql_batch, collection_stats, pairs)


def test_bench_ql_medium(benchmark, collection_stats):
    pairs = [({"t-1": 1, "t-2": 1}, {"t-1": 5, "t-10": 3}, 20)] * 100_000
    benchmark(_ql_batch, collection_stats, pairs)


def test_bench_ql_large(benchmark, collection_stats):
    pairs = [({"t-1": 1, "t-2": 1}, {"t-1": 5, "t-10": 3}, 20)] * 1_000_000
    benchmark(_ql_batch, collection_stats, pairs)


# ── RRF (#31) ─────────────────────────────────────────────────────


def _rrf_workload(rankings):
    from apps.pipeline.services.reciprocal_rank_fusion import fuse

    fuse(rankings, k=60)


def test_bench_rrf_small(benchmark):
    rankings = {
        "bm25": list(range(100)),
        "semantic": list(range(50, 150)),
        "ql": list(range(25, 125)),
    }
    benchmark(_rrf_workload, rankings)


def test_bench_rrf_medium(benchmark):
    rankings = {
        "bm25": list(range(10_000)),
        "semantic": list(range(5_000, 15_000)),
        "ql": list(range(7_500, 17_500)),
    }
    benchmark(_rrf_workload, rankings)


def test_bench_rrf_large(benchmark):
    rankings = {
        f"r{i}": list(range(i * 100_000, i * 100_000 + 1_000_000)) for i in range(5)
    }
    benchmark(_rrf_workload, rankings)


# ── Platt Calibration (#32) ───────────────────────────────────────


def _platt_fit_and_predict(scores, labels, predict_batch):
    from apps.pipeline.services.platt_calibration import fit

    cal = fit(scores=scores, labels=labels)
    cal.predict_many(predict_batch)


def test_bench_platt_small(benchmark):
    rng = np.random.default_rng(0)
    scores = rng.standard_normal(100).tolist()
    labels = [1 if s > 0 else 0 for s in scores]
    predict_batch = rng.standard_normal(100).tolist()
    benchmark(_platt_fit_and_predict, scores, labels, predict_batch)


def test_bench_platt_medium(benchmark):
    rng = np.random.default_rng(0)
    scores = rng.standard_normal(10_000).tolist()
    labels = [1 if s > 0 else 0 for s in scores]
    predict_batch = rng.standard_normal(10_000).tolist()
    benchmark(_platt_fit_and_predict, scores, labels, predict_batch)


def test_bench_platt_large(benchmark):
    rng = np.random.default_rng(0)
    scores = rng.standard_normal(100_000).tolist()
    labels = [1 if s > 0 else 0 for s in scores]
    predict_batch = rng.standard_normal(100_000).tolist()
    benchmark(_platt_fit_and_predict, scores, labels, predict_batch)


# ── HITS (#29) ────────────────────────────────────────────────────


def _hits_compute(graph):
    from apps.pipeline.services.hits import compute

    compute(graph)


def test_bench_hits_small(benchmark):
    g = _random_graph(100, avg_out_degree=5, seed=1)
    benchmark(_hits_compute, g)


def test_bench_hits_medium(benchmark):
    g = _random_graph(10_000, avg_out_degree=10, seed=2)
    benchmark(_hits_compute, g)


def test_bench_hits_large(benchmark):
    g = _random_graph(100_000, avg_out_degree=10, seed=3)
    benchmark(_hits_compute, g)


# ── Personalized PageRank (#36) ───────────────────────────────────


def _ppr_compute(graph, seeds):
    from apps.pipeline.services.personalized_pagerank import compute

    compute(graph, seeds=seeds)


def test_bench_ppr_small(benchmark):
    g = _random_graph(100, avg_out_degree=5, seed=1)
    benchmark(_ppr_compute, g, [1, 5, 20])


def test_bench_ppr_medium(benchmark):
    g = _random_graph(10_000, avg_out_degree=10, seed=2)
    benchmark(_ppr_compute, g, list(range(0, 100, 10)))


def test_bench_ppr_large(benchmark):
    g = _random_graph(100_000, avg_out_degree=10, seed=3)
    benchmark(_ppr_compute, g, list(range(0, 1000, 50)))


# ── TrustRank (#30) ───────────────────────────────────────────────


def _trustrank_compute(graph, seeds):
    from apps.pipeline.services.trustrank import compute

    compute(graph, trusted_seeds=seeds)


def test_bench_trustrank_small(benchmark):
    g = _random_graph(100, avg_out_degree=5, seed=1)
    benchmark(_trustrank_compute, g, [1, 5, 20])


def test_bench_trustrank_medium(benchmark):
    g = _random_graph(10_000, avg_out_degree=10, seed=2)
    benchmark(_trustrank_compute, g, list(range(0, 100, 10)))


def test_bench_trustrank_large(benchmark):
    g = _random_graph(100_000, avg_out_degree=10, seed=3)
    benchmark(_trustrank_compute, g, list(range(0, 1000, 50)))


# ── Auto-Seeder (#51) ─────────────────────────────────────────────


def _auto_seeder(graph):
    from apps.pipeline.services.trustrank_auto_seeder import pick_seeds

    pick_seeds(graph, seed_count_k=20)


def test_bench_auto_seeder_small(benchmark):
    g = _random_graph(100, avg_out_degree=5, seed=1)
    benchmark(_auto_seeder, g)


def test_bench_auto_seeder_medium(benchmark):
    g = _random_graph(10_000, avg_out_degree=10, seed=2)
    benchmark(_auto_seeder, g)


def test_bench_auto_seeder_large(benchmark):
    g = _random_graph(100_000, avg_out_degree=10, seed=3)
    benchmark(_auto_seeder, g)
