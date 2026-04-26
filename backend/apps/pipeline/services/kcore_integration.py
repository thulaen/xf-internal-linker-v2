"""FR-102 K-Core Integration Boost (KCIB).

Rewards candidates where the host is in a higher k-core than the
destination — "high-centrality pulls periphery in." Integrates peripheral
pages into the site's dense core.

Source: Seidman, S. B. (1983). "Network structure and minimum degree."
Social Networks 5(3):269–287, DOI 10.1016/0378-8733(83)90028-X. §2 eq. 1
defines the k-core; §4 discusses k-core decomposition properties.

Modern implementation: Batagelj & Zaversnik (2003) "An O(m) algorithm for
cores decomposition of networks" — used by networkx.core_number(G).

Full spec: docs/specs/fr102-kcore-integration-boost.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class KCIBSettings:
    """FR-102 ranking-signal settings."""

    enabled: bool = True
    ranking_weight: float = 0.03
    min_kcore_spread: int = 1  # Minimum host.kcore - dest.kcore to trigger
    min_graph_nodes: int = 50


@dataclass(frozen=True, slots=True)
class KCIBEvaluation:
    score_component: float
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class KCoreCache:
    """Per-pipeline-run k-core precompute."""

    kcore_number_map: dict[ContentKey, int]
    max_kcore: int
    total_graph_nodes: int


def evaluate_kcib(
    *,
    host_key: ContentKey,
    destination_key: ContentKey,
    kcore_cache: KCoreCache | None,
    settings: KCIBSettings,
) -> KCIBEvaluation:
    if not settings.enabled:
        return KCIBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "disabled",
                "path": "python",
            },
        )

    if kcore_cache is None or kcore_cache.total_graph_nodes < settings.min_graph_nodes:
        return KCIBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "insufficient_graph_data",
                "graph_node_count": kcore_cache.total_graph_nodes if kcore_cache else 0,
                "path": "python",
            },
        )

    if kcore_cache.max_kcore <= 0:
        return KCIBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "degenerate_graph",
                "path": "python",
            },
        )

    host_kcore = kcore_cache.kcore_number_map.get(host_key)
    dest_kcore = kcore_cache.kcore_number_map.get(destination_key)
    if host_kcore is None:
        return KCIBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "host_not_in_graph",
                "path": "python",
            },
        )
    if dest_kcore is None:
        return KCIBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "dest_not_in_graph",
                "path": "python",
            },
        )

    # Source: Seidman 1983 §2 — core number. KCIB rewards host.kcore > dest.kcore.
    kcore_delta = host_kcore - dest_kcore
    if kcore_delta < settings.min_kcore_spread:
        return KCIBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "non_integrating_direction",
                "host_kcore": host_kcore,
                "dest_kcore": dest_kcore,
                "max_kcore": kcore_cache.max_kcore,
                "kcore_delta": kcore_delta,
                "path": "python",
            },
        )

    score_component = max(0.0, min(1.0, kcore_delta / kcore_cache.max_kcore))

    return KCIBEvaluation(
        score_component=score_component,
        diagnostics={
            "fallback_triggered": False,
            "diagnostic": "ok",
            "host_kcore": host_kcore,
            "dest_kcore": dest_kcore,
            "max_kcore": kcore_cache.max_kcore,
            "kcore_delta": kcore_delta,
            "path": "python",
        },
    )
