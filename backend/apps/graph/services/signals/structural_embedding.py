import logging
import math
from typing import Any

from apps.core.runtime_flags import is_enabled
from apps.pipeline.services.node2vec_embeddings import (
    DEFAULT_DIMENSION,
    DEFAULT_NUM_WALKS,
    DEFAULT_P,
    DEFAULT_Q,
    DEFAULT_WALK_LENGTH,
    DEFAULT_WINDOW,
    _build_graph_from_edges,
    _train_node2vec,
)

logger = logging.getLogger(__name__)

# Small graph threshold for testing the skip path
NODE2VEC_MIN_NODES = 5


def compute_structural_embeddings(
    graph: Any,
) -> dict[int, list[float]]:
    """Compute node2vec embeddings reusing the existing pipeline package.

    Returns a dict mapping node_idx to embedding vector.
    Skips if node2vec is disabled or the graph is below the size threshold.
    """
    if not is_enabled("node2vec.enabled", default=True):
        logger.info("structural_embedding: skipped (disabled via config)")
        return {}

    node_count = graph.numberOfNodes()
    if node_count < NODE2VEC_MIN_NODES:
        logger.info("structural_embedding: skipped (below threshold %d < %d)", node_count, NODE2VEC_MIN_NODES)
        return {}

    edges = []
    def collect_edge(u, v, weight, edgeid):
        edges.append((str(u), str(v), float(weight)))
    
    graph.forEdges(collect_edge)

    if not edges:
        return {}

    nx_graph = _build_graph_from_edges(edges)
    if nx_graph.number_of_nodes() < 2:
        return {}

    # Seed for deterministic tests
    import numpy as np
    import random
    np.random.seed(42)
    random.seed(42)

    vectors_str = _train_node2vec(
        nx_graph,
        dimension=DEFAULT_DIMENSION,
        walk_length=DEFAULT_WALK_LENGTH,
        num_walks=DEFAULT_NUM_WALKS,
        p=DEFAULT_P,
        q=DEFAULT_Q,
        window=DEFAULT_WINDOW,
    )

    vectors = {}
    for node_idx_str, vec in vectors_str.items():
        try:
            vectors[int(node_idx_str)] = vec
        except ValueError:
            pass
            
    return vectors


def compute_embed_cosine(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two dense vectors."""
    if not vec1 or not vec2:
        return 0.0
    if len(vec1) != len(vec2):
        return 0.0
    
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1)
    norm2 = sum(a * a for a in vec2)
    
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


def populate_candidate_cosine(
    candidates: list[dict],
    embeddings: dict[int, list[float]],
    id_to_idx: dict[str, int],
) -> None:
    """Enrich candidate dictionaries with embed_cosine."""
    for cand in candidates:
        from_id = cand.get("from_id")
        to_id = cand.get("to_id")
        
        from_idx = id_to_idx.get(from_id) if from_id else None
        to_idx = id_to_idx.get(to_id) if to_id else None
        
        if (from_idx is not None and to_idx is not None and 
            from_idx in embeddings and to_idx in embeddings):
            vec1 = embeddings[from_idx]
            vec2 = embeddings[to_idx]
            cand["embed_cosine"] = compute_embed_cosine(vec1, vec2)
        else:
            cand["embed_cosine"] = 0.0
