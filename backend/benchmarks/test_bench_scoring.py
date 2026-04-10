"""Benchmarks for scoring C++ extensions (scoring, simsearch)."""

import numpy as np


def _import_scoring():
    import scoring

    return scoring


def _import_simsearch():
    import simsearch

    return simsearch


# ── Composite Scoring (full batch) ──────────────────────────────


def test_bench_scoring_full_batch_small(benchmark):
    scoring = _import_scoring()
    rng = np.random.default_rng(42)
    components = rng.standard_normal((100, 8)).astype(np.float32)
    weights = rng.standard_normal(8).astype(np.float32)
    silo = rng.standard_normal(100).astype(np.float32)
    benchmark(scoring.calculate_composite_scores_full_batch, components, weights, silo)


def test_bench_scoring_full_batch_medium(benchmark):
    scoring = _import_scoring()
    rng = np.random.default_rng(42)
    components = rng.standard_normal((10_000, 8)).astype(np.float32)
    weights = rng.standard_normal(8).astype(np.float32)
    silo = rng.standard_normal(10_000).astype(np.float32)
    benchmark(scoring.calculate_composite_scores_full_batch, components, weights, silo)


def test_bench_scoring_full_batch_large(benchmark):
    scoring = _import_scoring()
    rng = np.random.default_rng(42)
    components = rng.standard_normal((100_000, 8)).astype(np.float32)
    weights = rng.standard_normal(8).astype(np.float32)
    silo = rng.standard_normal(100_000).astype(np.float32)
    benchmark(scoring.calculate_composite_scores_full_batch, components, weights, silo)


# ── SimSearch (score_and_topk) ──────────────────────────────────


def test_bench_simsearch_small(benchmark, query_embedding):
    simsearch = _import_simsearch()
    rng = np.random.default_rng(43)
    sentences = rng.standard_normal((100, 384)).astype(np.float32)
    candidates = list(range(100))
    benchmark(simsearch.score_and_topk, query_embedding, sentences, candidates, 50)


def test_bench_simsearch_medium(benchmark, query_embedding):
    simsearch = _import_simsearch()
    rng = np.random.default_rng(43)
    sentences = rng.standard_normal((5_000, 384)).astype(np.float32)
    candidates = list(range(5_000))
    benchmark(simsearch.score_and_topk, query_embedding, sentences, candidates, 50)


def test_bench_simsearch_large(benchmark, query_embedding):
    simsearch = _import_simsearch()
    rng = np.random.default_rng(43)
    sentences = rng.standard_normal((50_000, 384)).astype(np.float32)
    candidates = list(range(50_000))
    benchmark(simsearch.score_and_topk, query_embedding, sentences, candidates, 50)
