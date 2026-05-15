"""Scheduled refresh for missing passage embeddings."""

from __future__ import annotations

from django.db.models import Count


def refresh_passages(*, max_items: int = 1000) -> dict[str, int]:
    """Regenerate passage embeddings for canonical content missing passage rows."""
    if max_items <= 0:
        return {"processed": 0, "passages_refreshed": 0}

    from apps.content.models import ContentItem
    from apps.pipeline.services.passage_relevance import (
        regenerate_passage_embeddings_for,
    )

    queryset = (
        ContentItem.objects.select_related("post")
        .filter(is_deleted=False, duplicate_of__isnull=True, post__isnull=False)
        .annotate(passage_row_count=Count("passage_embeddings"))
        .filter(passage_row_count=0)
        .order_by("pk")[:max_items]
    )
    processed = 0
    refreshed = 0
    for item in queryset.iterator(chunk_size=100):
        processed += 1
        refreshed += regenerate_passage_embeddings_for(item)
    return {"processed": processed, "passages_refreshed": refreshed}
