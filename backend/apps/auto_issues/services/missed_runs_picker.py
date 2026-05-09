"""Schedule-tracker missed-runs → AutoIssue picker.

Closes Gap #7 from `docs/OBSERVABILITY-GAPS-EXTENSION.md`. The
`apps.scheduled_updates` app already detects missed/failed/stalled
Celery beat dispatches and writes them to the `JobAlert` table. This
picker reads recent unacknowledged + unresolved alerts and surfaces
them in `auto_issues` so they land in the same agent-readable feed as
GlitchTip + Pyroscope + slow-query findings — no operator has to
remember to check a separate "Alerts" page.

Cross-source dedup via `services.dedup.upsert_dedup` — same
`(job_key, alert_type)` → stable canonical fingerprint, so a job that
misses its window every day for a week ends up as ONE AutoIssue row
with 7 entries in `source_observations`, not 7 separate rows.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 7
_MAX_PER_RUN = 25


def _severity_for(alert_type: str) -> str:
    if alert_type == "failed":
        return AutoIssue.SEVERITY_HIGH
    if alert_type == "stalled":
        return AutoIssue.SEVERITY_MEDIUM
    # Missed window — usually means the laptop was off. Lower urgency.
    return AutoIssue.SEVERITY_LOW


def _fetch_active_alerts():
    """Recent unacknowledged + unresolved JobAlert rows."""
    from apps.scheduled_updates.models import JobAlert

    cutoff = timezone.now() - timedelta(days=_LOOKBACK_DAYS)
    return list(
        JobAlert.objects.filter(
            acknowledged_at__isnull=True,
            resolved_at__isnull=True,
            last_seen_at__gte=cutoff,
        ).order_by("-last_seen_at")[:_MAX_PER_RUN]
    )


def _upsert_missed_run(alert) -> str:
    title = (
        f"Schedule-tracker: job `{alert.job_key}` {alert.alert_type} "
        f"({alert.calendar_date.isoformat()})"
    )
    description = (
        f"The scheduled job `{alert.job_key}` was flagged as "
        f"`{alert.alert_type}` on {alert.calendar_date.isoformat()}. "
        f"`apps.scheduled_updates.JobAlert` keeps one row per "
        f"`(job_key, alert_type, calendar_date)`; this AutoIssue is the "
        f"corresponding cross-source dedup row.\n\n"
        f"Three alert types this picker surfaces:\n"
        f"  - missed: scheduled run window passed without dispatch.\n"
        f"  - failed: job ran but raised an exception.\n"
        f"  - stalled: job started but never reported completion.\n\n"
        f"To resolve manually: open the Alerts UI on the Scheduled "
        f"Updates page and click the ✕, OR fix the root cause and the "
        f"next successful run will auto-clear it."
    )
    canonical = canonical_fingerprint(
        f"missed-run::{alert.job_key}::{alert.alert_type}", ""
    )
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"missed-{alert.job_key}-{alert.alert_type}",
        fingerprint=f"missed-{alert.job_key}-{alert.alert_type}",
        title=title,
        description=description,
        affected_files=["backend/apps/scheduled_updates/", "backend/config/settings/celery_schedules.py"],
        severity=_severity_for(alert.alert_type),
        priority_score=0.6 if alert.alert_type == "failed" else 0.35,
        occurrence_count=1,
    )
    return outcome


def pick_missed_runs() -> dict:
    """Top-K active JobAlert rows → AutoIssue (with cross-source dedup)."""
    alerts = _fetch_active_alerts()
    if not alerts:
        return {
            "status": "ok",
            "alerts": 0,
            "promoted": 0,
            "created": 0,
            "merged": 0,
            "updated": 0,
        }
    counts = {"created": 0, "merged": 0, "updated": 0}
    for alert in alerts:
        outcome = _upsert_missed_run(alert)
        counts[outcome] = counts.get(outcome, 0) + 1
    logger.info(
        "[auto_issues.missed_runs_picker] alerts=%d created=%d merged=%d updated=%d",
        len(alerts), counts["created"], counts["merged"], counts["updated"],
    )
    return {
        "status": "ok",
        "alerts": len(alerts),
        "promoted": sum(counts.values()),
        **counts,
    }
