"""FR-103 Bridge-Edge Redundancy Penalty (BERP).

Applies a small penalty when adding host→dest would create a new bridge
edge — a fragile single-path connector between two otherwise-disconnected
subgraphs. Discourages creating single points of failure in the link
topology.

Source: Hopcroft, J. & Tarjan, R. (1973). "Algorithm 447: efficient
algorithms for graph manipulation." CACM 16(6):372–378, DOI
10.1145/362248.362272. §2 Algorithm 3 — O(V+E) bridge detection.

Implementation: we use biconnected-component (BCC) membership as a proxy
for would-be-bridge detection. Host and dest in *different* BCCs of the
existing undirected graph means host→dest would be a bridge (Tarjan 1972
§3: BCCs partition edges into cycle-equivalence classes; bridges are the
inter-BCC edges).

Full spec: docs/specs/fr103-bridge-edge-redundancy-penalty.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class BERPSettings:
    enabled: bool = True
    ranking_weight: float = 0.04
    min_component_size: int = 5  # Skip small BCCs — noisy
    min_graph_nodes: int = 50


@dataclass(frozen=True, slots=True)
class BERPEvaluation:
    score_component: float  # Always ≤ 0 (penalty)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BridgeEdgeCache:
    """Per-pipeline BCC precompute."""

    bcc_label_map: dict[ContentKey, int]  # node → BCC label
    bcc_size_map: dict[int, int]  # BCC label → size
    total_graph_nodes: int


def evaluate_berp(
    *,
    host_key: ContentKey,
    destination_key: ContentKey,
    bridge_cache: BridgeEdgeCache | None,
    settings: BERPSettings,
) -> BERPEvaluation:
    """Returns a negative score_component when host→dest would be a bridge edge."""
    if not settings.enabled:
        return BERPEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "disabled",
                "path": "python",
            },
        )

    if (
        bridge_cache is None
        or bridge_cache.total_graph_nodes < settings.min_graph_nodes
    ):
        return BERPEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "insufficient_graph_data",
                "graph_node_count": bridge_cache.total_graph_nodes
                if bridge_cache
                else 0,
                "path": "python",
            },
        )

    host_bcc = bridge_cache.bcc_label_map.get(host_key)
    dest_bcc = bridge_cache.bcc_label_map.get(destination_key)
    if host_bcc is None or dest_bcc is None:
        return BERPEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "host_or_dest_not_in_graph",
                "path": "python",
            },
        )

    host_bcc_size = int(bridge_cache.bcc_size_map.get(host_bcc, 0))
    dest_bcc_size = int(bridge_cache.bcc_size_map.get(dest_bcc, 0))

    # Skip tiny BCCs — a 1-node BCC is just an isolated node; penalty is noise.
    if (
        host_bcc_size < settings.min_component_size
        or dest_bcc_size < settings.min_component_size
    ):
        return BERPEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "small_component_skip",
                "host_bcc": host_bcc,
                "dest_bcc": dest_bcc,
                "host_bcc_size": host_bcc_size,
                "dest_bcc_size": dest_bcc_size,
                "min_component_size": settings.min_component_size,
                "path": "python",
            },
        )

    would_create_bridge = host_bcc != dest_bcc

    if not would_create_bridge:
        return BERPEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": False,
                "diagnostic": "ok",
                "host_bcc": host_bcc,
                "dest_bcc": dest_bcc,
                "would_create_bridge": False,
                "host_bcc_size": host_bcc_size,
                "dest_bcc_size": dest_bcc_size,
                "path": "python",
            },
        )

    # Penalty: -1.0. Ranker multiplies by ranking_weight, producing net -weight.
    return BERPEvaluation(
        score_component=-1.0,
        diagnostics={
            "fallback_triggered": False,
            "diagnostic": "ok",
            "host_bcc": host_bcc,
            "dest_bcc": dest_bcc,
            "would_create_bridge": True,
            "host_bcc_size": host_bcc_size,
            "dest_bcc_size": dest_bcc_size,
            "path": "python",
        },
    )
