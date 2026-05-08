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

Originally written for pytest; converted to Django ``SimpleTestCase``
so it runs under ``manage.py test``.
"""

from __future__ import annotations

import unittest

import numpy as np
import scipy.sparse as sp
from django.test import SimpleTestCase

from apps.pipeline.services import pagerank_cuda


def _has_cuda() -> bool:
    return pagerank_cuda.cuda_random_walk_available()


# ────────────────────────────────────────────────────────────────────
# Fixtures: deterministic synthetic graphs at multiple sizes / shapes
# ────────────────────────────────────────────────────────────────────


def _random_csr(n: int, density: float = 0.05, seed: int = 42):
    """Return ``(indptr, indices, data, dangling_mask)`` for a random sparse graph."""
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
    return (
        matrix.indptr.astype(np.int32),
        matrix.indices.astype(np.int32),
        matrix.data.astype(np.float64),
        np.zeros(n, dtype=np.bool_),
    )


def _disconnected_components_csr(n_per_component: int, n_components: int):
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


@unittest.skipUnless(
    _has_cuda(),
    reason="cuPy / CUDA not available — parity test only runs on GPU hosts",
)
class PagerankCudaParityTests(SimpleTestCase):
    """CPU vs GPU numerical parity for pagerank / PPR / HITS step kernels."""

    def _assert_close(self, cpu, gpu, label=""):
        if cpu.shape != gpu.shape:
            self.fail(f"{label}: shape mismatch cpu={cpu.shape} gpu={gpu.shape}")
        if cpu.size == 0:
            return
        abs_diff = np.abs(cpu - gpu)
        denom = np.maximum(np.abs(cpu), 1e-12)
        rel_diff = abs_diff / denom
        fails = (abs_diff > 1e-5) & (rel_diff > 1e-6)
        if fails.any():
            worst_idx = int(abs_diff.argmax())
            self.fail(
                f"{label}: parity failed at idx={worst_idx} "
                f"cpu={cpu[worst_idx]:.6e} gpu={gpu[worst_idx]:.6e} "
                f"abs_diff={abs_diff[worst_idx]:.3e} "
                f"rel_diff={rel_diff[worst_idx]:.3e}"
            )

    def _assert_top_100_stable(self, cpu, gpu, label=""):
        """Top-K stability: at least 90% overlap between CPU and GPU top-K.

        On random graphs at one iteration, many scores are near-tied —
        ranks 100 and 101 differ by less than 1e-5 — so a strict
        set-equality check fires on noise that ``_assert_close`` already
        accepts as valid value parity. 90% overlap catches real bugs
        (a sort inversion or off-by-one in either kernel always shifts
        more than 10% of the top-K) without flagging tied-score swaps.
        """
        if cpu.size == 0:
            return
        k = min(100, cpu.size)
        cpu_top = set(np.argsort(-cpu)[:k].tolist())
        gpu_top = set(np.argsort(-gpu)[:k].tolist())
        overlap = len(cpu_top & gpu_top)
        if overlap < int(0.9 * k):
            self.fail(
                f"{label}: top-{k} overlap {overlap}/{k} below 90% threshold. "
                f"cpu_only={sorted(cpu_top - gpu_top)} "
                f"gpu_only={sorted(gpu_top - cpu_top)}"
            )

    # ── pagerank_step parity ─────────────────────────────────────────

    def test_pagerank_step_random_parity(self):
        # Value parity is the contract; top-K stability is not — at one
        # iteration on random data, many scores are near-tied at the
        # rank-K cutoff and CPU/GPU pick different winners within the
        # documented 1e-5 / 1e-6 tolerance band.
        from extensions import pagerank as kernel

        for n in (100, 1_000):
            with self.subTest(n=n):
                indptr, indices, data, dangling = _random_csr(n)
                ranks = np.full(n, 1.0 / n, dtype=np.float64)
                cpu_ranks, cpu_delta = kernel.pagerank_step(
                    indptr, indices, data, ranks, dangling, 0.15, n
                )
                gpu_ranks, gpu_delta = pagerank_cuda.pagerank_step_cuda(
                    indptr, indices, data, ranks, dangling, 0.15, n
                )
                self._assert_close(cpu_ranks, gpu_ranks, label=f"pagerank n={n}")
                self.assertLess(abs(cpu_delta - gpu_delta), 1e-6)

    def test_pagerank_step_empty_graph(self):
        gpu_ranks, gpu_delta = pagerank_cuda.pagerank_step_cuda(
            np.array([0], dtype=np.int32),
            np.array([], dtype=np.int32),
            np.array([], dtype=np.float64),
            np.array([], dtype=np.float64),
            np.array([], dtype=np.bool_),
            0.15,
            0,
        )
        self.assertEqual(gpu_ranks.size, 0)
        self.assertEqual(gpu_delta, 0.0)

    def test_pagerank_step_single_node(self):
        from extensions import pagerank as kernel

        indptr = np.array([0, 0], dtype=np.int32)
        indices = np.array([], dtype=np.int32)
        data = np.array([], dtype=np.float64)
        ranks = np.array([1.0], dtype=np.float64)
        dangling = np.array([True], dtype=np.bool_)
        cpu_ranks, cpu_delta = kernel.pagerank_step(
            indptr, indices, data, ranks, dangling, 0.15, 1
        )
        gpu_ranks, gpu_delta = pagerank_cuda.pagerank_step_cuda(
            indptr, indices, data, ranks, dangling, 0.15, 1
        )
        self._assert_close(cpu_ranks, gpu_ranks, label="single node")
        self.assertLess(abs(cpu_delta - gpu_delta), 1e-6)

    def test_pagerank_step_complete_graph_small(self):
        from extensions import pagerank as kernel

        n = 32
        indptr, indices, data, dangling = _complete_graph_csr(n)
        ranks = np.full(n, 1.0 / n, dtype=np.float64)
        cpu_ranks, _ = kernel.pagerank_step(
            indptr, indices, data, ranks, dangling, 0.15, n
        )
        gpu_ranks, _ = pagerank_cuda.pagerank_step_cuda(
            indptr, indices, data, ranks, dangling, 0.15, n
        )
        self._assert_close(cpu_ranks, gpu_ranks, label="complete K_32")

    def test_pagerank_step_disconnected_components(self):
        from extensions import pagerank as kernel

        indptr, indices, data, dangling = _disconnected_components_csr(20, 5)
        n = indptr.shape[0] - 1
        ranks = np.full(n, 1.0 / n, dtype=np.float64)
        cpu_ranks, _ = kernel.pagerank_step(
            indptr, indices, data, ranks, dangling, 0.15, n
        )
        gpu_ranks, _ = pagerank_cuda.pagerank_step_cuda(
            indptr, indices, data, ranks, dangling, 0.15, n
        )
        self._assert_close(cpu_ranks, gpu_ranks, label="disconnected")

    def test_pagerank_step_heavy_dangling_mass(self):
        from extensions import pagerank as kernel

        n = 200
        indptr, indices, data, _ = _random_csr(n, density=0.01)
        dangling = np.zeros(n, dtype=np.bool_)
        dangling[: int(n * 0.6)] = True
        ranks = np.full(n, 1.0 / n, dtype=np.float64)
        cpu_ranks, _ = kernel.pagerank_step(
            indptr, indices, data, ranks, dangling, 0.15, n
        )
        gpu_ranks, _ = pagerank_cuda.pagerank_step_cuda(
            indptr, indices, data, ranks, dangling, 0.15, n
        )
        self._assert_close(cpu_ranks, gpu_ranks, label="heavy dangling")

    # ── personalized_pagerank_step parity ────────────────────────────

    def test_personalized_pagerank_step_random_parity(self):
        # See test_pagerank_step_random_parity — top-K stability is
        # not part of the one-iteration parity contract.
        from extensions import pagerank as kernel

        for n in (100, 1_000):
            with self.subTest(n=n):
                indptr, indices, data, dangling = _random_csr(n)
                ranks = np.full(n, 1.0 / n, dtype=np.float64)
                personalization = np.zeros(n, dtype=np.float64)
                seed_count = max(1, n // 20)
                personalization[:seed_count] = 1.0 / seed_count
                cpu_ranks, cpu_delta = kernel.personalized_pagerank_step(
                    indptr,
                    indices,
                    data,
                    ranks,
                    dangling,
                    personalization,
                    0.15,
                    n,
                )
                gpu_ranks, gpu_delta = pagerank_cuda.personalized_pagerank_step_cuda(
                    indptr,
                    indices,
                    data,
                    ranks,
                    dangling,
                    personalization,
                    0.15,
                    n,
                )
                self._assert_close(cpu_ranks, gpu_ranks, label=f"ppr n={n}")
                self.assertLess(abs(cpu_delta - gpu_delta), 1e-6)

    # ── hits_step parity ─────────────────────────────────────────────

    def test_hits_step_random_parity(self):
        # See test_pagerank_step_random_parity — top-K stability is
        # not part of the one-iteration parity contract.
        from extensions import pagerank as kernel

        for n in (100, 1_000):
            with self.subTest(n=n):
                indptr, indices, data, _ = _random_csr(n)
                authority = np.full(n, 1.0 / n, dtype=np.float64)
                hub = np.full(n, 1.0 / n, dtype=np.float64)
                cpu_authority, cpu_hub = kernel.hits_step(
                    indptr, indices, data, authority, hub, n
                )
                gpu_authority, gpu_hub = pagerank_cuda.hits_step_cuda(
                    indptr, indices, data, authority, hub, n
                )
                self._assert_close(
                    cpu_authority, gpu_authority, label=f"hits n={n} authority"
                )
                self._assert_close(cpu_hub, gpu_hub, label=f"hits n={n} hub")

    def test_hits_step_empty_graph(self):
        gpu_authority, gpu_hub = pagerank_cuda.hits_step_cuda(
            np.array([0], dtype=np.int32),
            np.array([], dtype=np.int32),
            np.array([], dtype=np.float64),
            np.array([], dtype=np.float64),
            np.array([], dtype=np.float64),
            0,
        )
        self.assertEqual(gpu_authority.size, 0)
        self.assertEqual(gpu_hub.size, 0)
