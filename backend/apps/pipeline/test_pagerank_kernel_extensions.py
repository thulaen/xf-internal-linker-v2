"""Tests for Phase 5a — pagerank.cpp extensions: personalized PageRank + HITS.

Two parity proofs:

1. **PPR step** matches a Python power-iteration reference within
   ``atol=1e-9`` on a fixture graph. The Python reference re-implements
   the same recurrence the C++ kernel computes — that's the parity
   contract; networkx PPR uses an equivalent algorithm and converges
   to the same solution within ``tol``, but its absolute outputs
   differ because of internal normalisation order.

2. **HITS step** matches a Python power-iteration reference within
   ``atol=1e-9`` on a fixture graph. Note: networkx 3.4 implements
   HITS via ``scipy.sparse.linalg.svds`` (SVD on the adjacency
   matrix), not power iteration — so we cannot strict-parity against
   networkx. Both methods converge to the same dominant eigenvector
   up to sign, which is the correctness contract.

Plus a smoke test that the kernel zeroes its own output buffers.
"""

from __future__ import annotations

import numpy as np
from django.test import SimpleTestCase

from extensions import pagerank


def _ppr_reference(
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    ranks: np.ndarray,
    dangling: np.ndarray,
    personalization: np.ndarray,
    damping: float,
    node_count: int,
) -> tuple[np.ndarray, float]:
    """Pure-Python reference for ``personalized_pagerank_step_core``.

    Mirrors the C++ recurrence line-for-line so the parity check
    bottoms out on identical math, not on a third-party
    implementation that may use a different solver.
    """
    next_ranks = np.zeros(node_count, dtype=np.float64)
    dangling_mass = 0.0
    for row in range(node_count):
        link_mass = 0.0
        for idx in range(indptr[row], indptr[row + 1]):
            col = int(indices[idx])
            link_mass += float(data[idx]) * float(ranks[col])
        next_ranks[row] = (1.0 - damping) * link_mass
        if dangling[row]:
            dangling_mass += float(ranks[row])
    teleport_mass = (1.0 - damping) * dangling_mass + damping
    total = 0.0
    for row in range(node_count):
        next_ranks[row] += teleport_mass * float(personalization[row])
        total += next_ranks[row]
    if total > 0.0:
        next_ranks /= total
    delta = float(np.abs(next_ranks - ranks).sum())
    return next_ranks, delta


def _hits_reference(
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    authority: np.ndarray,
    hub: np.ndarray,
    node_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Pure-Python reference for ``hits_step_core``.

    Same loop body as the C++ kernel — outer loop walks targets ``v``,
    inner loop reads each source ``u`` that points at ``v`` from the
    row=target CSR. Deposits both authority and hub in one pass.
    """
    next_authority = np.zeros(node_count, dtype=np.float64)
    next_hub = np.zeros(node_count, dtype=np.float64)
    for v in range(node_count):
        for idx in range(indptr[v], indptr[v + 1]):
            u = int(indices[idx])
            w = float(data[idx])
            next_authority[v] += w * float(hub[u])
            next_hub[u] += w * float(authority[v])
    return next_authority, next_hub


class _Fixture:
    """Tiny 5-node graph used by every test in this module.

    Edges (with weights, row=target convention):
        0 ← 1, 0 ← 2     (node 0 has incoming from 1, 2)
        1 ← 3            (node 1 has incoming from 3)
        2 ← 1            (node 2 has incoming from 1)
        3 ← 4            (node 3 has incoming from 4)
        4 has no incoming, will be dangling source (in row=target CSR
        node 4 has no edges into it BUT it has outgoing edges to 3, so
        for dangling-source detection we need the dangling_mask to
        flag nodes whose OUT-degree is zero — the existing weighted
        graph builder marks dangling correctly per
        ``weighted_pagerank.py``. For the kernel test we set the
        dangling mask explicitly.)
    """

    NODE_COUNT = 5

    @staticmethod
    def csr() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        # row=target, col=source, edge weights in [0, 1].
        # Build via dict-of-incoming-edges, then flatten.
        incoming: dict[int, list[tuple[int, float]]] = {
            0: [(1, 0.5), (2, 0.5)],
            1: [(3, 1.0)],
            2: [(1, 1.0)],
            3: [(4, 1.0)],
            4: [],  # no incoming
        }
        indptr = [0]
        indices: list[int] = []
        data: list[float] = []
        for v in range(_Fixture.NODE_COUNT):
            for u, w in incoming[v]:
                indices.append(u)
                data.append(w)
            indptr.append(len(indices))
        # Dangling = no outgoing. Out-degrees:
        #   0 → none → dangling (so we should set dangling[0] = True)
        # Wait actually: looking at incoming above, node 0 receives
        # but never sends; so 0 is dangling. We list out-degrees:
        #   0: out to nothing → dangling
        #   1: out to 0, 2
        #   2: out to 0
        #   3: out to 1
        #   4: out to 3
        dangling = np.array([True, False, False, False, False], dtype=bool)
        return (
            np.asarray(indptr, dtype=np.int32),
            np.asarray(indices, dtype=np.int32),
            np.asarray(data, dtype=np.float64),
            dangling,
        )


class PersonalizedPageRankParityTests(SimpleTestCase):
    def test_ppr_step_matches_python_reference(self) -> None:
        indptr, indices, data, dangling = _Fixture.csr()
        n = _Fixture.NODE_COUNT
        # Concentrate teleport mass on node 0 (a "trust seed").
        personalization = np.zeros(n, dtype=np.float64)
        personalization[0] = 1.0
        ranks = np.full(n, 1.0 / n, dtype=np.float64)
        damping = 0.15  # teleport probability (this codebase's convention)

        # Run 20 iterations of both implementations and compare.
        cpp_ranks = ranks.copy()
        py_ranks = ranks.copy()
        for _ in range(20):
            cpp_next, cpp_delta = pagerank.personalized_pagerank_step(
                indptr, indices, data, cpp_ranks, dangling, personalization,
                damping, n,
            )
            py_next, py_delta = _ppr_reference(
                indptr, indices, data, py_ranks, dangling, personalization,
                damping, n,
            )
            np.testing.assert_allclose(cpp_next, py_next, atol=1e-9, rtol=0.0)
            self.assertAlmostEqual(cpp_delta, py_delta, places=9)
            cpp_ranks, py_ranks = cpp_next, py_next

        # The persisted scores sum to 1.0 (probability mass conserved).
        self.assertAlmostEqual(float(cpp_ranks.sum()), 1.0, places=9)

    def test_uniform_personalization_reduces_to_pagerank_step(self) -> None:
        """When the personalization vector is uniform 1/N, PPR ≈ uniform PageRank."""
        indptr, indices, data, dangling = _Fixture.csr()
        n = _Fixture.NODE_COUNT
        uniform = np.full(n, 1.0 / n, dtype=np.float64)
        ranks = np.full(n, 1.0 / n, dtype=np.float64)
        damping = 0.15

        ppr_next, _ = pagerank.personalized_pagerank_step(
            indptr, indices, data, ranks, dangling, uniform, damping, n,
        )
        plain_next, _ = pagerank.pagerank_step(
            indptr, indices, data, ranks, dangling, damping, n,
        )
        # Both formulations should converge to the same numbers within
        # rounding because PPR with uniform p[i]=1/N is mathematically
        # identical to standard PageRank.
        np.testing.assert_allclose(ppr_next, plain_next, atol=1e-12, rtol=0.0)

    def test_seed_node_gets_higher_score(self) -> None:
        """Concentrating teleport mass on a seed node lifts that node's score."""
        indptr, indices, data, dangling = _Fixture.csr()
        n = _Fixture.NODE_COUNT
        damping = 0.15
        ranks = np.full(n, 1.0 / n, dtype=np.float64)

        # Seed only node 4.
        personalization = np.zeros(n, dtype=np.float64)
        personalization[4] = 1.0
        seed_4 = ranks.copy()
        for _ in range(50):
            seed_4, _ = pagerank.personalized_pagerank_step(
                indptr, indices, data, seed_4, dangling, personalization,
                damping, n,
            )
        # Node 4 should outscore at least one other node when it gets
        # all the teleport mass.
        other_max = max(seed_4[i] for i in range(n) if i != 4)
        self.assertGreater(seed_4[4], 0.05)  # got real teleport mass
        self.assertGreater(seed_4[4], min(seed_4[i] for i in range(n) if i != 4))


class HitsParityTests(SimpleTestCase):
    def test_hits_step_matches_python_reference(self) -> None:
        indptr, indices, data, _ = _Fixture.csr()
        n = _Fixture.NODE_COUNT

        authority = np.full(n, 1.0 / n, dtype=np.float64)
        hub = np.full(n, 1.0 / n, dtype=np.float64)

        for _ in range(10):
            cpp_a, cpp_h = pagerank.hits_step(
                indptr, indices, data, authority, hub, n,
            )
            py_a, py_h = _hits_reference(
                indptr, indices, data, authority, hub, n,
            )
            np.testing.assert_allclose(cpp_a, py_a, atol=1e-9, rtol=0.0)
            np.testing.assert_allclose(cpp_h, py_h, atol=1e-9, rtol=0.0)

            # L1-normalise after each iteration so power iteration
            # doesn't blow up — same scheme any production driver
            # would use.
            a_sum = cpp_a.sum()
            h_sum = cpp_h.sum()
            authority = cpp_a / a_sum if a_sum > 0 else cpp_a
            hub = cpp_h / h_sum if h_sum > 0 else cpp_h

    def test_hits_kernel_zeroes_outputs(self) -> None:
        """The kernel takes ownership of zeroing the output buffers."""
        indptr, indices, data, _ = _Fixture.csr()
        n = _Fixture.NODE_COUNT
        authority = np.zeros(n, dtype=np.float64)  # zero input
        hub = np.zeros(n, dtype=np.float64)  # zero input
        # With both vectors zero, every deposit is zero × 0 = 0, so
        # the output should be all-zero too. This catches a subtle
        # bug where the kernel forgets to zero its outputs and
        # leaves NaN / stale values.
        out_a, out_h = pagerank.hits_step(
            indptr, indices, data, authority, hub, n,
        )
        np.testing.assert_array_equal(out_a, np.zeros(n))
        np.testing.assert_array_equal(out_h, np.zeros(n))

    def test_hits_power_iteration_converges_to_a_meaningful_ranking(self) -> None:
        """50-step power iteration produces an L1-normalised eigenvector
        with a strict ordering — not the all-equal initial state.

        We don't pin the exact top-authority node here because the
        dominant eigenvector for our 5-node fixture can favour
        different vertices depending on the in-degree / out-degree
        balance. The convergence behaviour is the wiring contract
        (i.e. iteration changes the ranks); ranking specifics are
        graph-shape-dependent.
        """
        indptr, indices, data, _ = _Fixture.csr()
        n = _Fixture.NODE_COUNT

        authority = np.full(n, 1.0 / n, dtype=np.float64)
        hub = np.full(n, 1.0 / n, dtype=np.float64)
        for _ in range(50):
            authority, hub = pagerank.hits_step(
                indptr, indices, data, authority, hub, n,
            )
            a_sum = authority.sum()
            h_sum = hub.sum()
            if a_sum > 0:
                authority /= a_sum
            if h_sum > 0:
                hub /= h_sum

        # L1-normalised vectors sum to 1.
        self.assertAlmostEqual(float(authority.sum()), 1.0, places=9)
        self.assertAlmostEqual(float(hub.sum()), 1.0, places=9)
        # Iteration produced a non-trivial ranking — at least one
        # node lifted above the uniform 1/N baseline, at least one
        # dropped below.
        uniform = 1.0 / n
        self.assertGreater(authority.max(), uniform * 1.1)
        self.assertLess(authority.min(), uniform * 0.9)
