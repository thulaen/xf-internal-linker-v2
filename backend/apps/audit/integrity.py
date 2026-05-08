"""
Startup integrity checks for artefact tables.

Ensures no-dups, no-circular-refs, and retention consistency.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from django.db import models
from django.db.models import Count, F, QuerySet
from django.utils import timezone

from apps.audit.error_ingest import ingest_error
from apps.content.models import ContentItem, SupersededEmbedding
from apps.crawler.models import CrawledPageMeta

logger = logging.getLogger(__name__)

VERIFIED_SUPERSEDED_RETENTION_DAYS = 30


@dataclass(frozen=True)
class ArtefactTableSpec:
    """One artefact table plus the duplicate-identity fields it must respect."""

    name: str
    model: type[models.Model]
    duplicate_identity_fields: tuple[str, ...]
    verifier: Callable[[], None]


def _emit_integrity_error(
    *,
    step: str,
    error_message: str,
    severity: str,
    why: str,
) -> None:
    ingest_error(
        job_type="integrity_check",
        step=step,
        error_message=error_message,
        severity=severity,
        why=why,
    )


def _duplicate_groups_for_spec(spec: ArtefactTableSpec) -> QuerySet:
    return (
        spec.model.objects.exclude(content_hash="")
        .values(*spec.duplicate_identity_fields)
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )


def _format_identity(fields: tuple[str, ...], group: dict[str, object]) -> str:
    return ", ".join(f"{field}={group[field]!r}" for field in fields)


def _verify_crawled_page_meta() -> None:
    spec = CRAWLED_PAGE_META_SPEC
    duplicates = _duplicate_groups_for_spec(spec)
    for duplicate in duplicates:
        identity = _format_identity(spec.duplicate_identity_fields, duplicate)
        _emit_integrity_error(
            step=spec.name,
            error_message=f"Duplicate CrawledPageMeta detected for {identity}.",
            severity="high",
            why="Crawler upsert logic may have failed or manual edits occurred.",
        )


def _verify_content_item_duplicates() -> None:
    _emit_self_reference_errors()
    _emit_daisy_chain_errors()


def _emit_self_reference_errors() -> None:
    self_refs = ContentItem.objects.filter(duplicate_of=F("id"))
    for item in self_refs:
        _emit_integrity_error(
            step="ContentItem",
            error_message=(
                f"Circular reference: ContentItem {item.pk} is a duplicate of itself."
            ),
            severity="critical",
            why="Import logic error: duplicate_of points to self.",
        )


def _emit_daisy_chain_errors() -> None:
    daisy_chains = ContentItem.objects.filter(
        duplicate_of__isnull=False,
        duplicate_of__duplicate_of__isnull=False,
    )
    for item in daisy_chains:
        _emit_integrity_error(
            step="ContentItem",
            error_message=(
                f"Daisy-chained duplicate: ContentItem {item.pk} points to another "
                f"duplicate {item.duplicate_of_id}."
            ),
            severity="medium",
            why="Import logic error: duplicate_of should always point to the canonical row.",
        )


def _verify_superseded_embeddings() -> None:
    _emit_orphaned_superseded_embedding_error()
    _emit_retention_drift_error()


def _emit_orphaned_superseded_embedding_error() -> None:
    orphans = SupersededEmbedding.objects.filter(content_item__isnull=True)
    count = orphans.count()
    if count:
        _emit_integrity_error(
            step="SupersededEmbedding",
            error_message=f"Found {count} orphaned SupersededEmbedding rows.",
            severity="medium",
            why="ContentItem was deleted without cascade or signal failure.",
        )


def _emit_retention_drift_error() -> None:
    cutoff = timezone.now() - timezone.timedelta(
        days=VERIFIED_SUPERSEDED_RETENTION_DAYS
    )
    old_superseded = SupersededEmbedding.objects.filter(
        superseded_at__lt=cutoff,
        replacement_verified_at__isnull=False,
    )
    count = old_superseded.count()
    if count:
        _emit_integrity_error(
            step="Retention",
            error_message=(
                f"Found {count} verified SupersededEmbedding rows older than "
                f"{VERIFIED_SUPERSEDED_RETENTION_DAYS} days."
            ),
            severity="low",
            why="nightly_data_retention task might be failing or stalled.",
        )


CRAWLED_PAGE_META_SPEC = ArtefactTableSpec(
    name="CrawledPageMeta",
    model=CrawledPageMeta,
    duplicate_identity_fields=("normalized_url", "content_hash"),
    verifier=_verify_crawled_page_meta,
)

ARTEFACT_TABLE_SPECS: tuple[ArtefactTableSpec, ...] = (
    CRAWLED_PAGE_META_SPEC,
    ArtefactTableSpec(
        name="ContentItem",
        model=ContentItem,
        duplicate_identity_fields=("content_hash",),
        verifier=_verify_content_item_duplicates,
    ),
    ArtefactTableSpec(
        name="SupersededEmbedding",
        model=SupersededEmbedding,
        duplicate_identity_fields=(
            "content_item",
            "embedding_model_version",
            "content_hash",
            "content_version",
        ),
        verifier=_verify_superseded_embeddings,
    ),
)


def verify_artefact_integrity() -> None:
    """
    Run startup integrity checks and report violations to the Error Log.
    """
    logger.info("[integrity] Starting artefact integrity audit...")
    for spec in ARTEFACT_TABLE_SPECS:
        spec.verifier()
    logger.info("[integrity] Integrity audit complete.")
