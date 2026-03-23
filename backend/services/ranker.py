"""
Ranker service — scoring utilities for link suggestions.

Computes composite relevance scores combining:
- Semantic similarity (cosine distance via pgvector)
- Keyword overlap
- Node affinity (topic clustering)
- Content quality score
- PageRank score
- Velocity score (recency + engagement momentum)

Migrated from V1 with minimal changes in Phase 2.
V1 source: ../xf-internal-linker/services/ranker.py
"""

# TODO Phase 2: migrate from V1 ranker.py


def compute_score(
    semantic_score: float,
    keyword_score: float,
    pagerank_score: float,
    quality_score: float,
    velocity_score: float,
    node_affinity_score: float,
) -> float:
    """
    Compute a composite relevance score for a suggestion candidate.

    Args:
        semantic_score: Cosine similarity from pgvector (0.0–1.0).
        keyword_score: Keyword overlap ratio (0.0–1.0).
        pagerank_score: Normalized PageRank of destination (0.0–1.0).
        quality_score: Content quality estimate (0.0–1.0).
        velocity_score: Recency and engagement momentum (0.0–1.0).
        node_affinity_score: Topic cluster proximity (0.0–1.0).

    Returns:
        Weighted composite score (0.0–1.0).

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Ranker service migrated in Phase 2")
