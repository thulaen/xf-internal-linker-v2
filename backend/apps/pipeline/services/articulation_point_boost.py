"""FR-101 Tarjan Articulation Point Boost (TAPB).

Rewards candidates where the host is an articulation point (cut vertex) of
the undirected link graph — a node whose removal would disconnect the
graph. Articulation-point hosts carry disproportionate structural value,
so their outbound links earn a small bonus.

Source: Tarjan, R. (1972). "Depth-first search and linear graph
algorithms." SIAM J. Computing 1(2):146–160, DOI 10.1137/0201010. §3 eq.
3.2 low-link characterization.

Divergence: Tarjan's algorithm runs on undirected graphs; we symmetrize
the directed ExistingLink graph before running the AP detection (Newman
2010 §7.4.1 standard treatment for directed cut analysis). We delegate
to networkx.articulation_points(G) which implements Tarjan 1972 with a
Cython-accelerated DFS.

Full spec: docs/specs/fr101-tarjan-articulation-point-boost.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class TAPBSettings:
    """FR-101 ranking-signal settings."""

    enabled: bool = True
    ranking_weight: float = 0.03
    apply_to_articulation_node_only: bool = True
    # BLC §6.4 minimum-data floor: too-small graphs produce meaningless AP sets.
    min_graph_nodes: int = 50


@dataclass(frozen=True, slots=True)
class TAPBEvaluation:
    """Per-pair TAPB result."""

    score_component: float
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArticulationPointCache:
    """Per-pipeline-run precomputed data for TAPB.

    Built once in pipeline_data.py via networkx.articulation_points(G)
    on the undirected symmetrization of the link graph.
    """

    articulation_point_set: frozenset[ContentKey]
    total_graph_nodes: int
    articulation_point_count: int


def evaluate_tapb(
    *,
    host_key: ContentKey,
    articulation_cache: ArticulationPointCache | None,
    settings: TAPBSettings,
) -> TAPBEvaluation:
    """Compute the FR-101 TAPB score.

    1.0 when host is an articulation point, 0.0 otherwise. Weighted by
    settings.ranking_weight at the ranker layer.
    """
    if not settings.enabled:
        return TAPBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "disabled",
                "path": "python",
            },
        )

    if articulation_cache is None:
        return TAPBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "cold_start_no_graph",
                "path": "python",
            },
        )

    if articulation_cache.total_graph_nodes < settings.min_graph_nodes:
        return TAPBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "insufficient_graph_data",
                "graph_node_count": articulation_cache.total_graph_nodes,
                "min_required": settings.min_graph_nodes,
                "path": "python",
            },
        )

    is_ap = host_key in articulation_cache.articulation_point_set
    score_component = 1.0 if is_ap else 0.0

    return TAPBEvaluation(
        score_component=score_component,
        diagnostics={
            "fallback_triggered": False,
            "diagnostic": "ok",
            "is_articulation_point": is_ap,
            "graph_node_count": articulation_cache.total_graph_nodes,
            "articulation_point_count": articulation_cache.articulation_point_count,
            "path": "python",
        },
    )
