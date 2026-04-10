"""Benchmarks for embedding-related C++ extensions (l2norm)."""

import numpy as np


def _import_l2norm():
    import l2norm

    return l2norm


# ── L2 Norm 1D ──────────────────────────────────────────────────


def test_bench_l2norm_1d_small(benchmark):
    l2norm = _import_l2norm()
    data = np.random.default_rng(42).standard_normal(128).astype(np.float32)
    benchmark(l2norm.normalize_l2, data.copy())


def test_bench_l2norm_1d_medium(benchmark):
    l2norm = _import_l2norm()
    data = np.random.default_rng(42).standard_normal(384).astype(np.float32)
    benchmark(l2norm.normalize_l2, data.copy())


def test_bench_l2norm_1d_large(benchmark):
    l2norm = _import_l2norm()
    data = np.random.default_rng(42).standard_normal(1536).astype(np.float32)
    benchmark(l2norm.normalize_l2, data.copy())


# ── L2 Norm Batch ───────────────────────────────────────────────


def test_bench_l2norm_batch_small(benchmark, small_embeddings):
    l2norm = _import_l2norm()
    benchmark(l2norm.normalize_l2_batch, small_embeddings.copy())


def test_bench_l2norm_batch_medium(benchmark, medium_embeddings):
    l2norm = _import_l2norm()
    benchmark(l2norm.normalize_l2_batch, medium_embeddings.copy())


def test_bench_l2norm_batch_large(benchmark, large_embeddings):
    l2norm = _import_l2norm()
    benchmark(l2norm.normalize_l2_batch, large_embeddings.copy())
