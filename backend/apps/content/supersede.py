"""
Superseded-embedding archive + retention helpers (plan item 20).

Use ``archive_superseded_embedding`` at the moment a ContentItem's embedding
is about to be overwritten. The function takes a snapshot of the OLD vector
plus metadata, stores it in ``SupersededEmbedding``, and returns that row so
the caller can later call ``mark_replacement_verified`` once the new
embedding has been sanity-checked (downstream similarity still works, etc).

The pruner Celery task ``prune_superseded_embeddings`` deletes archived rows
that are both older than 7 days AND have a non-null
``replacement_verified_at`` — unverified copies stay even when old so the
operator still has a rollback path while things are in flux.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

# 7-day retention window per plan item 20.
RETENTION_DAYS = 7


def archive_superseded_embedding(content_item) -> "object | None":
    """Snapshot the ContentItem's current embedding to ``SupersededEmbedding``.

    Returns the newly-created row, or None if there was no embedding to archive
    or the archive step failed (the caller should still proceed with the
    replacement — archive is best-effort).
    """
    if getattr(content_item, "embedding", None) is None:
        return None
    try:
        from apps.content.models import SupersededEmbedding

        row = SupersededEmbedding.objects.create(
            content_item=content_item,
            embedding=content_item.embedding,
            embedding_model_version=getattr(content_item, "embedding_model_version", "")
            or "",
            content_hash=getattr(content_item, "content_hash", "") or "",
            content_version=getattr(content_item, "content_version", 1) or 1,
        )
        return row
    except Exception:
        logger.warning(
            "archive_superseded_embedding failed; replacement will proceed",
            exc_info=True,
        )
        return None


def mark_replacement_verified(superseded_row) -> None:
    """Flag an archived row as verified so the pruner is allowed to delete it."""
    if superseded_row is None:
        return
    try:
        superseded_row.replacement_verified_at = timezone.now()
        superseded_row.save(update_fields=["replacement_verified_at"])
    except Exception:
        logger.warning("mark_replacement_verified failed", exc_info=True)


def prune_verified_rows(now=None) -> dict:
    """Delete SupersededEmbedding rows older than RETENTION_DAYS AND verified.

    Returns a summary dict for logging / telemetry.
    """
    from apps.content.models import SupersededEmbedding

    if now is None:
        now = timezone.now()
    cutoff = now - timedelta(days=RETENTION_DAYS)

    qs = SupersededEmbedding.objects.filter(
        superseded_at__lt=cutoff,
        replacement_verified_at__isnull=False,
    )
    count = qs.count()
    if count:
        qs.delete()
    return {"ok": True, "pruned": count}
