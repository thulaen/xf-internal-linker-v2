"""Three-size benchmark for the CUDA random-walk kernels (Group C.7).

Plain-English purpose: prove the CUDA path actually delivers speedup
on the target hardware (RTX 3050 6 GB). Three input sizes per the
mandatory benchmark rule in CLAUDE.md: 1k / 10k / 100k nodes.

The pytest-benchmark output appears on the Performance dashboard at
``/performance`` next to the existing C++ benchmarks so the
operator can compare CPU vs GPU per-iteration cost.

Skipping rule: benchmark skips cleanly when cuPy / CUDA aren't
available. CI runs that exercise the GPU path are gated to a
GPU-equipped worker.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from apps.pipeline.services import pagerank_cuda


pytestmark = pytest.mark.skipif(
    not pagerank_cuda.cuda_random_walk_available(),
    reason="cuPy / CUDA not available — benchmark only runs on GPU hosts",
)


def _make_random_csr(n: int, density: float = 0.005, seed: int = 1234):
    """Sparse random graph with row-normalised weights + dangling mask."""
    rng = np.random.default_rng(seed)
    matrix = sp.random(n, n, density=density, format="csr", random_state=rng)
    matrix.data = matrix.data.astype(np.float64)
    indptr = matrix.indptr.astype(np.int32)
    indices = matrix.indices.astype(np.int32)
    data = matrix.data.copy()

    dangling = np.zeros(n, dtype=np.bool_)
    for row in range(n):
        start = indptr[row]
        end = indptr[row + 1]
        if start == end:
            dangling[row] = True
            continue
        row_sum = data[start:end].sum()
        if row_sum > 0:
            data[start:end] /= row_sum
    return indptr, indices, data, dangling


# ────────────────────────────────────────────────────────────────────
# pagerank_step_cuda — three sizes
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [1_000, 10_000, 100_000])
def test_bench_pagerank_step_cuda(benchmark, n):
    indptr, indices, data, dangling = _make_random_csr(n)
    ranks = np.full(n, 1.0 / n, dtype=np.float64)

    def run_one_step():
        return pagerank_cuda.pagerank_step_cuda(
            indptr, indices, data, ranks, dangling, 0.15, n
        )

    result_ranks, _ = benchmark(run_one_step)
    assert result_ranks.shape == (n,)


# ────────────────────────────────────────────────────────────────────
# personalized_pagerank_step_cuda — three sizes
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [1_000, 10_000, 100_000])
def test_bench_personalized_pagerank_step_cuda(benchmark, n):
    indptr, indices, data, dangling = _make_random_csr(n)
    ranks = np.full(n, 1.0 / n, dtype=np.float64)
    # ~5 % of nodes seeded
    personalization = np.zeros(n, dtype=np.float64)
    seeds = max(1, n // 20)
    personalization[:seeds] = 1.0 / seeds

    def run_one_step():
        return pagerank_cuda.personalized_pagerank_step_cuda(
            indptr, indices, data, ranks, dangling, personalization, 0.15, n
        )

    result_ranks, _ = benchmark(run_one_step)
    assert result_ranks.shape == (n,)


# ────────────────────────────────────────────────────────────────────
# hits_step_cuda — three sizes
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [1_000, 10_000, 100_000])
def test_bench_hits_step_cuda(benchmark, n):
    indptr, indices, data, _ = _make_random_csr(n)
    authority = np.full(n, 1.0 / n, dtype=np.float64)
    hub = np.full(n, 1.0 / n, dtype=np.float64)

    def run_one_step():
        return pagerank_cuda.hits_step_cuda(indptr, indices, data, authority, hub, n)

    result_authority, result_hub = benchmark(run_one_step)
    assert result_authority.shape == (n,)
    assert result_hub.shape == (n,)
