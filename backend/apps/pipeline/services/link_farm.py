"""FR-197 reciprocal link-farm ring detector."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Mapping, TypeAlias

ContentKey: TypeAlias = tuple[int, str]
ExistingLinkKey: TypeAlias = tuple[ContentKey, ContentKey]


@dataclass(frozen=True, slots=True)
class LinkFarmSettings:
    enabled: bool = True
    ranking_weight: float = 0.03
    min_scc_size: int = 3
    density_threshold: float = 0.6
    lambda_value: float = 0.8
    algorithm_version: str = "fr197-v1"


@dataclass(frozen=True, slots=True)
class LinkFarmEvaluation:
    score_link_farm: float
    score_component: float
    diagnostics: dict[str, object]


def detect_link_farm_rings(
    *,
    existing_links: set[ExistingLinkKey],
    settings: LinkFarmSettings,
) -> dict[ContentKey, LinkFarmEvaluation]:
    """Detect SCCs in the reciprocal sub-graph and score each node."""
    if not settings.enabled:
        return {}
    if not existing_links:
        return {}

    original_adj: dict[ContentKey, set[ContentKey]] = defaultdict(set)
    reciprocal_adj: dict[ContentKey, set[ContentKey]] = defaultdict(set)
    all_nodes: set[ContentKey] = set()

    for source_key, dest_key in existing_links:
        original_adj[source_key].add(dest_key)
        all_nodes.add(source_key)
        all_nodes.add(dest_key)

    for source_key, dest_key in existing_links:
        if source_key == dest_key:
            continue
        if source_key in original_adj.get(dest_key, set()):
            reciprocal_adj[source_key].add(dest_key)

    components = _tarjan_scc(all_nodes, reciprocal_adj)
    evaluations: dict[ContentKey, LinkFarmEvaluation] = {}
    total_nodes = max(len(all_nodes), 1)
    for scc_id, component in enumerate(components):
        if len(component) < settings.min_scc_size:
            for node in component:
                evaluations[node] = _neutral_eval(
                    state="below_min_scc_size",
                    algorithm_version=settings.algorithm_version,
                )
            continue

        component_set = set(component)
        internal_edges = 0
        outflow = 0
        for node in component:
            outgoing = original_adj.get(node, set())
            internal_edges += sum(1 for target in outgoing if target in component_set)
            outflow += sum(1 for target in outgoing if target not in component_set)

        size = len(component)
        density = internal_edges / max(size * (size - 1), 1)
        if density < settings.density_threshold:
            for node in component:
                evaluations[node] = _neutral_eval(
                    state="below_density_threshold",
                    algorithm_version=settings.algorithm_version,
                    extras={
                        "scc_id": scc_id,
                        "ring_size": size,
                        "ring_density": round(density, 6),
                        "ring_outflow": outflow,
                    },
                )
            continue

        capped_size = min(size, max(1, int(total_nodes * 0.1)))
        ring_score = density * math.log1p(capped_size) * (1.0 / (1.0 + (outflow / size)))
        ring_penalty = 1.0 - math.exp(-settings.lambda_value * ring_score)
        score_link_farm = 0.5 - 0.5 * ring_penalty
        score_component = min(0.0, 2.0 * (score_link_farm - 0.5))
        state = "over_clustered" if size > capped_size else "scored"
        for node in component:
            evaluations[node] = LinkFarmEvaluation(
                score_link_farm=score_link_farm,
                score_component=score_component,
                diagnostics={
                    "link_farm_state": state,
                    "scc_id": scc_id,
                    "ring_size": size,
                    "ring_density": round(density, 6),
                    "ring_outflow": outflow,
                    "ring_score": round(ring_score, 6),
                    "ring_penalty": round(ring_penalty, 6),
                    "score_link_farm": round(score_link_farm, 6),
                    "density_threshold": settings.density_threshold,
                    "lambda": settings.lambda_value,
                    "algorithm_version": settings.algorithm_version,
                },
            )
    return evaluations


def _neutral_eval(
    *,
    state: str,
    algorithm_version: str,
    extras: dict[str, object] | None = None,
) -> LinkFarmEvaluation:
    diagnostics = {
        "link_farm_state": state,
        "ring_size": 0,
        "ring_density": 0.0,
        "ring_outflow": 0,
        "ring_score": 0.0,
        "ring_penalty": 0.0,
        "score_link_farm": 0.5,
        "algorithm_version": algorithm_version,
    }
    if extras:
        diagnostics.update(extras)
    return LinkFarmEvaluation(
        score_link_farm=0.5,
        score_component=0.0,
        diagnostics=diagnostics,
    )


def _tarjan_scc(
    nodes: set[ContentKey],
    adjacency: Mapping[ContentKey, set[ContentKey]],
) -> list[list[ContentKey]]:
    index = 0
    stack: list[ContentKey] = []
    on_stack: set[ContentKey] = set()
    indices: dict[ContentKey, int] = {}
    lowlinks: dict[ContentKey, int] = {}
    components: list[list[ContentKey]] = []

    def strongconnect(node: ContentKey) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in adjacency.get(node, set()):
            if neighbor not in indices:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])

        if lowlinks[node] == indices[node]:
            component: list[ContentKey] = []
            while stack:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == node:
                    break
            components.append(component)

    for node in nodes:
        if node not in indices:
            strongconnect(node)
    return components
