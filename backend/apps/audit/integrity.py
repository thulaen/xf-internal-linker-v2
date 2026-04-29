"""
Startup integrity checks for artefact tables.
Ensures no-dups, no-circular-refs, and retention consistency.
"""

import logging
from django.db.models import Count, F, Q
from django.utils import timezone
from apps.audit.error_ingest import ingest_error
from apps.crawler.models import CrawledPageMeta
from apps.content.models import ContentItem, SupersededEmbedding

logger = logging.getLogger(__name__)

def verify_artefact_integrity():
    """
    Runs a suite of integrity checks against the database.
    Logs any violations to the Error Log via ingest_error.
    """
    logger.info("[integrity] Starting artefact integrity audit...")

    # 1. Duplicate CrawledPageMeta by normalized_url
    # Every session has a unique constraint, but cross-session duplicates
    # should have been handled by the Group D.5 upsert.
    dups = (
        CrawledPageMeta.objects.values("normalized_url")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )
    if dups.exists():
        for dup in dups:
            ingest_error(
                job_type="integrity_check",
                step="CrawledPageMeta",
                error_message=f"Duplicate CrawledPageMeta detected for URL: {dup['normalized_url']}",
                severity="high",
                why="Upsert logic in Group D.5 may have failed or manual edits occurred.",
            )

    # 2. Circular or daisy-chained duplicate_of references in ContentItem
    # Check for self-references first
    self_refs = ContentItem.objects.filter(duplicate_of=F("id"))
    if self_refs.exists():
        for item in self_refs:
            ingest_error(
                job_type="integrity_check",
                step="ContentItem",
                error_message=f"Circular reference: ContentItem {item.pk} is a duplicate of itself.",
                severity="critical",
                why="Import logic error: duplicate_of points to self.",
            )

    # Daisy-chain check: A -> B and B -> C
    # In V2, duplicate_of should ALWAYS point to a canonical item (duplicate_of=None)
    daisy_chains = ContentItem.objects.filter(
        duplicate_of__isnull=False,
        duplicate_of__duplicate_of__isnull=False
    )
    if daisy_chains.exists():
        for item in daisy_chains:
            ingest_error(
                job_type="integrity_check",
                step="ContentItem",
                error_message=f"Daisy-chained duplicate: ContentItem {item.pk} points to another duplicate {item.duplicate_of_id}.",
                severity="medium",
                why="Import logic error: duplicate_of should always point to the original canonical row.",
            )

    # 3. Orphaned SupersededEmbeddings
    # If a ContentItem is deleted, its superseded embeddings should stay for 7 days
    # (signals usually handle this, but let's check).
    orphans = SupersededEmbedding.objects.filter(content_item__isnull=True)
    if orphans.exists():
        count = orphans.count()
        ingest_error(
            job_type="integrity_check",
            step="SupersededEmbedding",
            error_message=f"Found {count} orphaned SupersededEmbedding rows.",
            severity="medium",
            why="ContentItem was deleted without cascade or signal failure.",
        )

    # 4. Retention drift
    # Check for rows older than 30 days that should have been pruned
    # (This is more of a health check than a hard integrity error).
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    old_superseded = SupersededEmbedding.objects.filter(
        superseded_at__lt=thirty_days_ago,
        replacement_verified_at__isnull=False
    )
    if old_superseded.exists():
        count = old_superseded.count()
        ingest_error(
            job_type="integrity_check",
            step="Retention",
            error_message=f"Found {count} verified SupersededEmbedding rows older than 30 days.",
            severity="low",
            why="nightly_data_retention task might be failing or stalled.",
        )

    logger.info("[integrity] Integrity audit complete.")
