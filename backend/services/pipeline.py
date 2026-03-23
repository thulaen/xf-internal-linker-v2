"""
Pipeline service — retrieval + ranking for link suggestions.

The core ML pipeline: given a host thread, find the best destination links.
Migrated from V1 with minimal changes in Phase 2.
V1 source: ../xf-internal-linker/services/pipeline.py

Pipeline steps:
1. Split host content into sentences (first 600 words only)
2. Embed each sentence
3. Retrieve candidate destinations via pgvector similarity search
4. Score candidates (semantic + keyword + PageRank + velocity + quality)
5. Filter by anchor policy (no generic anchors, cap reuse)
6. Return top 3 suggestions maximum
"""

# TODO Phase 2: migrate from V1 pipeline.py


def run_pipeline(host_thread_id: int) -> list[dict]:
    """
    Run the full suggestion pipeline for a host thread.

    Args:
        host_thread_id: The database ID of the thread to find links for.

    Returns:
        List of suggestion dicts (max 3), each containing:
        - destination_id: ContentItem pk
        - anchor_text: suggested anchor text
        - host_sentence: the sentence where the link would go
        - score: composite relevance score
        - score_breakdown: dict of individual scoring components

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Pipeline service migrated in Phase 2")
