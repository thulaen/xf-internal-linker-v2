"""Benchmarks for miscellaneous C++ extensions (feedrerank)."""

import numpy as np


def _import_feedrerank():
    import feedrerank

    return feedrerank


# ── Feed Rerank ─────────────────────────────────────────────────


def test_bench_rerank_factors_small(benchmark):
    fr = _import_feedrerank()
    n = 100
    successes = np.random.default_rng(42).integers(0, 100, size=n).astype(np.int32)
    totals = np.random.default_rng(43).integers(1, 200, size=n).astype(np.int32)
    observation_confidences = np.ones(n, dtype=np.float64)
    benchmark(
        fr.calculate_rerank_factors_batch,
        successes,
        totals,
        observation_confidences,
        10000,
        1.0,
        1.0,
        0.3,
        0.1,
    )


def test_bench_rerank_factors_medium(benchmark):
    fr = _import_feedrerank()
    n = 5_000
    successes = np.random.default_rng(42).integers(0, 100, size=n).astype(np.int32)
    totals = np.random.default_rng(43).integers(1, 200, size=n).astype(np.int32)
    observation_confidences = np.ones(n, dtype=np.float64)
    benchmark(
        fr.calculate_rerank_factors_batch,
        successes,
        totals,
        observation_confidences,
        10000,
        1.0,
        1.0,
        0.3,
        0.1,
    )


def test_bench_rerank_factors_large(benchmark):
    fr = _import_feedrerank()
    n = 50_000
    successes = np.random.default_rng(42).integers(0, 100, size=n).astype(np.int32)
    totals = np.random.default_rng(43).integers(1, 200, size=n).astype(np.int32)
    observation_confidences = np.ones(n, dtype=np.float64)
    benchmark(
        fr.calculate_rerank_factors_batch,
        successes,
        totals,
        observation_confidences,
        10000,
        1.0,
        1.0,
        0.3,
        0.1,
    )


def test_bench_mmr_scores_small(benchmark):
    fr = _import_feedrerank()
    rng = np.random.default_rng(42)
    n_cand, n_sel, dim = 50, 10, 128
    relevance = rng.standard_normal(n_cand)
    candidates = rng.standard_normal((n_cand, dim))
    selected = rng.standard_normal((n_sel, dim))
    benchmark(fr.calculate_mmr_scores_batch, relevance, candidates, selected, 0.7)


def test_bench_mmr_scores_medium(benchmark):
    fr = _import_feedrerank()
    rng = np.random.default_rng(42)
    n_cand, n_sel, dim = 500, 50, 384
    relevance = rng.standard_normal(n_cand)
    candidates = rng.standard_normal((n_cand, dim))
    selected = rng.standard_normal((n_sel, dim))
    benchmark(fr.calculate_mmr_scores_batch, relevance, candidates, selected, 0.7)
