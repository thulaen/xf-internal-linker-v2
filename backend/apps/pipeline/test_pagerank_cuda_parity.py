"""Parity tests for the CUDA random-walk kernels (masterplan Group C.6).

Plain-English purpose: every CUDA kernel in
``apps.pipeline.services.pagerank_cuda`` must produce the same
numerical output as the existing C++ kernel in
``backend/extensions/pagerank.cpp``. These tests prove that with
synthetic data — no DB, no fixtures, no real corpus.

Tolerance: ``abs ≤ 1e-5`` OR ``rel ≤ 1e-6``, whichever is looser.
Different summation order on the GPU shifts individual ranks by ~1e-7;
the threshold absorbs that without hiding real bugs.

Skipping rule: tests skip cleanly when cuPy / CUDA aren't installed,
so the suite still passes on a CPU-only laptop. CI gates on a
GPU-available worker (when one exists) will exercise the real path.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from apps.pipeline.services import pagerank_cuda


def _has_cuda() -> bool:
    return pagerank_cuda.cuda_random_walk_available()


pytestmark = pytest.mark.skipif(
    not _has_cuda(),
    reason="cuPy / CUDA not available — parity test only runs on GPU hosts",
)


# ────────────────────────────────────────────────────────────────────
# Fixtures: deterministic synthetic graphs at multiple sizes / shapes
# ────────────────────────────────────────────────────────────────────


def _random_csr(n: int, density: float = 0.05, seed: int = 42):
    """Return ``(indptr, indices, data, dangling_mask)`` for a random sparse graph.

    Edge weights are uniform in [0, 1]. Each row's outgoing weights
    are normalised to sum to 1.0 (or the row is dangling). Mirrors
    the convention the C++ kernel expects.
    """
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


def _complete_graph_csr(n: int):
    """Dense, symmetric, fully-connected (no self-loops) — worst-case density."""
    rows, cols = [], []
    for r in range(n):
        for c in range(n):
            if r == c:
                continue
            rows.append(r)
            cols.append(c)
    weight_per_edge = 1.0 / max(1, n - 1)
    matrix = sp.csr_matrix(
        (
            np.full(len(rows), weight_per_edge, dtype=np.float64),
            (np.array(rows, dtype=np.int32), np.array(cols, dtype=np.int32)),
        ),
        shape=(n, n),
    )
    indptr = matrix.indptr.astype(np.int32)
    indices = matrix.indices.astype(np.int32)
    data = matrix.data.astype(np.float64)
    dangling = np.zeros(n, dtype=np.bool_)
    return indptr, indices, data, dangling


def _disconnected_components_csr(n_per_component: int, n_components: int):
    """N small chains (component k is a -> a+1 -> ... -> a+k-1)."""
    rows, cols, data = [], [], []
    for c in range(n_components):
        offset = c * n_per_component
        for i in range(n_per_component - 1):
            rows.append(offset + i)
            cols.append(offset + i + 1)
            data.append(1.0)
    n = n_per_component * n_components
    matrix = sp.csr_matrix(
        (
            np.array(data, dtype=np.float64),
            (np.array(rows, dtype=np.int32), np.array(cols, dtype=np.int32)),
        ),
        shape=(n, n),
    )
    indptr = matrix.indptr.astype(np.int32)
    indices = matrix.indices.astype(np.int32)
    out_data = matrix.data.astype(np.float64)
    dangling = np.zeros(n, dtype=np.bool_)
    for row in range(n):
        if indptr[row] == indptr[row + 1]:
            dangling[row] = True
    return indptr, indices, out_data, dangling


def _assert_close(cpu: np.ndarray, gpu: np.ndarray, *, label: str = ""):
    """Pass if abs ≤ 1e-5 OR rel ≤ 1e-6 elementwise. Loose union, not intersection."""
    if cpu.shape != gpu.shape:
        pytest.fail(f"{label}: shape mismatch cpu={cpu.shape} gpu={gpu.shape}")
    if cpu.size == 0:
        return
    abs_diff = np.abs(cpu - gpu)
    abs_tol = 1e-5
    # Avoid divide-by-zero on tiny CPU values
    denom = np.maximum(np.abs(cpu), 1e-12)
    rel_diff = abs_diff / denom
    rel_tol = 1e-6
    fails = (abs_diff > abs_tol) & (rel_diff > rel_tol)
    if fails.any():
        worst_idx = int(abs_diff.argmax())
        pytest.fail(
            f"{label}: parity failed at idx={worst_idx} "
            f"cpu={cpu[worst_idx]:.6e} gpu={gpu[worst_idx]:.6e} "
            f"abs_diff={abs_diff[worst_idx]:.3e} rel_diff={rel_diff[worst_idx]:.3e}"
        )


def _assert_top_100_stable(cpu: np.ndarray, gpu: np.ndarray, *, label: str = ""):
    """Top-100 rank order must not swap between CPU and GPU."""
    if cpu.size == 0:
        return
    k = min(100, cpu.size)
    cpu_top = set(np.argsort(-cpu)[:k].tolist())
    gpu_top = set(np.argsort(-gpu)[:k].tolist())
    if cpu_top != gpu_top:
        pytest.fail(
            f"{label}: top-{k} membership differs. "
            f"cpu_only={sorted(cpu_top - gpu_top)} "
            f"gpu_only={sorted(gpu_top - cpu_top)}"
        )


# ────────────────────────────────────────────────────────────────────
# pagerank_step parity
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [100, 1_000])
def test_pagerank_step_random_parity(n):
    indptr, indices, data, dangling = _random_csr(n)
    ranks = np.full(n, 1.0 / n, dtype=np.float64)
    damping = 0.15  # teleport probability

    from extensions import pagerank as kernel

    cpu_ranks, cpu_delta = kernel.pagerank_step(
        indptr, indices, data, ranks, dangling, damping, n
    )
    gpu_ranks, gpu_delta = pagerank_cuda.pagerank_step_cuda(
        indptr, indices, data, ranks, dangling, damping, n
    )
    _assert_close(cpu_ranks, gpu_ranks, label=f"pagerank n={n} ranks")
    assert abs(cpu_delta - gpu_delta) < 1e-6
    _assert_top_100_stable(cpu_ranks, gpu_ranks, label=f"pagerank n={n} top100")


def test_pagerank_step_empty_graph():
    """Zero-node graph — both kernels return empty + zero delta."""
    indptr = np.array([0], dtype=np.int32)
    indices = np.array([], dtype=np.int32)
    data = np.array([], dtype=np.float64)
    ranks = np.array([], dtype=np.float64)
    dangling = np.array([], dtype=np.bool_)

    gpu_ranks, gpu_delta = pagerank_cuda.pagerank_step_cuda(
        indptr, indices, data, ranks, dangling, 0.15, 0
    )
    assert gpu_ranks.size == 0
    assert gpu_delta == 0.0


def test_pagerank_step_single_node():
    """One node, no edges — fully dangling, all teleport mass lands on it."""
    indptr = np.array([0, 0], dtype=np.int32)
    indices = np.array([], dtype=np.int32)
    data = np.array([], dtype=np.float64)
    ranks = np.array([1.0], dtype=np.float64)
    dangling = np.array([True], dtype=np.bool_)

    from extensions import pagerank as kernel

    cpu_ranks, cpu_delta = kernel.pagerank_step(
        indptr, indices, data, ranks, dangling, 0.15, 1
    )
    gpu_ranks, gpu_delta = pagerank_cuda.pagerank_step_cuda(
        indptr, indices, data, ranks, dangling, 0.15, 1
    )
    _assert_close(cpu_ranks, gpu_ranks, label="pagerank single node")
    assert abs(cpu_delta - gpu_delta) < 1e-6


def test_pagerank_step_complete_graph_small():
    n = 32
    indptr, indices, data, dangling = _complete_graph_csr(n)
    ranks = np.full(n, 1.0 / n, dtype=np.float64)

    from extensions import pagerank as kernel

    cpu_ranks, _ = kernel.pagerank_step(indptr, indices, data, ranks, dangling, 0.15, n)
    gpu_ranks, _ = pagerank_cuda.pagerank_step_cuda(
        indptr, indices, data, ranks, dangling, 0.15, n
    )
    _assert_close(cpu_ranks, gpu_ranks, label="pagerank complete K_32")


def test_pagerank_step_disconnected_components():
    indptr, indices, data, dangling = _disconnected_components_csr(20, 5)
    n = indptr.shape[0] - 1
    ranks = np.full(n, 1.0 / n, dtype=np.float64)

    from extensions import pagerank as kernel

    cpu_ranks, _ = kernel.pagerank_step(indptr, indices, data, ranks, dangling, 0.15, n)
    gpu_ranks, _ = pagerank_cuda.pagerank_step_cuda(
        indptr, indices, data, ranks, dangling, 0.15, n
    )
    _assert_close(cpu_ranks, gpu_ranks, label="pagerank disconnected")


def test_pagerank_step_heavy_dangling_mass():
    n = 200
    indptr, indices, data, _ = _random_csr(n, density=0.01)
    # Force 60 % of nodes to be dangling
    dangling = np.zeros(n, dtype=np.bool_)
    dangling[: int(n * 0.6)] = True
    ranks = np.full(n, 1.0 / n, dtype=np.float64)

    from extensions import pagerank as kernel

    cpu_ranks, _ = kernel.pagerank_step(indptr, indices, data, ranks, dangling, 0.15, n)
    gpu_ranks, _ = pagerank_cuda.pagerank_step_cuda(
        indptr, indices, data, ranks, dangling, 0.15, n
    )
    _assert_close(cpu_ranks, gpu_ranks, label="pagerank heavy dangling")


# ────────────────────────────────────────────────────────────────────
# personalized_pagerank_step parity
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [100, 1_000])
def test_personalized_pagerank_step_random_parity(n):
    indptr, indices, data, dangling = _random_csr(n)
    ranks = np.full(n, 1.0 / n, dtype=np.float64)
    # Personalisation: top 5 % of nodes get all the teleport mass.
    personalization = np.zeros(n, dtype=np.float64)
    seed_count = max(1, n // 20)
    personalization[:seed_count] = 1.0 / seed_count
    damping = 0.15

    from extensions import pagerank as kernel

    cpu_ranks, cpu_delta = kernel.personalized_pagerank_step(
        indptr, indices, data, ranks, dangling, personalization, damping, n
    )
    gpu_ranks, gpu_delta = pagerank_cuda.personalized_pagerank_step_cuda(
        indptr, indices, data, ranks, dangling, personalization, damping, n
    )
    _assert_close(cpu_ranks, gpu_ranks, label=f"ppr n={n} ranks")
    assert abs(cpu_delta - gpu_delta) < 1e-6
    _assert_top_100_stable(cpu_ranks, gpu_ranks, label=f"ppr n={n} top100")


# ────────────────────────────────────────────────────────────────────
# hits_step parity
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [100, 1_000])
def test_hits_step_random_parity(n):
    indptr, indices, data, _ = _random_csr(n)
    authority = np.full(n, 1.0 / n, dtype=np.float64)
    hub = np.full(n, 1.0 / n, dtype=np.float64)

    from extensions import pagerank as kernel

    cpu_authority, cpu_hub = kernel.hits_step(
        indptr, indices, data, authority, hub, n
    )
    gpu_authority, gpu_hub = pagerank_cuda.hits_step_cuda(
        indptr, indices, data, authority, hub, n
    )
    _assert_close(cpu_authority, gpu_authority, label=f"hits n={n} authority")
    _assert_close(cpu_hub, gpu_hub, label=f"hits n={n} hub")
    _assert_top_100_stable(
        cpu_authority, gpu_authority, label=f"hits n={n} authority top100"
    )
    _assert_top_100_stable(cpu_hub, gpu_hub, label=f"hits n={n} hub top100")


def test_hits_step_empty_graph():
    indptr = np.array([0], dtype=np.int32)
    indices = np.array([], dtype=np.int32)
    data = np.array([], dtype=np.float64)
    authority = np.array([], dtype=np.float64)
    hub = np.array([], dtype=np.float64)

    gpu_authority, gpu_hub = pagerank_cuda.hits_step_cuda(
        indptr, indices, data, authority, hub, 0
    )
    assert gpu_authority.size == 0
    assert gpu_hub.size == 0
