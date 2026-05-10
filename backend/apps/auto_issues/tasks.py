"""Celery tasks for the issue picker chain.

Tasks:
  - ``pick_daily_glitchtip_issues`` — promote top GT-mirror rows.
  - ``pick_daily_pyroscope_regressions`` — surface CPU regressions
    AND same-day hotspots (added 2026-05-10).
  - ``close_stale_issues`` — auto-defer rows idle ≥30 days under 0.3 score.

Schedules (UTC) live in ``backend/config/settings/celery_schedules.py``.
The pickers run every 30 min during the active-laptop window 11-23 UTC
so session-start sees fresh data; staggered :05/:35 (GT) and :10/:40
(Pyroscope) so they don't fight Postgres.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)


@shared_task(name="auto_issues.pick_daily_glitchtip_issues")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=15,
)
def pick_daily_glitchtip_issues():
    """Read the audit_errorlog mirror, score top-K, write to auto_issues."""
    from apps.auto_issues.services.glitchtip_picker import pick_glitchtip_issues

    return pick_glitchtip_issues()


@shared_task(name="auto_issues.pick_daily_pyroscope_regressions")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=90,
)
def pick_daily_pyroscope_regressions():
    """Query Pyroscope for both week-over-week regressions and same-day
    hotspots; write both to auto_issues.

    Hotspot detection added 2026-05-10 per plan
    ``does-adding-qodana-make-swift-wall.md`` Stream 2 — needed because
    week-over-week regressions need 7 days of profile history, leaving
    Pyroscope-source AutoIssues empty during the warmup. Hotspots work
    from day one. The two detectors use disjoint fingerprint prefixes
    so they never collide on the unique constraint.
    """
    from apps.auto_issues.services.pyroscope_picker import (
        pick_pyroscope_hotspots,
        pick_pyroscope_regressions,
    )

    regressions = pick_pyroscope_regressions()
    hotspots = pick_pyroscope_hotspots()
    return {"regressions": regressions, "hotspots": hotspots}


@shared_task(name="auto_issues.pick_daily_loki_findings")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=192,
    expected_seconds_p50=45,
)
def pick_daily_loki_findings():
    """Query Loki for hot patterns + WARN/ERROR rate bursts; write to auto_issues.

    Added 2026-05-10 per plan
    ``does-adding-qodana-make-swift-wall.md`` Stream 4. Two disjoint
    detectors run in one call: hot_pattern (works from day one) and
    warn_burst (needs ≥24 h of baseline). The two use disjoint
    fingerprint prefixes (``loki:hot::`` and ``loki:burst::``) so they
    never collide on the AutoIssue unique constraint.
    """
    from apps.auto_issues.services.loki_picker import pick_loki_findings

    return pick_loki_findings()


@shared_task(name="auto_issues.run_retention_cleanup")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=128, expected_seconds_p50=120,
)
def run_retention_cleanup():
    """90-day data retention across Pyroscope + audit_errorlog + auto_issues."""
    from apps.auto_issues.services.retention_cleanup import run_retention_cleanup as _run

    return _run()


@shared_task(name="auto_issues.pick_disk_pressure")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=64, expected_seconds_p50=2,
)
def pick_disk_pressure():
    """Hourly disk-fill probe → AutoIssue."""
    from apps.auto_issues.services.disk_pressure_picker import pick_disk_pressure as _pick

    return _pick()


@shared_task(name="auto_issues.pick_slo_probes")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=64, expected_seconds_p50=10,
)
def pick_slo_probes():
    """Synthetic SLO probes → AutoIssue (15-min cadence)."""
    from apps.auto_issues.services.slo_probe_picker import pick_slo_probes as _pick

    return _pick()


@shared_task(name="auto_issues.pick_missed_runs")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=128, expected_seconds_p50=5,
)
def pick_missed_runs():
    """Schedule-tracker missed-runs → AutoIssue (daily)."""
    from apps.auto_issues.services.missed_runs_picker import pick_missed_runs as _pick

    return _pick()


@shared_task(name="auto_issues.pick_deploy_check_findings")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=128, expected_seconds_p50=15,
)
def pick_deploy_check_findings():
    """Django check --deploy → AutoIssue (weekly)."""
    from apps.auto_issues.services.deploy_check_picker import pick_deploy_check_findings as _pick

    return _pick()


@shared_task(name="auto_issues.pick_output_quality")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=256, expected_seconds_p50=30,
)
def pick_output_quality():
    """Output-quality probes → AutoIssue (daily)."""
    from apps.auto_issues.services.output_quality_picker import pick_output_quality as _pick

    return _pick()


@shared_task(name="auto_issues.pick_weekly_pip_audit_findings")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=180,
)
def pick_weekly_pip_audit_findings():
    """Weekly dependency CVE scan via pip-audit → AutoIssue.

    Closes a gap GlitchTip + Pyroscope + pg_stat_statements all miss:
    known security vulnerabilities in installed Python packages. Each
    CVE becomes one AutoIssue row, deduped across weeks via stable
    `(package, cve_id)` canonical fingerprint.
    """
    from apps.auto_issues.services.pip_audit_picker import pick_pip_audit_findings

    return pick_pip_audit_findings()


@shared_task(name="auto_issues.pick_daily_slow_queries")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=5,
)
def pick_daily_slow_queries():
    """Top-K slow queries from `pg_stat_statements` → auto_issues.

    Closes a gap that GlitchTip + Pyroscope miss: queries that get
    progressively slower without raising an exception. The picker reads
    the pg_stat_statements view (extension preloaded via postgres.conf)
    and surfaces queries with mean exec time over 100 ms, ranked by
    total time.
    """
    from apps.auto_issues.services.slow_query_picker import pick_slow_queries

    return pick_slow_queries()


@shared_task(name="auto_issues.pick_daily_internal_issues")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=15,
)
def pick_daily_internal_issues():
    """Promote top in-app `audit_errorlog` (source='internal') rows into auto_issues.

    Closes the source-coverage gap: errors caught in-process by
    `apps.audit.error_ingest.ingest_error()` (Celery failures, FAISS init,
    etc.) now flow into `auto_issues` alongside GlitchTip + Pyroscope.
    Cross-source dedup keeps duplicates out — same root cause from
    multiple sources lands on ONE row with `source_observations` listing
    all the sources that observed it.
    """
    from apps.auto_issues.services.internal_picker import pick_internal_issues

    return pick_internal_issues()


@shared_task(name="auto_issues.close_stale_issues")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=5,
)
def close_stale_issues():
    """Auto-defer rows idle ≥30 days under 0.3 priority score.

    SPEC § Anti-bloat — bounded growth guarantee. Re-running is safe
    (idempotent — already-deferred rows are skipped).
    """
    from apps.auto_issues.models import AutoIssue
    from apps.auto_issues.services.scoring import auto_close_stale_threshold

    idle_delta, score_floor = auto_close_stale_threshold()
    cutoff = timezone.now() - idle_delta
    qs = AutoIssue.objects.filter(
        status__in=(AutoIssue.STATUS_OPEN, AutoIssue.STATUS_PICKED),
        last_seen__lt=cutoff,
        priority_score__lt=score_floor,
    )
    closed = qs.update(
        status=AutoIssue.STATUS_DEFERRED,
        resolved_at=timezone.now(),
        resolved_by="auto-stale",
    )
    logger.info("[auto_issues.close_stale_issues] closed=%d", closed)
    return {"status": "ok", "closed": closed}
