"""Convert a ``networkx.DiGraph`` to the CSR layout the
``backend/extensions/pagerank.cpp`` kernels expect.

The C++ kernels (``pagerank_step``, ``personalized_pagerank_step``,
``hits_step``) all consume the same row=target / col=source CSR
layout that ``apps.pipeline.services.weighted_pagerank.load_weighted_graph``
produces from the database. This module is the equivalent converter
for an in-memory ``networkx.DiGraph`` so the Phase 5b producer
services (``personalized_pagerank`` / ``hits`` / ``trustrank``) can
plug straight into the kernels without rebuilding their graph
plumbing.

Single source of truth for the conversion lives here so a future
fourth caller doesn't have to re-derive the row=target convention
from a stale comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

import networkx as nx
import numpy as np


@dataclass(frozen=True)
class NxCsrGraph:
    """CSR view of a ``networkx.DiGraph`` in the row=target convention.

    All fields share the same node ordering: row index ``i``
    corresponds to ``node_keys[i]``.
    """

    indptr: np.ndarray  # int32[N + 1]
    indices: np.ndarray  # int32[E] — source indices per target row
    data: np.ndarray  # float64[E] — edge weights
    dangling: np.ndarray  # bool[N] — True iff node has zero outgoing edges
    node_keys: list[Hashable]  # graph nodes in row order
    node_count: int

    @property
    def index_for(self) -> dict[Hashable, int]:
        """Return a ``{node: row_index}`` mapping for caller-side seed lookup."""
        return {key: i for i, key in enumerate(self.node_keys)}


def nx_digraph_to_csr(
    graph: nx.DiGraph,
    *,
    normalize_per_source: bool,
    weight_attr: str = "weight",
) -> NxCsrGraph:
    """Convert *graph* to the row=target CSR layout.

    Parameters
    ----------
    graph
        A directed networkx graph. Undirected input must be rejected
        by the caller before this point — HITS / PPR don't make
        sense on undirected edges.
    normalize_per_source
        When ``True``, edge weights are divided by the sum of
        outgoing weights from each source node so the result is a
        column-stochastic transition matrix (PageRank / PPR
        convention). When ``False``, raw edge weights pass through
        unchanged (HITS convention — weights are co-citation /
        co-link counts and aggregate naturally).
    weight_attr
        Edge attribute to read for the weight. Missing → 1.0
        (unweighted edge), matching networkx's own default for
        ``pagerank``/``hits`` when ``weight`` isn't set on edges.

    Returns
    -------
    :class:`NxCsrGraph`. All four arrays are length-N or length-E
    numpy arrays in the dtypes the C++ kernels expect.

    Notes
    -----
    Empty graphs return an :class:`NxCsrGraph` with ``node_count=0``
    and zero-length arrays — callers should short-circuit before
    calling the kernels in that case.
    """
    node_keys = list(graph.nodes())
    n = len(node_keys)
    if n == 0:
        return NxCsrGraph(
            indptr=np.zeros(1, dtype=np.int32),
            indices=np.zeros(0, dtype=np.int32),
            data=np.zeros(0, dtype=np.float64),
            dangling=np.zeros(0, dtype=bool),
            node_keys=[],
            node_count=0,
        )

    index_for = {key: i for i, key in enumerate(node_keys)}

    # Pre-compute the out-weight total per source so per-source
    # normalisation is a single divide later. Done in one pass over
    # all edges; we do not need a second walk.
    out_total = np.zeros(n, dtype=np.float64)
    for u, v, edata in graph.edges(data=True):
        u_idx = index_for[u]
        w = float(edata.get(weight_attr, 1.0))
        out_total[u_idx] += w

    # Bucket edges by target row so the CSR build is one O(E) walk.
    # Each bucket is a list of (source_index, weight_after_normalize).
    by_target: list[list[tuple[int, float]]] = [[] for _ in range(n)]
    for u, v, edata in graph.edges(data=True):
        u_idx = index_for[u]
        v_idx = index_for[v]
        raw_weight = float(edata.get(weight_attr, 1.0))
        if normalize_per_source:
            # Each row of the transition matrix (row=target) holds
            # incoming probabilities. Normalising by ``out_total[u]``
            # makes Σ_v P(u→v) = 1 for every source u, the standard
            # PageRank convention. Sources with zero out-weight are
            # dangling — handled by the dangling_mask below; their
            # edges (if any) are kept with raw weight as a safety net,
            # though in practice ``out_total[u] == 0`` means the source
            # has no edges in the iteration loop.
            if out_total[u_idx] > 0.0:
                weight = raw_weight / out_total[u_idx]
            else:
                weight = raw_weight
        else:
            weight = raw_weight
        by_target[v_idx].append((u_idx, weight))

    indptr = np.zeros(n + 1, dtype=np.int32)
    for v in range(n):
        indptr[v + 1] = indptr[v] + len(by_target[v])
    total_edges = int(indptr[n])
    indices = np.zeros(total_edges, dtype=np.int32)
    data = np.zeros(total_edges, dtype=np.float64)
    cursor = 0
    for v in range(n):
        for src_idx, weight in by_target[v]:
            indices[cursor] = src_idx
            data[cursor] = weight
            cursor += 1

    # Dangling = nodes with no outgoing weight. Same definition the
    # existing weighted_pagerank.load_weighted_graph uses.
    dangling = out_total <= 0.0

    return NxCsrGraph(
        indptr=indptr,
        indices=indices,
        data=data,
        dangling=dangling,
        node_keys=node_keys,
        node_count=n,
    )
