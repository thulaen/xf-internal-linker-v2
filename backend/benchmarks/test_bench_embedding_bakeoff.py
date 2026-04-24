"""Benchmarks for the bake-off scorer (plan Part 4, FR-232).

Exercises the MRR@10 / NDCG@10 / Recall@10 loop on synthetic vector pools at
three scales (100 / 500 / 1 000 positive pairs). No Django / no network —
pure numpy arithmetic.
"""

from __future__ import annotations

import numpy as np


_TOP_K = 10


def _score_bakeoff(
    query_vectors: np.ndarray,
    target_cols: list[int],
    pool_matrix: np.ndarray,
) -> tuple[float, float, float]:
    """Mirrors the hot loop in ``embedding_bakeoff.score_provider``.

    Returns ``(mrr_at_10, ndcg_at_10, recall_at_10)``.
    """
    q_norms = np.linalg.norm(query_vectors, axis=1, keepdims=True)
    q_norms = np.where(q_norms > 0, q_norms, 1.0)
    queries_n = query_vectors / q_norms
    p_norms = np.linalg.norm(pool_matrix, axis=1, keepdims=True)
    p_norms = np.where(p_norms > 0, p_norms, 1.0)
    pool_n = pool_matrix / p_norms
    scores = queries_n @ pool_n.T

    mrr = 0.0
    ndcg = 0.0
    recall = 0
    n = len(target_cols)
    for row_idx, target in enumerate(target_cols):
        row = scores[row_idx]
        order = np.argsort(-row)
        rank = int(np.where(order == target)[0][0]) + 1
        if rank <= _TOP_K:
            mrr += 1.0 / rank
            ndcg += 1.0 / np.log2(rank + 1)
            recall += 1
    return mrr / n, ndcg / n, recall / n


def _make_bakeoff(n: int, dim: int) -> tuple[np.ndarray, list[int], np.ndarray]:
    rng = np.random.default_rng(101)
    queries = rng.standard_normal((n, dim)).astype(np.float32)
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    pool_size = max(n, _TOP_K + 10)
    pool = rng.standard_normal((pool_size, dim)).astype(np.float32)
    pool /= np.linalg.norm(pool, axis=1, keepdims=True)
    # Ensure each query's target is a valid column so metrics have signal.
    targets = [i % pool_size for i in range(n)]
    return queries, targets, pool


def test_bench_bakeoff_small(benchmark):
    queries, targets, pool = _make_bakeoff(100, 1024)
    benchmark(_score_bakeoff, queries, targets, pool)


def test_bench_bakeoff_medium(benchmark):
    queries, targets, pool = _make_bakeoff(500, 1024)
    benchmark(_score_bakeoff, queries, targets, pool)


def test_bench_bakeoff_large(benchmark):
    queries, targets, pool = _make_bakeoff(1_000, 1024)
    benchmark(_score_bakeoff, queries, targets, pool)
