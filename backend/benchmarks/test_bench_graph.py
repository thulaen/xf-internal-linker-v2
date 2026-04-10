"""Benchmarks for graph-related C++ extensions (linkparse, pagerank, inv_index)."""

import numpy as np


def _import_linkparse():
    import linkparse

    return linkparse


def _import_pagerank():
    import pagerank

    return pagerank


def _import_inv_index():
    import inv_index

    return inv_index


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


# ── Inverted Index ──────────────────────────────────────────────


def test_bench_inv_index_build_small(benchmark):
    inv = _import_inv_index()

    def build():
        idx = inv.InvertedIndex()
        rng = np.random.default_rng(42)
        for doc_id in range(100):
            tokens = rng.integers(0, 10000, size=50).tolist()
            idx.add_document(doc_id, tokens)
        return idx

    benchmark(build)


def test_bench_inv_index_build_medium(benchmark):
    inv = _import_inv_index()

    def build():
        idx = inv.InvertedIndex()
        rng = np.random.default_rng(42)
        for doc_id in range(10_000):
            tokens = rng.integers(0, 10000, size=50).tolist()
            idx.add_document(doc_id, tokens)
        return idx

    benchmark(build)


def test_bench_inv_index_search(benchmark):
    inv = _import_inv_index()
    idx = inv.InvertedIndex()
    rng = np.random.default_rng(42)
    for doc_id in range(10_000):
        tokens = rng.integers(0, 10000, size=50).tolist()
        idx.add_document(doc_id, tokens)
    query = [int(x) for x in rng.integers(0, 10000, size=10)]
    benchmark(idx.search, query, 1.5, 0.75)
