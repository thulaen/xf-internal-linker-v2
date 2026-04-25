"""Celery task: fortnightly embedding-accuracy audit (plan Part 3, FR-231).

Runs on the ``pipeline`` queue (concurrency=1) so it naturally yields to other
Heavy/Medium work. Fortnight-gated via AppSetting so Beat double-dispatches
are trivially idempotent. Re-embeds only the flagged PK subset via the
existing ``generate_all_embeddings`` — zero duplicate writes (signature filter).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="pipeline.embedding_accuracy_audit",
    queue="pipeline",
    soft_time_limit=60 * 60,   # 1h soft
    time_limit=60 * 60 + 300,  # hard + 5m grace
    max_retries=0,
)
def embedding_accuracy_audit(self, *, fortnightly: bool = True, force: bool = False):
    """Scan + flag + re-embed drifted ContentItem vectors.

    Args:
        fortnightly: Enforce the 13-day gate. Tests / manual runs set False.
        force: Bypass all gates (manual 'Run audit now' from the UI).
    """
    from apps.pipeline.services.embedding_audit import (
        get_last_run_at,
        get_thresholds,
        is_audit_enabled,
        scan_embedding_health,
        set_last_run_at,
        write_diagnostic,
    )

    if not force and not is_audit_enabled():
        logger.info("embedding_accuracy_audit disabled via AppSetting; exiting")
        return {"skipped": "disabled"}

    if fortnightly and not force:
        last = get_last_run_at()
        if last and (timezone.now() - last) < timedelta(days=13):
            logger.info("fortnight gate: last run %s; skipping", last.isoformat())
            return {"skipped": "fortnight_gate"}

    # Window gate (operator window per apps/scheduled_updates/window.py and
    # docs/PERFORMANCE.md §5) — only enforced in fortnightly mode so manual
    # runs are never blocked. Source of truth is the constants in
    # apps.scheduled_updates.window — keep this gate aligned there.
    if fortnightly and not force:
        from apps.scheduled_updates.window import (
            WINDOW_END_HOUR,
            WINDOW_START_HOUR,
        )

        now_utc = timezone.now().utctimetuple()
        if not (WINDOW_START_HOUR <= now_utc.tm_hour < WINDOW_END_HOUR):
            logger.info(
                "outside %02d:00-%02d:59 UTC window (hour=%d); deferring 5min",
                WINDOW_START_HOUR,
                WINDOW_END_HOUR - 1,
                now_utc.tm_hour,
            )
            raise self.retry(countdown=300)

    from apps.pipeline.services.embeddings import (
        generate_all_embeddings,
        get_current_embedding_dimension,
        get_current_embedding_signature,
    )

    current_sig = get_current_embedding_signature()
    current_dim = get_current_embedding_dimension()
    norm_tol, drift_thr, resample_sz = get_thresholds()

    report = scan_embedding_health(
        current_signature=current_sig,
        current_dimension=current_dim,
        norm_tolerance=norm_tol,
        drift_threshold=drift_thr,
        resample_size=resample_sz,
    )
    logger.info("embedding_accuracy_audit report=%s", report.as_dict())
    write_diagnostic(run_id=self.request.id, report=report)

    # Re-embed only the flagged PKs. generate_all_embeddings honours the
    # existing signature filter, so already-fresh items are skipped even if
    # they appear in the list.
    if report.flagged_pks:
        try:
            generate_all_embeddings(
                report.flagged_pks,
                job_id=self.request.id,
                force_reembed=False,
            )
        except Exception:
            logger.exception("Re-embed of flagged items failed")

    set_last_run_at(timezone.now())
    return report.as_dict()
