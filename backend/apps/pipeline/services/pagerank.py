"""Standard global PageRank over the existing internal-link graph.

V2 change from V1: replaces raw SQLite queries with Django ORM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

logger = logging.getLogger(__name__)
NodeKey = tuple[int, str]


@dataclass(frozen=True, slots=True)
class LoadedGraph:
    """Graph inputs required to run PageRank over content_items."""

    node_keys: tuple[NodeKey, ...]
    index_by_key: dict[NodeKey, int]
    adjacency_matrix: csr_matrix
    edge_count: int
    dangling_mask: np.ndarray


def load_graph() -> LoadedGraph:
    """Load the non-deleted content graph and valid directed edges via Django ORM."""
    from apps.content.models import ContentItem
    from apps.graph.models import ExistingLink

    node_qs = (
        ContentItem.objects
        .filter(is_deleted=False)
        .order_by("pk", "content_type")
        .values_list("pk", "content_type")
    )
    node_keys: tuple[NodeKey, ...] = tuple(
        (pk, content_type) for pk, content_type in node_qs
    )
    index_by_key: dict[NodeKey, int] = {key: idx for idx, key in enumerate(node_keys)}
    node_count = len(node_keys)

    if node_count == 0:
        return LoadedGraph(
            node_keys=(),
            index_by_key={},
            adjacency_matrix=csr_matrix((0, 0), dtype=np.float64),
            edge_count=0,
            dangling_mask=np.zeros(0, dtype=bool),
        )

    edge_qs = (
        ExistingLink.objects
        .filter(
            from_content_item__is_deleted=False,
            to_content_item__is_deleted=False,
        )
        .order_by(
            "from_content_item__pk",
            "from_content_item__content_type",
            "to_content_item__pk",
            "to_content_item__content_type",
        )
        .values_list(
            "from_content_item__pk",
            "from_content_item__content_type",
            "to_content_item__pk",
            "to_content_item__content_type",
        )
    )

    row_indices: list[int] = []
    col_indices: list[int] = []
    for from_pk, from_type, to_pk, to_type in edge_qs:
        from_key: NodeKey = (from_pk, from_type)
        to_key: NodeKey = (to_pk, to_type)
        from_idx = index_by_key.get(from_key)
        to_idx = index_by_key.get(to_key)
        if from_idx is None or to_idx is None:
            continue
        row_indices.append(to_idx)
        col_indices.append(from_idx)

    edge_count = len(row_indices)
    if edge_count == 0:
        return LoadedGraph(
            node_keys=node_keys,
            index_by_key=index_by_key,
            adjacency_matrix=csr_matrix((node_count, node_count), dtype=np.float64),
            edge_count=0,
            dangling_mask=np.ones(node_count, dtype=bool),
        )

    row_array = np.asarray(row_indices, dtype=np.int32)
    col_array = np.asarray(col_indices, dtype=np.int32)
    out_degree = np.bincount(col_array, minlength=node_count).astype(np.float64)
    weights = 1.0 / out_degree[col_array]

    adjacency_matrix = coo_matrix(
        (weights, (row_array, col_array)),
        shape=(node_count, node_count),
        dtype=np.float64,
    ).tocsr()

    return LoadedGraph(
        node_keys=node_keys,
        index_by_key=index_by_key,
        adjacency_matrix=adjacency_matrix,
        edge_count=edge_count,
        dangling_mask=out_degree == 0,
    )


def calculate_pagerank(
    graph: LoadedGraph,
    damping: float = 0.15,
    max_iter: int = 100,
    tolerance: float = 1e-6,
) -> tuple[dict[NodeKey, float], dict[str, int | float]]:
    """Run standard global PageRank power iteration on the loaded graph."""
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
        }

    ranks = np.full(node_count, 1.0 / node_count, dtype=np.float64)
    dangling_count = int(graph.dangling_mask.sum())
    final_delta = 0.0
    iterations = 0

    for iteration in range(1, max_iter + 1):
        link_mass = graph.adjacency_matrix @ ranks
        dangling_mass = float(ranks[graph.dangling_mask].sum()) if dangling_count else 0.0

        next_ranks = (1.0 - damping) * link_mass
        next_ranks += ((1.0 - damping) * dangling_mass + damping) / node_count
        next_ranks /= float(next_ranks.sum())

        final_delta = float(np.abs(next_ranks - ranks).sum())
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
    }
    return scores, diagnostics


def persist_pagerank(scores: dict[NodeKey, float]) -> int:
    """Persist PageRank scores back onto non-deleted content_items via Django ORM.

    Returns the number of items updated.
    """
    from apps.content.models import ContentItem

    ContentItem.objects.filter(is_deleted=False).update(pagerank_score=0.0)

    updated = 0
    for (pk, content_type), score in scores.items():
        count = ContentItem.objects.filter(
            pk=pk,
            content_type=content_type,
            is_deleted=False,
        ).update(pagerank_score=score)
        updated += count

    logger.info("PageRank persisted: %d items updated.", updated)
    return updated


def run_pagerank(
    damping: float = 0.15,
    max_iter: int = 100,
    tolerance: float = 1e-6,
) -> dict[str, int | float]:
    """Load graph, run PageRank, persist scores, return diagnostics dict."""
    graph = load_graph()
    scores, diagnostics = calculate_pagerank(graph, damping=damping, max_iter=max_iter, tolerance=tolerance)
    persist_pagerank(scores)
    return diagnostics
