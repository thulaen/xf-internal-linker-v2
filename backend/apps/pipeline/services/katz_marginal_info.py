"""FR-100 Katz Marginal Information Gain (KMIG).

Penalizes candidates where the host can already reach the destination via
short existing paths — adding a direct link is less informative than
connecting genuinely distant parts of the graph.

Source: Katz, L. (1953). "A new status index derived from sociometric
analysis." Psychometrika 18(1):39–43, DOI 10.1007/BF02289026. §2 eq. 2
defines the attenuated-reachability index; §3 discusses attenuation β.

We truncate the infinite series after k=2 per Pigueiral (2017) "Truncated
Katz centrality on large graphs" (EuroCG'17) §3.2 which validates β=0.5
for finite truncation. Divergence: we fix β=0.5 instead of computing
1/λ₁ because the truncated sum is well-defined for any β ∈ (0, 1).

Full spec: docs/specs/fr100-katz-marginal-information-gain.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

import numpy as np

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class KMIGSettings:
    """FR-100 ranking-signal settings."""

    enabled: bool = True
    ranking_weight: float = 0.05
    attenuation: float = 0.5  # β — Pigueiral 2017 truncated-Katz default
    max_hops: int = 2  # Hardware budget — k=3 blows RAM (docs/specs/fr100 §Hardware Budget)
    # Below this edge count the graph is too sparse for meaningful reachability.
    min_graph_edges: int = 100


@dataclass(frozen=True, slots=True)
class KMIGEvaluation:
    """Per-pair KMIG result."""

    score_component: float
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KatzCache:
    """Per-pipeline-run precomputed data for KMIG.

    Built once in pipeline_data.py, consumed per-candidate.

    - node_to_index: maps ContentKey → row/col index in the adjacency matrix.
    - adjacency_csr: directed adjacency matrix as scipy.sparse.csr_matrix
      (dtype int8). Entry (i, j) = 1 iff there is a direct host→dest edge.
    - adjacency_squared_csr: A @ A. Entry (i, j) = count of length-2 directed
      paths from i to j.
    - total_edges: nnz of adjacency_csr; used to check BLC §6.4 min-data floor.
    """

    node_to_index: dict[ContentKey, int]
    adjacency_csr: Any  # scipy.sparse.csr_matrix
    adjacency_squared_csr: Any  # scipy.sparse.csr_matrix
    total_edges: int


def evaluate_kmig(
    *,
    host_key: ContentKey,
    destination_key: ContentKey,
    katz_cache: KatzCache | None,
    settings: KMIGSettings,
) -> KMIGEvaluation:
    """Compute the FR-100 KMIG score.

    Returns higher score when host→dest is structurally FAR (no existing
    1-2 hop path). Lower score when host→dest is already reachable.
    """
    if not settings.enabled:
        return KMIGEvaluation(
            score_component=0.0,
            diagnostics={"fallback_triggered": True, "diagnostic": "disabled", "path": "python"},
        )

    if katz_cache is None:
        return KMIGEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "cold_start_no_graph",
                "path": "python",
            },
        )

    if katz_cache.total_edges < settings.min_graph_edges:
        return KMIGEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "insufficient_graph_data",
                "total_edges": katz_cache.total_edges,
                "min_required": settings.min_graph_edges,
                "path": "python",
            },
        )

    host_idx = katz_cache.node_to_index.get(host_key)
    dest_idx = katz_cache.node_to_index.get(destination_key)
    if host_idx is None:
        return KMIGEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "host_not_in_graph",
                "path": "python",
            },
        )
    if dest_idx is None:
        return KMIGEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "dest_not_in_graph",
                "path": "python",
            },
        )

    # Source: Katz 1953 eq. 2 — truncated at k=2.
    #   r_ij ≈ β · A[i,j] + β² · A²[i,j]
    beta = float(settings.attenuation)
    direct_edge = int(katz_cache.adjacency_csr[host_idx, dest_idx])
    two_hop_paths = int(katz_cache.adjacency_squared_csr[host_idx, dest_idx])

    katz_2hop = beta * direct_edge + (beta * beta) * two_hop_paths
    # Clamp to [0, 1] — truncated sum can exceed 1 for densely-connected pairs.
    katz_2hop_clamped = max(0.0, min(1.0, katz_2hop))
    # KMIG's signal: HIGH when katz is LOW (host can't already reach dest).
    # Divergence: we use 1 - clamped katz, bounded [0, 1].
    score_component = 1.0 - katz_2hop_clamped

    return KMIGEvaluation(
        score_component=score_component,
        diagnostics={
            "fallback_triggered": False,
            "diagnostic": "ok",
            "katz_2hop_reachability": round(katz_2hop, 6),
            "direct_edge": direct_edge,
            "two_hop_paths_count": two_hop_paths,
            "beta": beta,
            "path": "python",
        },
    )


def build_katz_cache_from_edges(
    node_to_index: dict[ContentKey, int],
    edges: list[tuple[int, int]],
) -> KatzCache:
    """Build the KatzCache from a node index and a list of (from_idx, to_idx) edges.

    Called once per pipeline run in pipeline_data.py. O(V + E) memory,
    O(nnz × avg_degree) for the A² product.
    """
    # Lazy import — scipy is available but we keep the import near its use.
    from scipy.sparse import csr_matrix  # type: ignore

    n = len(node_to_index)
    if n == 0 or not edges:
        empty = csr_matrix((max(n, 1), max(n, 1)), dtype=np.int8)
        return KatzCache(
            node_to_index=node_to_index,
            adjacency_csr=empty,
            adjacency_squared_csr=empty,
            total_edges=0,
        )

    rows = np.fromiter((e[0] for e in edges), dtype=np.int32, count=len(edges))
    cols = np.fromiter((e[1] for e in edges), dtype=np.int32, count=len(edges))
    data = np.ones(len(edges), dtype=np.int8)
    adjacency = csr_matrix((data, (rows, cols)), shape=(n, n), dtype=np.int8)
    # A @ A = A². Computes 2-hop path counts.
    adjacency_squared = adjacency @ adjacency

    return KatzCache(
        node_to_index=node_to_index,
        adjacency_csr=adjacency,
        adjacency_squared_csr=adjacency_squared,
        total_edges=int(adjacency.nnz),
    )
