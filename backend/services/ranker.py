"""
Ranker service stub.

The real ranker now lives in `backend/apps/pipeline/services/ranker.py`.
This placeholder stays only so old imports fail clearly if they are still used.
"""


def compute_score(
    semantic_score: float,
    keyword_score: float,
    march_2026_pagerank_score: float,
    quality_score: float,
    velocity_score: float,
    node_affinity_score: float,
) -> float:
    """
    Compute a composite relevance score for a suggestion candidate.

    Args:
        semantic_score: Cosine similarity from pgvector (0.0-1.0).
        keyword_score: Keyword overlap ratio (0.0-1.0).
        march_2026_pagerank_score: Normalized March 2026 PageRank of destination (0.0-1.0).
        quality_score: Content quality estimate (0.0-1.0).
        velocity_score: Recency and engagement momentum (0.0-1.0).
        node_affinity_score: Topic cluster proximity (0.0-1.0).

    Raises:
        NotImplementedError: This legacy stub should not be used.
    """
    raise NotImplementedError("Ranker service migrated to apps.pipeline.services.ranker")
