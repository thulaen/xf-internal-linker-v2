"""Benchmarks for miscellaneous C++ extensions (strpool, feedrerank, pulse_metrics)."""

import numpy as np


def _import_strpool():
    import strpool
    return strpool


def _import_feedrerank():
    import feedrerank
    return feedrerank


def _import_pulse_metrics():
    import pulse_metrics
    return pulse_metrics


# ── String Pool ─────────────────────────────────────────────────


def test_bench_strpool_intern_small(benchmark):
    sp = _import_strpool()

    def run():
        pool = sp.StringPool()
        for i in range(1_000):
            pool.intern(f"token_{i}")
        return pool

    benchmark(run)


def test_bench_strpool_intern_medium(benchmark):
    sp = _import_strpool()

    def run():
        pool = sp.StringPool()
        for i in range(100_000):
            pool.intern(f"token_{i}")
        return pool

    benchmark(run)


# ── Feed Rerank ─────────────────────────────────────────────────


def test_bench_rerank_factors_small(benchmark):
    fr = _import_feedrerank()
    n = 100
    successes = np.random.default_rng(42).integers(0, 100, size=n).astype(np.int32)
    totals = np.random.default_rng(43).integers(1, 200, size=n).astype(np.int32)
    benchmark(fr.calculate_rerank_factors_batch,
              successes, totals, 10000, 1.0, 1.0, 0.3, 0.1)


def test_bench_rerank_factors_medium(benchmark):
    fr = _import_feedrerank()
    n = 5_000
    successes = np.random.default_rng(42).integers(0, 100, size=n).astype(np.int32)
    totals = np.random.default_rng(43).integers(1, 200, size=n).astype(np.int32)
    benchmark(fr.calculate_rerank_factors_batch,
              successes, totals, 10000, 1.0, 1.0, 0.3, 0.1)


def test_bench_rerank_factors_large(benchmark):
    fr = _import_feedrerank()
    n = 50_000
    successes = np.random.default_rng(42).integers(0, 100, size=n).astype(np.int32)
    totals = np.random.default_rng(43).integers(1, 200, size=n).astype(np.int32)
    benchmark(fr.calculate_rerank_factors_batch,
              successes, totals, 10000, 1.0, 1.0, 0.3, 0.1)


def test_bench_mmr_scores_small(benchmark):
    fr = _import_feedrerank()
    rng = np.random.default_rng(42)
    n_cand, n_sel, dim = 50, 10, 128
    relevance = rng.standard_normal(n_cand)
    candidates = rng.standard_normal((n_cand, dim))
    selected = rng.standard_normal((n_sel, dim))
    benchmark(fr.calculate_mmr_scores_batch,
              relevance, candidates, selected, 0.7)


def test_bench_mmr_scores_medium(benchmark):
    fr = _import_feedrerank()
    rng = np.random.default_rng(42)
    n_cand, n_sel, dim = 500, 50, 384
    relevance = rng.standard_normal(n_cand)
    candidates = rng.standard_normal((n_cand, dim))
    selected = rng.standard_normal((n_sel, dim))
    benchmark(fr.calculate_mmr_scores_batch,
              relevance, candidates, selected, 0.7)


# ── Pulse Metrics ───────────────────────────────────────────────


def test_bench_pulse_push(benchmark):
    pm = _import_pulse_metrics()
    ts = 1_000_000.0

    def push_batch():
        nonlocal ts
        for _ in range(100):
            pm.push_event(ts, 1, 12.5, 100)
            ts += 60.0

    benchmark(push_batch)


def test_bench_pulse_summary(benchmark):
    pm = _import_pulse_metrics()
    ts = 1_000_000.0
    for i in range(1000):
        pm.push_event(ts, i % 4, 10.0 + i, i)
        ts += 3.6
    benchmark(pm.get_summary)
