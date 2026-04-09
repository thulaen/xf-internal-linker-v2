"""Weighted authority over the existing internal-link graph.

This keeps the classic PageRank path intact and computes a separate weighted
graph where outgoing probabilities reflect link prominence and context.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

try:
    from extensions import pagerank as pagerank_ext

    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

logger = logging.getLogger(__name__)
NodeKey = tuple[int, str]

_EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class WeightedLoadedGraph:
    """Graph inputs required to run weighted authority over content items."""

    node_keys: tuple[NodeKey, ...]
    adjacency_matrix: csr_matrix
    edge_count: int
    dangling_mask: np.ndarray
    fallback_row_count: int
    coalesced_duplicate_count: int


@dataclass(frozen=True, slots=True)
class _WeightedEdge:
    """A single stored edge used to build the weighted transition matrix."""

    source_index: int
    target_index: int
    anchor_text: str
    extraction_method: str
    link_ordinal: int | None
    source_internal_link_count: int | None
    context_class: str
    pk: int


def load_weighted_graph(
    settings_map: Mapping[str, float] | None = None,
) -> WeightedLoadedGraph:
    """Load the non-deleted content graph and build the weighted transition matrix."""
    from apps.content.models import ContentItem
    from apps.graph.models import ExistingLink

    node_qs = (
        ContentItem.objects.filter(is_deleted=False)
        .order_by("pk", "content_type")
        .values_list("pk", "content_type")
    )
    node_keys: tuple[NodeKey, ...] = tuple(
        (pk, content_type) for pk, content_type in node_qs
    )
    node_count = len(node_keys)
    index_by_key = {key: idx for idx, key in enumerate(node_keys)}

    if node_count == 0:
        return WeightedLoadedGraph(
            node_keys=(),
            adjacency_matrix=csr_matrix((0, 0), dtype=np.float64),
            edge_count=0,
            dangling_mask=np.zeros(0, dtype=bool),
            fallback_row_count=0,
            coalesced_duplicate_count=0,
        )

    edge_qs = ExistingLink.objects.filter(
        from_content_item__is_deleted=False,
        to_content_item__is_deleted=False,
    ).values_list(
        "pk",
        "from_content_item__pk",
        "from_content_item__content_type",
        "to_content_item__pk",
        "to_content_item__content_type",
        "anchor_text",
        "extraction_method",
        "link_ordinal",
        "source_internal_link_count",
        "context_class",
    )

    edge_map: dict[tuple[int, int], _WeightedEdge] = {}
    coalesced_duplicate_count = 0
    for (
        edge_pk,
        from_pk,
        from_type,
        to_pk,
        to_type,
        anchor_text,
        extraction_method,
        link_ordinal,
        source_internal_link_count,
        context_class,
    ) in edge_qs:
        source_index = index_by_key.get((from_pk, from_type))
        target_index = index_by_key.get((to_pk, to_type))
        if source_index is None or target_index is None:
            continue

        edge = _WeightedEdge(
            source_index=source_index,
            target_index=target_index,
            anchor_text=anchor_text or "",
            extraction_method=extraction_method or "",
            link_ordinal=link_ordinal,
            source_internal_link_count=source_internal_link_count,
            context_class=context_class or "",
            pk=int(edge_pk),
        )
        pair_key = (source_index, target_index)
        current = edge_map.get(pair_key)
        if current is None:
            edge_map[pair_key] = edge
            continue
        coalesced_duplicate_count += 1
        if _edge_order_key(edge) < _edge_order_key(current):
            edge_map[pair_key] = edge

    edges_by_source: dict[int, list[_WeightedEdge]] = defaultdict(list)
    for edge in edge_map.values():
        edges_by_source[edge.source_index].append(edge)

    weights_config = settings_map or _load_settings()
    row_indices: list[int] = []
    col_indices: list[int] = []
    weights: list[float] = []
    fallback_row_count = 0
    dangling_mask = np.ones(node_count, dtype=bool)

    for source_index, source_edges in sorted(edges_by_source.items()):
        if not source_edges:
            continue

        dangling_mask[source_index] = False
        probabilities, used_fallback = _normalize_source_edges(
            source_edges, weights_config
        )
        if used_fallback:
            fallback_row_count += 1

        for edge, probability in zip(source_edges, probabilities, strict=True):
            row_indices.append(edge.target_index)
            col_indices.append(edge.source_index)
            weights.append(probability)

    if not weights:
        return WeightedLoadedGraph(
            node_keys=node_keys,
            adjacency_matrix=csr_matrix((node_count, node_count), dtype=np.float64),
            edge_count=0,
            dangling_mask=np.ones(node_count, dtype=bool),
            fallback_row_count=0,
            coalesced_duplicate_count=coalesced_duplicate_count,
        )

    adjacency_matrix = coo_matrix(
        (
            np.asarray(weights, dtype=np.float64),
            (
                np.asarray(row_indices, dtype=np.int32),
                np.asarray(col_indices, dtype=np.int32),
            ),
        ),
        shape=(node_count, node_count),
        dtype=np.float64,
    ).tocsr()

    return WeightedLoadedGraph(
        node_keys=node_keys,
        adjacency_matrix=adjacency_matrix,
        edge_count=len(weights),
        dangling_mask=dangling_mask,
        fallback_row_count=fallback_row_count,
        coalesced_duplicate_count=coalesced_duplicate_count,
    )


def calculate_weighted_pagerank(
    graph: WeightedLoadedGraph,
    damping: float = 0.15,
    max_iter: int = 100,
    tolerance: float = 1e-6,
) -> tuple[dict[NodeKey, float], dict[str, int | float]]:
    """Run the weighted authority iteration over the prepared graph."""
    if not 0.0 <= damping < 1.0:
        raise ValueError("damping must be in the range [0, 1).")
    if max_iter <= 0:
        raise ValueError("max_iter must be positive.")
    if tolerance <= 0.0:
        raise ValueError("tolerance must be positive.")

    node_count = len(graph.node_keys)
    if node_count == 0:
        return {}, {
            "node_count": 0,
            "edge_count": 0,
            "dangling_count": 0,
            "iterations": 0,
            "final_delta": 0.0,
            "fallback_row_count": 0,
            "coalesced_duplicate_count": graph.coalesced_duplicate_count,
        }

    ranks = np.full(node_count, 1.0 / node_count, dtype=np.float64)
    dangling_count = int(graph.dangling_mask.sum())
    final_delta = 0.0
    iterations = 0

    for iteration in range(1, max_iter + 1):
        if HAS_CPP_EXT:
            next_ranks, final_delta = pagerank_ext.pagerank_step(
                np.asarray(graph.adjacency_matrix.indptr, dtype=np.int32),
                np.asarray(graph.adjacency_matrix.indices, dtype=np.int32),
                np.asarray(graph.adjacency_matrix.data, dtype=np.float64),
                ranks,
                graph.dangling_mask,
                float(damping),
                int(node_count),
            )
        else:
            next_ranks, final_delta = _pagerank_step_py(
                indptr=np.asarray(graph.adjacency_matrix.indptr, dtype=np.int32),
                indices=np.asarray(graph.adjacency_matrix.indices, dtype=np.int32),
                data=np.asarray(graph.adjacency_matrix.data, dtype=np.float64),
                ranks=ranks,
                dangling_mask=graph.dangling_mask,
                damping=damping,
                node_count=node_count,
            )
        ranks = next_ranks
        iterations = iteration

        if final_delta < tolerance:
            break

    scores = {
        key: float(score)
        for key, score in zip(graph.node_keys, ranks.tolist(), strict=True)
    }
    diagnostics: dict[str, int | float] = {
        "node_count": node_count,
        "edge_count": graph.edge_count,
        "dangling_count": dangling_count,
        "iterations": iterations,
        "final_delta": final_delta,
        "fallback_row_count": graph.fallback_row_count,
        "coalesced_duplicate_count": graph.coalesced_duplicate_count,
    }
    return scores, diagnostics


def persist_weighted_pagerank(scores: dict[NodeKey, float]) -> int:
    """Persist March 2026 PageRank back onto content items."""
    from apps.content.models import ContentItem
    from django.db import transaction

    score_map = {pk: score for (pk, _content_type), score in scores.items()}

    with transaction.atomic():
        items_to_update = list(
            ContentItem.objects.filter(pk__in=score_map.keys(), is_deleted=False)
        )
        for item in items_to_update:
            item.march_2026_pagerank_score = score_map[item.pk]

        if items_to_update:
            ContentItem.objects.bulk_update(
                items_to_update,
                ["march_2026_pagerank_score"],
                batch_size=1000,
            )

        updated_pks = [item.pk for item in items_to_update]
        ContentItem.objects.exclude(pk__in=updated_pks).update(
            march_2026_pagerank_score=0.0
        )

    logger.info(
        "March 2026 PageRank persisted: %d items updated.", len(items_to_update)
    )
    return len(items_to_update)


def _pagerank_step_py(
    *,
    indptr: np.ndarray,
    indices: np.ndarray,
    data: np.ndarray,
    ranks: np.ndarray,
    dangling_mask: np.ndarray,
    damping: float,
    node_count: int,
) -> tuple[np.ndarray, float]:
    """Run one weighted PageRank iteration step from CSR arrays."""
    link_mass = np.zeros(node_count, dtype=np.float64)
    for row in range(node_count):
        row_total = 0.0
        for idx in range(indptr[row], indptr[row + 1]):
            row_total += float(data[idx]) * float(ranks[indices[idx]])
        link_mass[row] = row_total

    dangling_mass = (
        float(ranks[dangling_mask].sum()) if int(dangling_mask.sum()) else 0.0
    )
    next_ranks = (1.0 - damping) * link_mass
    next_ranks += ((1.0 - damping) * dangling_mass + damping) / node_count
    next_ranks /= float(next_ranks.sum())
    delta = float(np.abs(next_ranks - ranks).sum())
    return next_ranks, delta


def run_weighted_pagerank(
    *,
    settings_map: Mapping[str, float] | None = None,
    damping: float = 0.15,
    max_iter: int = 100,
    tolerance: float = 1e-6,
) -> dict[str, int | float]:
    """Load graph, compute March 2026 PageRank, persist scores, and return diagnostics."""
    graph = load_weighted_graph(settings_map=settings_map)
    scores, diagnostics = calculate_weighted_pagerank(
        graph,
        damping=damping,
        max_iter=max_iter,
        tolerance=tolerance,
    )
    persist_weighted_pagerank(scores)
    return diagnostics


def _load_settings() -> dict[str, float]:
    from apps.core.views import get_weighted_authority_settings

    config = get_weighted_authority_settings()
    return {
        "position_bias": float(config["position_bias"]),
        "empty_anchor_factor": float(config["empty_anchor_factor"]),
        "bare_url_factor": float(config["bare_url_factor"]),
        "weak_context_factor": float(config["weak_context_factor"]),
        "isolated_context_factor": float(config["isolated_context_factor"]),
    }


def _normalize_source_edges(
    source_edges: list[_WeightedEdge],
    settings_map: Mapping[str, float],
) -> tuple[list[float], bool]:
    if not source_edges:
        return [], False

    raw_scores: list[float] = []
    for edge in source_edges:
        raw_score = _raw_edge_score(edge, settings_map)
        if not math.isfinite(raw_score):
            uniform_probability = 1.0 / len(source_edges)
            return [uniform_probability] * len(source_edges), True
        raw_scores.append(raw_score)

    row_sum = float(sum(raw_scores))
    if row_sum <= 0.0:
        uniform_probability = 1.0 / len(source_edges)
        return [uniform_probability] * len(source_edges), True

    return [score / row_sum for score in raw_scores], False


def _raw_edge_score(edge: _WeightedEdge, settings_map: Mapping[str, float]) -> float:
    kind_factor = 1.0
    if edge.extraction_method == "bare_url":
        kind_factor = float(settings_map["bare_url_factor"])
    elif edge.anchor_text.strip() == "":
        kind_factor = float(settings_map["empty_anchor_factor"])

    position_factor = 1.0
    link_count = edge.source_internal_link_count
    if edge.link_ordinal is not None and link_count is not None and link_count > 1:
        position_ratio = edge.link_ordinal / (link_count - 1)
        position_factor = 1.0 - (float(settings_map["position_bias"]) * position_ratio)

    context_factor = 1.0
    if edge.context_class == "weak_context":
        context_factor = float(settings_map["weak_context_factor"])
    elif edge.context_class == "isolated":
        context_factor = float(settings_map["isolated_context_factor"])

    raw_score = kind_factor * position_factor * context_factor
    if not math.isfinite(raw_score):
        return raw_score
    return max(_EPSILON, raw_score)


def _edge_order_key(edge: _WeightedEdge) -> tuple[int, int, int]:
    if edge.link_ordinal is None:
        return (1, 0, edge.pk)
    return (0, edge.link_ordinal, edge.pk)
