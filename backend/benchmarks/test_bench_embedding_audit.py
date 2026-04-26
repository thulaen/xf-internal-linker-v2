"""Benchmarks for the fortnightly audit scorer (plan Part 3, FR-231).

The scan function walks every ContentItem row; for the benchmark we drive its
inner classifier (norm check + dim check) directly with synthetic vectors so
the number measures algorithm cost without DB I/O.

Three input sizes: 100 / 1 000 / 10 000 items.
"""

from __future__ import annotations

import numpy as np


def _scan_inner_loop(
    vectors: np.ndarray, target_dim: int, norm_tolerance: float
) -> dict[str, int]:
    """Replicates the hot inner path of ``scan_embedding_health`` (norm + dim gate).

    Kept here as a pure function so the benchmark does not need a populated DB.
    Matches the production classifier exactly (see embedding_audit.py).
    """
    counts = {"ok": 0, "null": 0, "wrong_dim": 0, "drift_norm": 0}
    for v in vectors:
        if v is None:
            counts["null"] += 1
            continue
        if v.shape[0] != target_dim:
            counts["wrong_dim"] += 1
            continue
        n = float(np.linalg.norm(v))
        if abs(n - 1.0) > norm_tolerance:
            counts["drift_norm"] += 1
            continue
        counts["ok"] += 1
    return counts


def _make_vectors(n: int, dim: int) -> np.ndarray:
    rng = np.random.default_rng(7)
    mat = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / norms


def test_bench_audit_small(benchmark):
    vectors = _make_vectors(100, 1024)
    benchmark(_scan_inner_loop, vectors, 1024, 0.02)


def test_bench_audit_medium(benchmark):
    vectors = _make_vectors(1_000, 1024)
    benchmark(_scan_inner_loop, vectors, 1024, 0.02)


def test_bench_audit_large(benchmark):
    vectors = _make_vectors(10_000, 1024)
    benchmark(_scan_inner_loop, vectors, 1024, 0.02)
