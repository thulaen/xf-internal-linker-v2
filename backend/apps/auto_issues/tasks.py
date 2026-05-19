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
from django.db import connection

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
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Refresh the GlitchTip mirror, then promote top rows to auto_issues."""
    from apps.audit.tasks import sync_glitchtip_issues
    from apps.auto_issues.services.glitchtip_picker import pick_glitchtip_issues

    sync_result = sync_glitchtip_issues()
    pick_result = pick_glitchtip_issues()
    return {
        "glitchtip_sync": sync_result,
        "glitchtip_picker": pick_result,
    }


@shared_task(name="auto_issues.pick_daily_pyroscope_regressions")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
    expected_seconds_p50=90,
)
def pick_daily_pyroscope_regressions():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

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
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

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


@shared_task(name="auto_issues.pick_daily_faro_findings")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=192,
    expected_seconds_p50=30,
)
def pick_daily_faro_findings():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Query Loki for Faro browser RUM events; promote JS error clusters
    and Web Vitals (LCP/INP/CLS) breaches to AutoIssue.

    Added 2026-05-11 per plan
    ``~/.claude/plans/objective-deploy-and-integrate-zany-bee.md`` Stream 5.
    Two disjoint detectors run in one call: error_cluster (works from
    day one once Faro is shipping events) and webvital_breach (needs
    ≥10 sessions over threshold). Disjoint fingerprint prefixes
    (``faro:err::`` and ``faro:webvital::``) keep them from colliding
    on the AutoIssue unique constraint.
    """
    from apps.auto_issues.services.faro_picker import pick_faro_findings

    return pick_faro_findings()


@shared_task(name="auto_issues.pick_daily_tempo_findings")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=192,
    expected_seconds_p50=30,
)
def pick_daily_tempo_findings():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Query Tempo TraceQL for slow spans and error spans; promote both
    to AutoIssue.

    Added 2026-05-11 per plan
    ``~/.claude/plans/objective-deploy-and-integrate-zany-bee.md`` Stream 6.
    Slow-span detector groups by (span_name, service.name) and
    promotes p99 outliers above ``tempo.slow_span_threshold_ms``.
    Error-span detector groups by the same key and promotes any cluster
    over ``tempo.error_span_min_count``. Disjoint fingerprint prefixes
    (``tempo:slow::`` and ``tempo:err::``).
    """
    from apps.auto_issues.services.tempo_picker import pick_tempo_findings

    return pick_tempo_findings()


# ── Phase 6 of the test-hardening plan (2026-05-12) ──
# Five new pickers covering the new failure-signal sources.


@shared_task(name="auto_issues.pick_mutation_survivors")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=192,
    expected_seconds_p50=15,
)
def pick_mutation_survivors():
    """Read mutmut + Stryker + Mull JSON reports; upsert each surviving mutant."""
    connection.close()
    from apps.auto_issues.services.mutation import pick_mutation_survivors as _run
    return _run()


@shared_task(name="auto_issues.pick_fuzz_crashes")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=10,
)
def pick_fuzz_crashes():
    """Scan backend/extensions/fuzz/ for libFuzzer reproducers; upsert each."""
    connection.close()
    from apps.auto_issues.services.fuzz import pick_fuzz_crashes as _run
    return _run()


@shared_task(name="auto_issues.pick_lint_errors")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=192,
    expected_seconds_p50=20,
)
def pick_lint_errors():
    """Read Super-Linter SARIF; upsert each finding above min severity."""
    connection.close()
    from apps.auto_issues.services.lint_error import pick_lint_errors as _run
    return _run()


@shared_task(name="auto_issues.pick_contract_drift")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=15,
)
def pick_contract_drift():
    """Read Pact provider-verification JSON; upsert each failed interaction."""
    connection.close()
    from apps.auto_issues.services.contract_drift import pick_contract_drift as _run
    return _run()


@shared_task(name="auto_issues.pick_ci_failed_runs")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=10,
)
def pick_ci_failed_runs():
    """Shell `gh run list --status failure --limit 10`; upsert each run."""
    connection.close()
    from apps.auto_issues.services.ci_failed_runs import pick_ci_failed_runs as _run
    return _run()


@shared_task(name="auto_issues.run_retention_cleanup")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=128, expected_seconds_p50=120,
)
def run_retention_cleanup():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """90-day data retention across Pyroscope + audit_errorlog + auto_issues."""
    from apps.auto_issues.services.retention_cleanup import run_retention_cleanup as _run

    return _run()


@shared_task(name="auto_issues.pick_disk_pressure")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=64, expected_seconds_p50=2,
)
def pick_disk_pressure():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Hourly disk-fill probe → AutoIssue."""
    from apps.auto_issues.services.disk_pressure_picker import pick_disk_pressure as _pick

    return _pick()


@shared_task(name="auto_issues.pick_slo_probes")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=64, expected_seconds_p50=10,
)
def pick_slo_probes():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Synthetic SLO probes → AutoIssue (15-min cadence)."""
    from apps.auto_issues.services.slo_probe_picker import pick_slo_probes as _pick

    return _pick()


@shared_task(name="auto_issues.pick_missed_runs")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=128, expected_seconds_p50=5,
)
def pick_missed_runs():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Schedule-tracker missed-runs → AutoIssue (daily)."""
    from apps.auto_issues.services.missed_runs_picker import pick_missed_runs as _pick

    return _pick()


@shared_task(name="auto_issues.pick_deploy_check_findings")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=128, expected_seconds_p50=15,
)
def pick_deploy_check_findings():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    """Django check --deploy → AutoIssue (weekly)."""
    from apps.auto_issues.services.deploy_check_picker import pick_deploy_check_findings as _pick

    return _pick()


@shared_task(name="auto_issues.pick_output_quality")
@HelperConstraint(
    cpu_intensive=False, gpu_required=False,
    storage_writes_to="postgres_main", ram_peak_mb=256, expected_seconds_p50=30,
)
def pick_output_quality():
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

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
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

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
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

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
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

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
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    if not connection.in_atomic_block:
        connection.close()

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
