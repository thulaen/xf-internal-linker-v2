"""Celery tasks for pipeline, sync, embeddings, verification, and link health."""

from __future__ import annotations
from celery.exceptions import SoftTimeLimitExceeded

import logging
import time
import uuid
from typing import Any

import requests
from asgiref.sync import async_to_sync
import traceback
from datetime import date

from celery import shared_task
from channels.layers import get_channel_layer

from apps.pipeline.decorators import with_weight_lock
from apps.core.pause_contract import JobPaused
from apps.core.helpers import HelperConstraint
from apps.core.helpers.resource_aware_retry import resource_aware_retry
from requests import RequestException
from django.db import (
    DatabaseError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    connection,
)
from urllib.error import URLError

logger = logging.getLogger(__name__) # fixed

_MAX_BROKEN_LINK_SCAN_URLS = 10_000  # maxsize for broken-link scan

# Batch sizes for bulk DB writes
_SENTENCE_BULK_CREATE_BATCH = 500  # maxsize for sentence bulk_create
_DISTILLED_TEXT_BULK_UPDATE_BATCH = 200  # maxsize for distilled-text bulk_update


# Data-retention cutoffs
_RETENTION_12_MONTHS = 365  # days
_RETENTION_6_MONTHS = 180  # days
_RETENTION_3_MONTHS = 90  # days

# AppSetting keys that surface the most recent prune cardinality to
# the dashboard ("Retention queue" panel). Each value is the count
# of rows that the *next* prune run would delete; the dashboard reads
# them via ``apps.core.runtime_flags`` / a lightweight diagnostics
# endpoint to render the operator-facing "X rows pending prune" line.
RETENTION_PREVIEW_KEY_IMPRESSIONS = "retention.queue.suggestion_impressions"
RETENTION_PREVIEW_KEY_PRESENTATIONS = "retention.queue.suggestion_presentations"
RETENTION_PREVIEW_KEY_NON_APPROVED = "retention.queue.non_approved_suggestions"
RETENTION_PREVIEW_KEY_LAST_RUN_AT = "retention.queue.last_run_at"

# Percentage multiplier for lift calculations
_PCT_MULTIPLIER = 100  # maxsize for percentage conversion

# GSC spike alert cooldown
_GSC_SPIKE_COOLDOWN = 86400  # seconds

# Preview truncation lengths (for log/alert messages)
_TITLE_PREVIEW_LEN = 60  # maxsize for title preview
_RUN_ID_PREVIEW_LEN = 16  # maxsize for run-id preview

# Progress-reporting interval for scoring loop
_SCORING_PROGRESS_INTERVAL = 100  # maxsize for scoring loop progress reporting

# Branded feature-name VERSION label used in user-facing messages
_PAGERANK_VERSION_LABEL = "Weighted PageRank"


def _scope_id_set(scope: dict[str, Any] | None) -> set[int] | None:
    if not scope:
        return None
    raw_ids = scope.get("scope_ids")
    if raw_ids is None:
        return None
    return {int(scope_id) for scope_id in raw_ids if scope_id is not None}


def _content_item_id_set(scope: dict[str, Any] | None) -> set[int] | None:
    if not scope:
        return None
    raw_ids = scope.get("content_item_ids")
    if raw_ids is None:
        return None
    return {int(content_id) for content_id in raw_ids if content_id is not None}


@shared_task(
    bind=True,
    name="pipeline.run_pipeline",
    time_limit=7200,
    soft_time_limit=6900,
    # AutoIssue #20219: a connection dropped MID-run (Postgres restart, idle
    # timeout, network blip during a 2-hour run) must re-queue the task; the
    # start-of-task connection.close() guard then hands the retry a fresh
    # connection. Bounded at 3 retries with backoff so we never retry-storm.
    autoretry_for=(DatabaseError, InterfaceError, OperationalError),
    max_retries=3,
    retry_backoff=60,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=4096,
    expected_seconds_p50=1200,
)
def run_pipeline(
    self,
    *,
    run_id: str,
    host_scope: dict[str, Any] | None = None,
    destination_scope: dict[str, Any] | None = None,
    rerun_mode: str = "skip_pending",
) -> dict[str, Any]:
    from apps.pipeline.services.pipeline import run_pipeline as run_pipeline_service
    from apps.suggestions.models import PipelineRun

    if not connection.in_atomic_block:
        connection.close()

    started_at = time.monotonic()
    PipelineRun.objects.filter(run_id=run_id).update(run_state="running")
    _publish_progress(run_id, "running", 0.0, "Starting link suggestion pipeline.")

    def _progress(progress: float, message: str) -> None:
        _publish_progress(run_id, "running", progress, message)

    try:
        result = run_pipeline_service(
            run_id=run_id,
            rerun_mode=rerun_mode,
            host_scope_ids=_scope_id_set(host_scope),
            destination_scope_ids=_scope_id_set(destination_scope),
            destination_content_item_ids=_content_item_id_set(destination_scope),
            progress_fn=_progress,
        )
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        _mark_pipeline_run_failed(run_id, started_at, exc)
        raise

    duration_seconds = _mark_pipeline_run_completed(run_id, started_at, result)
    return {
        "run_id": run_id,
        "state": "completed",
        "suggestions_created": result.suggestions_created,
        "destinations_processed": result.items_in_scope,
        "destinations_skipped": result.destinations_skipped,
        "duration_seconds": duration_seconds,
    }


def _mark_pipeline_run_failed(
    run_id: str,
    started_at: float,
    exc: Exception,
) -> None:
    from apps.suggestions.models import PipelineRun

    PipelineRun.objects.filter(run_id=run_id).update(
        run_state="failed",
        duration_seconds=round(time.monotonic() - started_at, 3),
        error_message=str(exc),
    )
    _publish_progress(
        run_id,
        "failed",
        0.0,
        f"Link suggestion pipeline failed: {exc}",
        error=str(exc),
    )


def _mark_pipeline_run_completed(
    run_id: str,
    started_at: float,
    result: Any,
) -> float:
    from apps.suggestions.models import PipelineRun

    duration_seconds = round(time.monotonic() - started_at, 3)
    PipelineRun.objects.filter(run_id=run_id).update(
        run_state="completed",
        suggestions_created=result.suggestions_created,
        destinations_processed=result.items_in_scope,
        destinations_skipped=result.destinations_skipped,
        duration_seconds=duration_seconds,
        error_message="",
    )
    _publish_progress(
        run_id,
        "completed",
        1.0,
        "Link suggestion pipeline complete.",
        suggestions_created=result.suggestions_created,
        destinations_processed=result.items_in_scope,
        destinations_skipped=result.destinations_skipped,
    )
    return duration_seconds


def dispatch_pipeline_run(
    *,
    run_id: str,
    host_scope: dict[str, Any] | None = None,
    destination_scope: dict[str, Any] | None = None,
    rerun_mode: str = "skip_pending",
) -> dict[str, str]:
    run_pipeline.delay(
        run_id=run_id,
        host_scope=host_scope or {},
        destination_scope=destination_scope or {},
        rerun_mode=rerun_mode,
    )
    return {"runtime_owner": "celery"}


def _publish_progress(
    job_id: str, state: str, progress: float, message: str, **extra: Any
) -> None:
    """Publish a job progress event to the WebSocket channel group."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Channel layer not available; progress event not sent.")
        return

    # Ensure progress fields are initialized if not provided
    event = {
        "type": "job.progress",
        "job_id": job_id,
        "state": state,
        "progress": round(progress, 3),
        "message": message,
        "spacy_progress": extra.get("spacy_progress", 0.0),
        "embedding_progress": extra.get("embedding_progress", 0.0),
        **extra,
    }
    try:
        async_to_sync(channel_layer.group_send)(f"job_{job_id}", event)
    except (AttributeError, RuntimeError, ConnectionError):
        logger.exception("Failed to publish progress event for job %s", job_id)


def _emit_job_alert(  # noqa  # forbidden-pattern too-many-args  # justification: shared by every task's success/failure path; bundling kwargs would obscure call sites
    event_type: str,
    severity: str,
    title: str,
    message: str,
    *,
    job_id: str,
    job_type: str,
    related_route: str = "/jobs",
    error_log_id: int | None = None,
) -> None:
    """Emit an operator alert for a job event. Never raises — alert failure must not kill the task."""
    try:
        from apps.notifications.services import emit_operator_alert
        from apps.notifications.models import OperatorAlert

        emit_operator_alert(
            event_type=event_type,
            severity=severity,
            title=title,
            message=message,
            source_area=OperatorAlert.AREA_JOBS,
            dedupe_key=f"{event_type}:{job_id}",
            related_object_type="SyncJob",
            related_object_id=job_id,
            related_route=related_route,
            payload={"job_id": job_id, "job_type": job_type},
            error_log_id=error_log_id,
        )
    except (ImportError, AttributeError, DatabaseError):
        logger.warning(
            "_emit_job_alert: failed to emit alert for job %s", job_id, exc_info=True
        )


def _save_checkpoint(
    job_id: str, stage: str, last_item_id: int, items_processed: int
) -> None:
    """Persist checkpoint to SyncJob for crash-resilient resume (FR-97).

    Uses a single UPDATE query -- no SELECT, no .save().
    Wrapped so a checkpoint failure never crashes the import.
    """
    try:
        from apps.sync.models import SyncJob

        SyncJob.objects.filter(job_id=job_id).update(
            checkpoint_stage=stage,
            checkpoint_last_item_id=last_item_id,
            checkpoint_items_processed=items_processed,
        )
    except Exception:
        # B9 (2026-05-09): escalate from logger.debug → logger.warning so
        # checkpoint failures actually surface in the operator's logs.
        # A silent debug-level swallow meant resumed jobs could
        # re-process thousands of items from a stale checkpoint without
        # anyone noticing. Also stamp a sidecar AppSetting key so the
        # next resume can detect "I'm starting from a possibly-stale
        # checkpoint" and treat it as suspect.
        logger.warning(
            "Checkpoint write failed for job %s (stage=%s) — "
            "subsequent resume may start from a stale position.",
            job_id,
            stage,
            exc_info=True,
        )
        try:
            from apps.core.models import AppSetting

            AppSetting.objects.update_or_create(
                key=f"sync.checkpoint_failed_at.{job_id}",
                defaults={
                    "value": str(int(__import__("time").time())),
                    "value_type": "int",
                    "category": "sync",
                    "is_secret": False,
                },
            )
        except Exception:
            logger.debug("Could not stamp checkpoint-failure sidecar", exc_info=True)


@shared_task(
    bind=True,
    name="pipeline.recalculate_click_distance",
    time_limit=1800,
    soft_time_limit=1740,
    # AutoIssue #20219: re-queue on a mid-task DB connection drop so the
    # start-of-task close guard can hand the retry a fresh connection.
    autoretry_for=(DatabaseError, InterfaceError, OperationalError),
    max_retries=3,
    retry_backoff=60,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=180,
)
def recalculate_click_distance_task(self, job_id: str | None = None) -> dict:
    """Recompute Phase 15 Click-Distance scores for all active ContentItems."""
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    job_id = job_id or str(uuid.uuid4())
    _publish_progress(
        job_id,
        "running",
        0.0,
        "Starting Click-Distance structural prior recalculation...",
    )

    try:
        from apps.pipeline.services.click_distance import ClickDistanceService

        service = ClickDistanceService()
        diagnostics = service.recalculate_all()

        _publish_progress(
            job_id,
            "completed",
            1.0,
            "Click-Distance recalculation complete.",
            **diagnostics,
        )
        return {"job_id": job_id, **diagnostics}
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as exc:
        logger.exception("Click-Distance recalculation %s failed", job_id)
        _publish_progress(
            job_id,
            "failed",
            0.0,
            f"Click-Distance recalculation failed: {exc}",
            error=str(exc),
        )
        raise


def _status_label(http_status: int) -> str:
    return str(http_status) if http_status else "connection error"


def _broken_link_scan_result(
    *,
    job_id: str,
    scanned_urls: int,
    flagged_urls: int,
    fixed_urls: int,
    hit_scan_cap: bool,
    probe_backend: str,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "scanned_urls": scanned_urls,
        "flagged_urls": flagged_urls,
        "fixed_urls": fixed_urls,
        "hit_scan_cap": hit_scan_cap,
        "probe_backend": probe_backend,
    }


def _empty_broken_link_scan_result(job_id: str, hit_scan_cap: bool) -> dict[str, Any]:
    _publish_progress(job_id, "completed", 1.0, "No internal links found to scan.")
    return _broken_link_scan_result(
        job_id=job_id,
        scanned_urls=0,
        flagged_urls=0,
        fixed_urls=0,
        hit_scan_cap=hit_scan_cap,
        probe_backend="python_async_httpx",
    )


def _execute_broken_link_scan(job_id: str) -> dict[str, Any]:
    from django.utils import timezone

    from apps.pipeline.tasks_broken_links import (
        build_existing_records_map,
        collect_urls_to_scan,
        persist_scan_results,
        scan_via_async_http,
    )

    _publish_progress(job_id, "running", 0.0, "Collecting links for health check...")
    urls_to_scan, hit_scan_cap = collect_urls_to_scan()
    total_urls = len(urls_to_scan)
    if total_urls == 0:
        return _empty_broken_link_scan_result(job_id, hit_scan_cap)

    to_create: list[Any] = []
    to_update: list[Any] = []
    flagged_urls, fixed_urls, probe_backend = scan_via_async_http(
        list(urls_to_scan.values()),
        job_id=job_id,
        total_urls=total_urls,
        existing_records=build_existing_records_map(urls_to_scan),
        to_create=to_create,
        to_update=to_update,
        checked_at=timezone.now(),
        hit_scan_cap=hit_scan_cap,
    )
    persist_scan_results(to_create, to_update)
    _publish_progress(
        job_id,
        "completed",
        1.0,
        "Broken link scan complete.",
        scanned_urls=total_urls,
        flagged_urls=flagged_urls,
        fixed_urls=fixed_urls,
        hit_scan_cap=hit_scan_cap,
        probe_backend=probe_backend,
    )
    return _broken_link_scan_result(
        job_id=job_id,
        scanned_urls=total_urls,
        flagged_urls=flagged_urls,
        fixed_urls=fixed_urls,
        hit_scan_cap=hit_scan_cap,
        probe_backend=probe_backend,
    )


@shared_task(name="pipeline.scan_broken_links", time_limit=3600, soft_time_limit=3540)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def scan_broken_links(job_id: str | None = None) -> dict[str, Any]:
    """Identify and flag broken outbound internal links."""
    if not connection.in_atomic_block:
        connection.close()

    return _execute_broken_link_scan(job_id or str(uuid.uuid4()))


def dispatch_broken_link_scan(job_id: str | None = None) -> dict[str, str]:
    scan_broken_links.delay(job_id=job_id)
    return {"runtime_owner": "celery"}


@shared_task(name="pipeline.run_clustering_pass", time_limit=1800, soft_time_limit=1740)
@HelperConstraint(
    cpu_intensive=True,  # k-means + pgvector queries
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=1024,
    expected_seconds_p50=300,
)
def run_clustering_pass(job_id: str | None = None) -> dict:
    """Run a batch clustering pass over all ContentItems with embeddings."""
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    from apps.content.models import ContentItem
    from apps.content.services.clustering import ClusteringService
    from apps.pipeline.services.embeddings import get_current_embedding_filter

    if not job_id:
        job_id = f"clustering_{int(time.time())}"

    logger.info("Starting batch clustering pass [%s]", job_id)
    _publish_progress(job_id, "running", 0.0, "Starting batch clustering pass...")

    # Filter items that have embeddings
    items = ContentItem.objects.filter(
        embedding__isnull=False,
        **get_current_embedding_filter(),
    ).only("id", "embedding", "cluster_id")
    total = items.count()

    if total == 0:
        _publish_progress(job_id, "completed", 1.0, "No items with embeddings found.")
        return {"status": "skipped", "message": "No items with embeddings."}

    service = ClusteringService()
    processed = 0

    for item in items:
        service.update_item_cluster(item.id)
        processed += 1
        if processed % 50 == 0:
            pct = processed / total
            _publish_progress(
                job_id, "running", pct, f"Clustered {processed}/{total} items..."
            )

    logger.info(
        "Batch clustering pass [%s] complete. Processed %d items.", job_id, processed
    )
    _publish_progress(
        job_id, "completed", 1.0, f"Clustering complete. Processed {processed} items."
    )

    return {"status": "completed", "processed": processed}


# ---------------------------------------------------------------------------
# Part 7 — Nightly data retention task
# ---------------------------------------------------------------------------


def _purge_aged_rows(  # noqa  # forbidden-pattern too-many-args  # justification: shared by 9 retention blocks; bundling kwargs would add allocations and obscure the per-call config
    *,
    model_cls,
    cutoff_field: str,
    cutoff,
    extra_filter: dict | None = None,
    label: str,
    step: str,
    fix_hint: str,
    use_date: bool = False,
) -> int:
    """Delete rows older than ``cutoff`` from ``model_cls``; log failure to ErrorLog.

    Returns deleted row count (0 on failure). Replaces 9 near-identical
    try/except blocks in ``nightly_data_retention``.
    """
    import traceback
    from django.db import DatabaseError
    from apps.audit.models import ErrorLog

    try:
        cutoff_value = cutoff.date() if use_date else cutoff
        qs_filter = {f"{cutoff_field}__lt": cutoff_value}
        if extra_filter:
            qs_filter.update(extra_filter)
        deleted, _ = model_cls.objects.filter(**qs_filter).delete()
        logger.info(
            "[nightly_data_retention] %s: deleted %d rows older than %s.",
            label,
            deleted,
            cutoff_value,
        )
        return deleted
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] %s purge failed.", label)
        # Close the broken connection so the next purge step gets a fresh one
        # from the pool instead of reusing the stale psycopg3 connection.
        if not connection.in_atomic_block:
            connection.close()
        ErrorLog.objects.create(
            job_type="data_retention",
            step=step,
            error_message=f"{label} retention purge failed.",
            raw_exception=raw,
            why=fix_hint,
        )
        return 0


def _purge_with_bitmap_preview(  # noqa  # forbidden-pattern too-many-args  # justification: shared by 3 IPS/IPW blocks (B.5, B.6, B.7); bundling reduces clarity at the per-call config sites
    *,
    queryset,
    use_bitmap: bool,
    label: str,
    step: str,
    fix_hint: str,
    preview_key: str | None = None,
) -> int:
    """Delete rows in ``queryset`` after taking a cardinality preview.

    For uint32-PK tables (SuggestionImpression, SuggestionPresentation),
    ``use_bitmap=True`` uses the Roaring bitmap path. UUID-PK tables
    (Suggestion) use ``use_bitmap=False`` and read cardinality via
    ``queryset.count()``.
    """
    import traceback
    from django.db import DatabaseError
    from apps.audit.models import ErrorLog
    from apps.pipeline.services import waste_bitmaps

    try:
        if use_bitmap:
            bitmap = waste_bitmaps.bitmap_from_pks(queryset)
            pending = waste_bitmaps.cardinality_preview(bitmap)
        else:
            pending = queryset.count()
        deleted = 0
        if pending:
            deleted, _ = queryset.delete()
        logger.info(
            "[nightly_data_retention] %s: deleted %d rows (preview was %d).",
            label,
            deleted,
            pending,
        )
        if preview_key is not None:
            _persist_retention_preview(preview_key, value=0, last_count=pending)
        return deleted
    except (DatabaseError, IntegrityError):
        raw = traceback.format_exc()
        logger.exception("[nightly_data_retention] %s purge failed.", label)
        if not connection.in_atomic_block:
            connection.close()
        ErrorLog.objects.create(
            job_type="data_retention",
            step=step,
            error_message=f"{label} retention purge failed.",
            raw_exception=raw,
            why=fix_hint,
        )
        return 0


def _retention_progress_reporter(progress_callback):
    """Wrap ``progress_callback`` in a no-op-on-error closure for nightly_data_retention."""

    def _report(pct: float, message: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(pct, message)
        except Exception:  # pragma: no cover — defensive
            logger.warning(
                "[nightly_data_retention] progress_callback raised "
                "for pct=%s message=%s; continuing",
                pct,
                message,
            )

    return _report


@shared_task(
    name="pipeline.nightly_data_retention",
    time_limit=1800,
    soft_time_limit=1740,
    # AutoIssue #20219: bulk Postgres deletes run for minutes; a mid-run
    # connection drop must re-queue rather than abort the nightly cleanup.
    autoretry_for=(DatabaseError, InterfaceError, OperationalError),
    max_retries=3,
    retry_backoff=60,
)
@HelperConstraint(
    cpu_intensive=False,  # bulk Postgres deletes; mostly DB-bound
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=600,
)
def nightly_data_retention(progress_callback=None):
    """Purge stale data rows according to the retention policy.

    Runs daily at 22:30 inside the operator window via
    ``apps.scheduled_updates.jobs.run_daily_data_retention`` (the
    primary caller). Also callable manually via
    ``nightly_data_retention.run()`` from the diagnostics manual-run
    view. The function name is kept (despite the ``nightly_`` prefix)
    for backward compatibility with the existing manual-run path and
    docstring references throughout the codebase.

    Retention policy:
        SearchMetric rows           — 12 months
        PipelineRun logs            — 90 days
        ContentMetricSnapshot       — keep last 2 per item
        Superseded Suggestions      — 30 days
        AuditEntry                  — 6 months (180 days)
        ErrorLog                    — 30 days
        WebhookReceipt              — 30 days
        SuggestionImpression        — 90 days  (B.5 — IPS / Cascade lookback)
        SuggestionPresentation      — 180 days (B.6 — IPW lookback)
        Pending / stale Suggestion  — 365 days (B.7 — non-approved trail)
        ImpactReport                — FOREVER (never purged)
        Approved Suggestion         — FOREVER (never purged — operator audit trail)
        WeightAdjustmentHistory     — FOREVER (never purged)

    *progress_callback*, when provided, is invoked as
    ``progress_callback(progress_pct: float, message: str)`` after each
    prune block so the scheduled-updates dashboard can render a live
    progress bar. Defaults to a no-op so the existing Celery / manual
    paths see no behavior change.
    """
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    from django.utils import timezone

    _report = _retention_progress_reporter(progress_callback)
    now = timezone.now()
    results: dict[str, int] = {}
    _report(0.0, "Starting data retention sweep")
    _run_standard_purges(now, results)
    _run_advanced_purges(now, results, _report)
    _persist_retention_run_timestamp(now.isoformat())
    _report(100.0, "Data retention complete")
    logger.info("[nightly_data_retention] Complete. Results: %s", results)
    return results


@shared_task(name="pipeline.prune_stale_data", time_limit=1800, soft_time_limit=1740)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def prune_stale_data(progress_callback=None):
    """Backward-compatible Celery name for the retention prune task."""
    return nightly_data_retention(progress_callback=progress_callback)


def _run_standard_purges(now, results: dict[str, int]) -> None:
    """Execute the 8 plain age-based purge blocks via the spec table."""
    from apps.audit.models import ErrorLog
    from apps.pipeline.services.velocity import prune_old_snapshots

    for spec in _build_standard_purge_specs(now):
        results[spec["result_key"]] = _purge_aged_rows(
            model_cls=spec["model_cls"],
            cutoff_field=spec["cutoff_field"],
            cutoff=spec["cutoff"],
            use_date=spec.get("use_date", False),
            extra_filter=spec.get("extra_filter"),
            label=spec["label"],
            step=spec["step"],
            fix_hint=spec["fix_hint"],
        )

    # ContentMetricSnapshot uses a "keep last N per item" rule, not an age
    # filter, so it doesn't fit the spec table.
    import traceback
    from django.db import DatabaseError

    try:
        results["metric_snapshots_deleted"] = prune_old_snapshots(keep=2)
        logger.info(
            "[nightly_data_retention] ContentMetricSnapshot: deleted %d rows (keeping last 2 per item).",
            results["metric_snapshots_deleted"],
        )
    except (DatabaseError, IntegrityError):
        logger.exception("[nightly_data_retention] ContentMetricSnapshot purge failed.")
        ErrorLog.objects.create(
            job_type="data_retention",
            step="metric_snapshot_purge",
            error_message="ContentMetricSnapshot retention purge failed.",
            raw_exception=traceback.format_exc(),
            why="Check database connectivity and the content.ContentMetricSnapshot table.",
        )
        results["metric_snapshots_deleted"] = 0


def _standard_purge_spec_rows() -> list[dict]:  # noqa  # forbidden-pattern long-function  # justification: pure static data table — adding a new retention rule = one entry; splitting would obscure the inventory.
    """Static spec rows used by :func:`_build_standard_purge_specs`.

    The 7 retention-purge entries below are pure data — each row maps
    directly to ``_purge_aged_rows`` keyword args. Splitting them into
    multiple functions would obscure the inventory; keeping the list
    here lets the operator scan all retention rules in one place.

    The age constants live in seconds-equivalent integer days, applied
    by the caller via ``now - timedelta(days=row["age_days"])``. Pulling
    the ``cutoff`` calculation OUT of the data rows lets this function
    run without a ``now`` argument, which is what makes it a pure
    static-data helper instead of a 90-line function.
    """
    from apps.analytics.models import SearchMetric
    from apps.audit.models import AuditEntry, ErrorLog
    from apps.crawler.models import CrawlerVisit
    from apps.suggestions.models import PipelineRun, Suggestion
    from apps.sync.models import WebhookReceipt

    return [
        {
            "model_cls": SearchMetric,
            "cutoff_field": "date",
            "use_date": True,
            "age_days": _RETENTION_12_MONTHS,
            "result_key": "search_metrics_deleted",
            "label": "SearchMetric (12 months)",
            "step": "search_metric_purge",
            "fix_hint": "Check database connectivity and the analytics.SearchMetric table.",
        },
        {
            "model_cls": PipelineRun,
            "cutoff_field": "created_at",
            "age_days": 90,
            "result_key": "pipeline_runs_deleted",
            "label": "PipelineRun (90 days)",
            "step": "pipeline_run_purge",
            "fix_hint": "Check database connectivity and the suggestions.PipelineRun table.",
        },
        {
            "model_cls": Suggestion,
            "cutoff_field": "updated_at",
            "age_days": 30,
            "extra_filter": {"status": "superseded"},
            "result_key": "superseded_suggestions_deleted",
            "label": "Superseded Suggestion (30 days)",
            "step": "superseded_suggestion_purge",
            "fix_hint": "Check database connectivity and the suggestions.Suggestion table.",
        },
        {
            "model_cls": AuditEntry,
            "cutoff_field": "created_at",
            "age_days": _RETENTION_6_MONTHS,
            "result_key": "audit_entries_deleted",
            "label": "AuditEntry (180 days)",
            "step": "audit_entry_purge",
            "fix_hint": "Check database connectivity and the audit.AuditEntry table.",
        },
        {
            "model_cls": ErrorLog,
            "cutoff_field": "created_at",
            "age_days": 30,
            "result_key": "error_logs_deleted",
            "label": "ErrorLog (30 days)",
            "step": "error_log_purge",
            # Cannot log ErrorLog purge failures to ErrorLog itself; logger.exception covers.
            "fix_hint": "Cannot self-log; check Postgres logs for the ErrorLog table.",
        },
        {
            "model_cls": WebhookReceipt,
            "cutoff_field": "created_at",
            "age_days": 30,
            "result_key": "webhook_receipts_deleted",
            "label": "WebhookReceipt (30 days)",
            "step": "webhook_receipt_purge",
            "fix_hint": "Check database connectivity and the sync.WebhookReceipt table.",
        },
        # Group D.7 — CrawlerVisit (D.5 dedup audit log; 90-day rolling window).
        # Heavy CrawledPageMeta rows are NOT pruned here — D.5/D.6 already dedupe them.
        {
            "model_cls": CrawlerVisit,
            "cutoff_field": "visited_at",
            "age_days": 90,
            "result_key": "crawler_visits_deleted",
            "label": "CrawlerVisit (D.7, 90 days)",
            "step": "crawler_visit_purge",
            "fix_hint": (
                "Check database connectivity and the crawler.CrawlerVisit table. "
                "The dedup feature (D.5) requires this table; failure here means "
                "the visit log will keep growing until disk runs out."
            ),
        },
    ]


def _build_standard_purge_specs(now) -> list[dict]:
    """Resolve cutoff timestamps for each spec row and return the list.

    Pure orchestration — the data lives in ``_standard_purge_spec_rows``
    so this function stays under the 50-line cap and adding a new
    retention rule means appending one entry to that helper, not
    editing this one.
    """
    from datetime import timedelta

    rows = _standard_purge_spec_rows()
    out: list[dict] = []
    for row in rows:
        spec = {k: v for k, v in row.items() if k != "age_days"}
        spec["cutoff"] = now - timedelta(days=row["age_days"])
        out.append(spec)
    return out


def _run_advanced_purges(now, results: dict[str, int], report) -> None:
    """Execute the 3 bitmap-preview purge blocks (B.5 / B.6 / B.7)."""
    from datetime import timedelta
    from apps.suggestions.models import (
        Suggestion,
        SuggestionImpression,
        SuggestionPresentation,
    )

    report(60.0, "Pruning IPS / Cascade impressions (B.5)")
    # Pick #33 (IPS) and #34 (Cascade Click) read 90-day impressions to fit
    # propensity estimates; older rows fall out of every producer's window.
    # Roaring bitmap is for the cardinality preview only (audit A3 fix); the
    # actual DELETE goes through the queryset so Postgres uses the indexed range scan.
    results["suggestion_impressions_deleted"] = _purge_with_bitmap_preview(
        queryset=SuggestionImpression.objects.filter(
            impressed_at__lt=now - timedelta(days=_RETENTION_3_MONTHS),
        ),
        use_bitmap=True,
        label="SuggestionImpression (B.5, 90 days)",
        step="suggestion_impression_purge",
        fix_hint="Check database connectivity and the suggestions.SuggestionImpression table.",
        preview_key=RETENTION_PREVIEW_KEY_IMPRESSIONS,
    )
    report(75.0, "Pruning IPW presentations (B.6)")
    # Joachims 2017 IPW reranker uses a 180-day presentation window for
    # exposure denominators; older rows can be pruned safely.
    results["suggestion_presentations_deleted"] = _purge_with_bitmap_preview(
        queryset=SuggestionPresentation.objects.filter(
            presented_date__lt=(now - timedelta(days=_RETENTION_6_MONTHS)).date(),
        ),
        use_bitmap=True,
        label="SuggestionPresentation (B.6, 180 days)",
        step="suggestion_presentation_purge",
        fix_hint="Check database connectivity and the suggestions.SuggestionPresentation table.",
        preview_key=RETENTION_PREVIEW_KEY_PRESENTATIONS,
    )
    report(90.0, "Pruning aged-out non-approved Suggestions (B.7)")
    # Approved / applied / verified Suggestions are the operator audit trail
    # and are NEVER purged. Pending / stale rows that aged out a year without
    # operator action are noise. UUID PK forbids the bitmap path (uint32-only)
    # so we use direct queryset .count() for the preview.
    results["non_approved_suggestions_deleted"] = _purge_with_bitmap_preview(
        queryset=Suggestion.objects.filter(
            status__in=("pending", "stale"),
            updated_at__lt=now - timedelta(days=_RETENTION_12_MONTHS),
        ),
        use_bitmap=False,
        label="Pending/stale Suggestion (B.7, 365 days)",
        step="non_approved_suggestion_purge",
        fix_hint="Check database connectivity and the suggestions.Suggestion table.",
        preview_key=RETENTION_PREVIEW_KEY_NON_APPROVED,
    )


def _persist_retention_preview(key: str, *, value: int, last_count: int) -> None:
    """Write ``key`` and ``key.last_count`` to AppSetting for the dashboard.

    *value* is the post-prune cardinality (always ~0 right after a
    successful prune); *last_count* is what the prune just acted on.
    The dashboard panel renders both — "0 rows pending now, last
    sweep deleted 12,480" — so the operator sees both freshness and
    historical volume at a glance.
    """
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": str(int(value)),
                "value_type": "int",
                "category": "retention",
                "description": "Retention queue cardinality (post-prune).",
            },
        )
        AppSetting.objects.update_or_create(
            key=f"{key}.last_count",
            defaults={
                "value": str(int(last_count)),
                "value_type": "int",
                "category": "retention",
                "description": "Rows the most recent prune actually deleted.",
            },
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("_persist_retention_preview(%s) failed: %s", key, exc)


def _persist_retention_run_timestamp(iso: str) -> None:
    """Write the last-run timestamp to AppSetting for the dashboard."""
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=RETENTION_PREVIEW_KEY_LAST_RUN_AT,
            defaults={
                "value": iso,
                "value_type": "str",
                "category": "retention",
                "description": "ISO-8601 timestamp of the last successful retention sweep.",
            },
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("_persist_retention_run_timestamp(%s) failed: %s", iso, exc)


@shared_task(name="pipeline.cleanup_stuck_sync_jobs")
@HelperConstraint(
    cpu_intensive=False,  # short DB-only sweep
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=64,
    expected_seconds_p50=10,
)
def cleanup_stuck_sync_jobs():
    """Mark SyncJob records that have been stuck in 'running' for over 2 hours as failed.

    This handles the case where the server was restarted or the laptop shut down
    mid-sync, leaving a job record that will never complete on its own.

    Scheduled daily at 03:30 UTC (after nightly_data_retention).
    """
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    from datetime import timedelta
    from django.utils import timezone
    from apps.sync.models import SyncJob

    cutoff = timezone.now() - timedelta(hours=2)
    stuck = SyncJob.objects.filter(status="running", started_at__lt=cutoff)
    count = stuck.count()
    if not count:
        logger.info("[cleanup_stuck_sync_jobs] No stuck jobs found.")
        return {"jobs_cleaned": 0}
    resumable_count, no_checkpoint_count = _mark_stuck_jobs_failed(
        stuck, timezone.now()
    )
    logger.info(
        "[cleanup_stuck_sync_jobs] Marked %d stuck job(s) as failed "
        "(%d resumable, %d need restart).",
        count,
        resumable_count,
        no_checkpoint_count,
    )
    return {"jobs_cleaned": count}


def _mark_stuck_jobs_failed(stuck_qs, now) -> tuple[int, int]:
    """Mark stuck jobs failed; return (resumable_count, no_checkpoint_count).

    Jobs with a checkpoint can resume from where they left off — flag
    is_resumable=True so the next import_content call picks up via the
    resume path. Jobs with no checkpoint must restart from scratch.
    """
    resumable_count = stuck_qs.exclude(checkpoint_stage="").update(
        status="failed",
        is_resumable=True,
        error_message=(
            "Job interrupted — server was likely restarted mid-sync. "
            "Resumable from last checkpoint."
        ),
        completed_at=now,
    )
    no_checkpoint_count = stuck_qs.filter(checkpoint_stage="").update(
        status="failed",
        is_resumable=False,
        error_message=(
            "Job timed out before any checkpoint — server was likely "
            "restarted mid-sync."
        ),
        completed_at=now,
    )
    return resumable_count, no_checkpoint_count


@shared_task(
    name="pipeline.sync_single_xf_item",
    time_limit=300,
    soft_time_limit=270,
    autoretry_for=(requests.RequestException, ConnectionError),
    max_retries=3,
    retry_backoff=60,
)
@HelperConstraint(
    cpu_intensive=False,  # network IO bound (XF API)
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=15,
)
def sync_single_xf_item(
    content_id: int, content_type: str = "thread", node_id: int | None = None
) -> dict:
    """Real-time sync for a single XenForo item (thread or resource) via webhook."""
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    from apps.pipeline.tasks import import_content

    logger.info(
        "Real-time sync triggered for %s %d (node/cat: %s)",
        content_type,
        content_id,
        node_id,
    )
    try:
        xf_node_id = _resolve_xf_node_id(content_id, content_type, node_id)
        if not xf_node_id:
            logger.error(
                "Could not determine node_id for %s %d",
                content_type,
                content_id,
            )
            return {"error": "Missing node_id"}
        scope = _ensure_scope_for_xf_node(xf_node_id, content_type)
        if not scope.is_enabled:
            logger.info(
                "Scope %s is disabled; skipping sync for %s %d",
                scope.title,
                content_type,
                content_id,
            )
            return {"status": "skipped", "reason": "scope disabled"}
        return import_content(scope_ids=[scope.pk], mode="full", source="api")
    except (DatabaseError, TimeoutError, MemoryError, ValueError) as e:
        logger.exception("Failed to sync single item %d", content_id)
        return {"error": str(e)}


def _resolve_xf_node_id(
    content_id: int,
    content_type: str,
    node_id: int | None,
) -> int | None:
    """Return ``node_id`` if supplied; otherwise look it up via the XenForo API."""
    if node_id:
        return node_id
    from apps.sync.services.xenforo_api import XenForoAPIClient

    client = XenForoAPIClient()
    if content_type == "thread":
        return client.get_thread(content_id).get("thread", {}).get("node_id")
    if content_type == "resource":
        return (
            client.get_resource_updates(content_id)  # hypothetical
            .get("resource", {})
            .get("resource_category_id")
        )
    return None


def _ensure_scope_for_xf_node(xf_node_id: int, content_type: str):
    """Get-or-create a ScopeItem for the resolved XenForo node/category id."""
    from apps.content.models import ScopeItem

    scope_type = "node" if content_type == "thread" else "resource_category"
    scope, _ = ScopeItem.objects.get_or_create(
        scope_id=xf_node_id,
        scope_type=scope_type,
        defaults={
            "title": f"Auto-discovered {scope_type} {xf_node_id}",
            "is_enabled": True,
        },
    )
    return scope


@shared_task(
    name="pipeline.sync_single_wp_item",
    time_limit=300,
    soft_time_limit=270,
    autoretry_for=(requests.RequestException, ConnectionError),
    max_retries=3,
    retry_backoff=60,
)
@HelperConstraint(
    cpu_intensive=False,  # network IO bound (WP REST API)
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=15,
)
def sync_single_wp_item(post_id: int, content_type: str = "post") -> dict:
    """Real-time sync for a single WordPress post/page via webhook."""
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

    from apps.core.views import get_wordpress_runtime_config
    from apps.sync.services.wordpress_api import WordPressAPIClient
    from apps.pipeline.tasks import import_content

    logger.info("Real-time sync triggered for WordPress %s %d", content_type, post_id)

    try:
        wp_config = get_wordpress_runtime_config()
        client = WordPressAPIClient(
            base_url=wp_config["base_url"],
            username=wp_config["username"],
            app_password=wp_config["app_password"],
        )

        # 1. Fetch item data to verify it exists
        if content_type == "page":
            item = client.get_page(post_id)
        else:
            item = client.get_post(post_id)

        if not item:
            return {"error": "Item not found"}

        # 2. Trigger import logic
        # For single items we always use "full" to ensure we get the body and embeddings
        return import_content(
            mode="full", source="wp", job_id=f"wp_single_{post_id}_{int(time.time())}"
        )

    except (DatabaseError, TimeoutError, MemoryError, ValueError) as e:
        logger.exception("Failed to sync single WP item %d", post_id)
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Import orchestration (restored stubs after refactoring)
# ──────────────────────────────────────────────────────────────────────────────
@shared_task(
    bind=True,
    name="pipeline.import_content",
    time_limit=7200,
    soft_time_limit=6900,
    # AutoIssue #20219: imports run up to 2 hours; a mid-run DB connection
    # drop must re-queue so the start-of-task close guard restores a fresh
    # connection on retry. Bounded at 3 retries with backoff.
    autoretry_for=(DatabaseError, InterfaceError, OperationalError),
    max_retries=3,
    retry_backoff=60,
)
@with_weight_lock("heavy")
@HelperConstraint(
    cpu_intensive=False,  # network IO plus existing post-import batch helpers
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=2048,
    expected_seconds_p50=1200,
)
def import_content(
    self,
    *,
    scope_ids: list[int] | None = None,
    mode: str = "full",
    source: str = "api",
    file_path: str | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, Any]:
    """Run a content import and record progress on the matching SyncJob."""
    if not connection.in_atomic_block:
        connection.close()

    job_id = job_id or str(uuid.uuid4())
    job = _start_import_job(
        job_id=job_id,
        source=source,
        mode=mode,
        file_path=file_path,
    )
    state = _build_import_state(
        job=job,
        job_id=job_id,
        source=source,
        mode=mode,
        force_reembed=force_reembed,
    )

    try:
        _publish_progress(job_id, "running", 0.0, "Starting content import.")
        _run_import_source(state, job, scope_ids=scope_ids, file_path=file_path)
        from apps.pipeline.tasks_import import (
            run_post_import_steps,
            update_scope_counts,
        )

        update_scope_counts(state.touched_scope_ids)
        run_post_import_steps(state, job, job_id, _publish_progress)
        _finish_import_job(job, state)
    except JobPaused as exc:
        _pause_import_job(job, exc)
        _publish_progress(job_id, "paused", 0.0, f"Import paused: {exc}")
        return _import_result(job, status="paused")
    except (RequestException, URLError, TimeoutError) as exc:
        _fail_import_job(job, exc, expected=True)
        _publish_progress(job_id, "failed", 0.0, f"Content import failed: {exc}")
        return _import_result(job, status="failed")
    except (DatabaseError, MemoryError, ValueError, SoftTimeLimitExceeded) as exc:
        _fail_import_job(job, exc)
        _publish_progress(job_id, "failed", 0.0, f"Content import failed: {exc}")
        raise

    _publish_progress(job_id, "completed", 1.0, "Content import complete.")
    return _import_result(job, status="completed")


def _start_import_job(
    *,
    job_id: str,
    source: str,
    mode: str,
    file_path: str | None,
):
    from django.utils import timezone
    from apps.sync.models import SyncJob

    job, _ = SyncJob.objects.get_or_create(
        job_id=job_id,
        defaults={
            "source": source,
            "mode": mode,
            "file_path": file_path or "",
            "status": "running",
            "started_at": timezone.now(),
            "message": "Import running.",
        },
    )
    job.source = source
    job.mode = mode
    job.file_path = file_path or job.file_path or ""
    job.status = "running"
    job.started_at = job.started_at or timezone.now()
    job.message = "Import running."
    job.save(
        update_fields=[
            "source",
            "mode",
            "file_path",
            "status",
            "started_at",
            "message",
            "updated_at",
        ]
    )
    return job


def _build_import_state(
    *,
    job,
    job_id: str,
    source: str,
    mode: str,
    force_reembed: bool,
):
    from apps.pipeline.tasks_import import ImportState

    resume_last_item_id = job.checkpoint_last_item_id if job.is_resumable else None
    resume_stage = job.checkpoint_stage if job.is_resumable else ""
    return ImportState(
        job_id=job_id,
        source=source,
        mode=mode,
        force_reembed=force_reembed,
        items_synced=job.checkpoint_items_processed if job.is_resumable else 0,
        resume_last_item_id=resume_last_item_id,
        resume_stage=resume_stage,
    )


def _run_import_source(
    state,
    job,
    *,
    scope_ids: list[int] | None,
    file_path: str | None,
) -> None:
    from apps.pipeline.tasks_import import (
        import_jsonl_content,
        import_wordpress_content,
        import_xenforo_scopes,
    )

    if state.source == "api":
        import_xenforo_scopes(state, job, scope_ids, _publish_progress)
        return
    if state.source == "wp":
        import_wordpress_content(state, job, _publish_progress)
        return
    if state.source == "jsonl":
        if not file_path:
            raise ValueError("JSONL imports require a saved file path.")
        import_jsonl_content(state, job, file_path)
        return
    raise ValueError(f"Unsupported import source: {state.source}")


def _finish_import_job(job, state) -> None:
    from django.utils import timezone

    job.status = "completed"
    job.progress = 100.0
    job.items_synced = state.items_synced
    job.items_updated = state.items_updated
    job.completed_at = timezone.now()
    job.message = "Import complete."
    job.error_message = ""
    job.is_resumable = False
    job.save(
        update_fields=[
            "status",
            "progress",
            "items_synced",
            "items_updated",
            "completed_at",
            "message",
            "error_message",
            "is_resumable",
            "updated_at",
        ]
    )


def _fail_import_job(job, exc: Exception, *, expected: bool = False) -> None:
    from django.utils import timezone

    if expected:
        logger.warning("Content import %s failed: %s", job.job_id, exc)
    else:
        logger.exception("Content import %s failed", job.job_id)
    job.status = "failed"
    job.completed_at = timezone.now()
    job.error_message = str(exc)
    job.message = "Import failed."
    job.save(
        update_fields=[
            "status",
            "completed_at",
            "error_message",
            "message",
            "updated_at",
        ]
    )


def _pause_import_job(job, exc: Exception) -> None:
    job.status = "paused"
    job.is_resumable = bool(job.checkpoint_stage or job.checkpoint_last_item_id)
    job.message = f"Import paused: {exc}"
    job.save(update_fields=["status", "is_resumable", "message", "updated_at"])


def _import_result(job, *, status: str) -> dict[str, Any]:
    return {
        "job_id": str(job.job_id),
        "status": status,
        "items_synced": job.items_synced,
        "items_updated": job.items_updated,
    }


def dispatch_import_content(
    *,
    scope_ids: list[int] | None = None,
    mode: str = "full",
    source: str = "api",
    file_path: str | None = None,
    job_id: str | None = None,
    force_reembed: bool = False,
) -> dict[str, Any]:
    """Dispatcher: enqueue an import job. Calls import_content task."""
    job_id = job_id or str(uuid.uuid4())
    import_content.apply_async(
        kwargs={
            "scope_ids": scope_ids,
            "mode": mode,
            "source": source,
            "file_path": file_path,
            "job_id": job_id,
            "force_reembed": force_reembed,
        }
    )
    return {"runtime_owner": "celery", "job_id": job_id}


# ──────────────────────────────────────────────────────────────────────────────
# Ranking recalculation tasks (stubs after refactoring)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(name="pipeline.recalculate_link_freshness", time_limit=1800)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
)
def recalculate_link_freshness():
    """Stub: recalculate link freshness scores."""
    logger.info("recalculate_link_freshness called (stub)")
    return {"status": "recalculation queued"}


@shared_task(name="pipeline.recalculate_weighted_authority", time_limit=1800)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
)
def recalculate_weighted_authority():
    """Stub: recalculate weighted authority scores."""
    logger.info("recalculate_weighted_authority called (stub)")
    return {"status": "recalculation queued"}


