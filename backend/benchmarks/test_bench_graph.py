"""Benchmarks for graph-related C++ extensions (linkparse, pagerank)."""

import numpy as np


def _import_linkparse():
    import linkparse

    return linkparse


def _import_pagerank():
    import pagerank

    return pagerank


# ── Link Parsing ────────────────────────────────────────────────


def test_bench_linkparse_small(benchmark, bbcode_small):
    linkparse = _import_linkparse()
    benchmark(linkparse.find_urls, bbcode_small)


def test_bench_linkparse_medium(benchmark, bbcode_medium):
    linkparse = _import_linkparse()
    benchmark(linkparse.find_urls, bbcode_medium)


def test_bench_linkparse_large(benchmark, bbcode_large):
    linkparse = _import_linkparse()
    benchmark(linkparse.find_urls, bbcode_large)


# ── PageRank ────────────────────────────────────────────────────


def _make_csr_graph(nodes, avg_edges=5, seed=42):
    """Build a sparse CSR graph for pagerank benchmarks."""
    rng = np.random.default_rng(seed)
    indptr = [0]
    indices_list = []
    data_list = []
    dangling = np.zeros(nodes, dtype=bool)

    for row in range(nodes):
        deg = rng.integers(0, avg_edges * 2 + 1)
        if deg == 0:
            dangling[row] = True
        neighbors = rng.integers(0, nodes, size=deg)
        weight = 1.0 / max(deg, 1)
        indices_list.extend(neighbors.tolist())
        data_list.extend([weight] * deg)
        indptr.append(len(indices_list))

    return (
        np.array(indptr, dtype=np.int32),
        np.array(indices_list, dtype=np.int32),
        np.array(data_list, dtype=np.float64),
        np.full(nodes, 1.0 / nodes, dtype=np.float64),
        dangling,
    )


def test_bench_pagerank_small(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, dangling = _make_csr_graph(100)
    benchmark(pr.pagerank_step, indptr, indices, data, ranks, dangling, 0.85, 100)


def test_bench_pagerank_medium(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, dangling = _make_csr_graph(10_000)
    benchmark(pr.pagerank_step, indptr, indices, data, ranks, dangling, 0.85, 10_000)


def test_bench_pagerank_large(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, dangling = _make_csr_graph(100_000)
    benchmark(pr.pagerank_step, indptr, indices, data, ranks, dangling, 0.85, 100_000)


# ── Personalized PageRank (pick #36 / pick #30 — Phase 5a kernel) ───
#
# Same fixture builder as ``pagerank_step`` benchmarks; we add a
# personalisation vector concentrated on a small seed set so the
# benchmark exercises a realistic seeded PPR run rather than the
# uniform 1/N degenerate case.


def _seed_personalization(nodes: int, seed_count: int = 5) -> np.ndarray:
    p = np.zeros(nodes, dtype=np.float64)
    seed_idx = np.linspace(0, nodes - 1, num=min(seed_count, nodes), dtype=int)
    p[seed_idx] = 1.0 / len(seed_idx)
    return p


def test_bench_personalized_pagerank_small(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, dangling = _make_csr_graph(100)
    p = _seed_personalization(100)
    benchmark(
        pr.personalized_pagerank_step,
        indptr, indices, data, ranks, dangling, p, 0.15, 100,
    )


def test_bench_personalized_pagerank_medium(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, dangling = _make_csr_graph(10_000)
    p = _seed_personalization(10_000)
    benchmark(
        pr.personalized_pagerank_step,
        indptr, indices, data, ranks, dangling, p, 0.15, 10_000,
    )


def test_bench_personalized_pagerank_large(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, dangling = _make_csr_graph(100_000)
    p = _seed_personalization(100_000)
    benchmark(
        pr.personalized_pagerank_step,
        indptr, indices, data, ranks, dangling, p, 0.15, 100_000,
    )


# ── HITS (pick #29 — Phase 5a kernel) ──────────────────────────────


def test_bench_hits_small(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, _ = _make_csr_graph(100)
    authority = np.full(100, 1.0 / 100, dtype=np.float64)
    hub = authority.copy()
    benchmark(pr.hits_step, indptr, indices, data, authority, hub, 100)


def test_bench_hits_medium(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, _ = _make_csr_graph(10_000)
    authority = np.full(10_000, 1.0 / 10_000, dtype=np.float64)
    hub = authority.copy()
    benchmark(pr.hits_step, indptr, indices, data, authority, hub, 10_000)


def test_bench_hits_large(benchmark):
    pr = _import_pagerank()
    indptr, indices, data, ranks, _ = _make_csr_graph(100_000)
    authority = np.full(100_000, 1.0 / 100_000, dtype=np.float64)
    hub = authority.copy()
    benchmark(pr.hits_step, indptr, indices, data, authority, hub, 100_000)
