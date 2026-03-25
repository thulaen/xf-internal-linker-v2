"""
Embeddings service — sentence-transformers wrapper.

Generates semantic embedding vectors for content items.
Migrated from V1 with minimal changes in Phase 2.
V1 source: ../xf-internal-linker/services/embeddings.py
"""

# TODO Phase 2: migrate from V1 embeddings.py
# Key V1 behavior to preserve:
# - Uses sentence-transformers (BAAI/bge-small-en-v1.5 by default)
# - Batch processing with configurable batch size
# - CPU mode by default, optional GPU via ML_PERFORMANCE_MODE=HIGH_PERFORMANCE
# - Stores vectors in PostgreSQL via pgvector (replacing .npy files)


def generate_embedding(text: str) -> list[float]:
    """
    Generate a semantic embedding vector for the given text.

    Args:
        text: The text to embed (typically title + distilled body).

    Returns:
        A list of floats representing the embedding vector.

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Embeddings service migrated in Phase 2")


def generate_batch_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embedding vectors for a batch of texts.

    Args:
        texts: List of texts to embed.

    Returns:
        List of embedding vectors, one per input text.

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Embeddings service migrated in Phase 2")
