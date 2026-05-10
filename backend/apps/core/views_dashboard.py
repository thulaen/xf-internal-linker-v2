"""
Dashboard, Today-Actions, Status-Story, Resume-State, and Mission-Brief
view layer extracted from ``apps/core/views.py``.

Why this file exists
--------------------
``apps/core/views.py`` was the historical home of every view in the
core app and grew well past the 1500-line cap that ``CLAUDE.md`` (Code
Quality Mandate) targets. The first slice (2026-05-10) moved the
per-feature settings views into ``views_settings.py``; the second
slice moved the runtime / system-metrics / safe-mode views into
``views_runtime.py``. This is the **third** slice — the dashboard /
today-actions / what-changed / resume-state / status-story /
mission-brief view classes plus the small per-section helpers they
rely on exclusively.

Behaviour preserved exactly
---------------------------
This is a pure mechanical refactor. No request shape, validation rule,
or response payload changed. The original ``apps.core.views`` module
re-exports every class and helper defined in this file at the end of
``views.py`` so existing importers (``apps/core/urls.py``,
``apps/core/tests_dashboard_helpers.py``, ``apps/core/views_mcp.py``,
``backend/mcp_server.py``, etc.) keep working unchanged via the
``from apps.core.views import …`` path they already use.

Helpers that remain in views.py (e.g. ``_safe_confidence_snapshot``,
``recommended_bool``-driven settings, ``get_*_settings``, etc.) are
reused by other view families that did not move out, so they stay
where they are. This file only owns the helpers used solely by the
dashboard / today-view / status-story / resume-state / mission-brief
view classes — and the few module-level constants (the
priority-rule thresholds in seconds/days for the today-actions waterfall)
that are exclusive to this layer.
"""

from __future__ import annotations

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.suggestions.recommended_weights import recommended_bool

logger = logging.getLogger(__name__)


class DashboardView(APIView):
    """
    GET /api/dashboard/

    Returns aggregated stats for the dashboard:
    - suggestion counts by status
    - total content items
    - last completed sync job
    - recent pipeline runs (last 5)
    - recent import jobs (last 5)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Aggregate every dashboard panel into one Response.

        Refactored 2026-05-04: was a 175-line monolith. Now delegates
        every panel to a per-section helper (``_dashboard_*``) so each
        piece is independently testable and the handler reads top-down
        like documentation. Behaviour preserved exactly.
        """
        # Local import — ``_safe_confidence_snapshot`` still lives in
        # ``apps.core.views`` because it is reused outside the dashboard
        # surface. Importing it lazily here avoids the circular import
        # that would otherwise fire at module-load time (views.py
        # imports from views_dashboard.py at the bottom of its file).
        from apps.core.views import _safe_confidence_snapshot

        return Response(
            {
                "suggestion_counts": _dashboard_suggestion_counts(),
                "content_count": _dashboard_content_count(),
                "open_broken_links": _dashboard_open_broken_links(),
                "last_sync": _dashboard_last_completed_sync(),
                "pipeline_runs": _dashboard_recent_pipeline_runs(),
                "recent_imports": _dashboard_recent_imports(),
                "system_health": _dashboard_system_health(),
                **_dashboard_freshness_timestamps(),
                "runtime_mode": _dashboard_runtime_mode_display(),
                "show_quick_controls": recommended_bool(
                    "dashboard.show_quick_controls"
                ),
                # Phase 4.3 — Confidence Meter "Ready to Rock" snapshot.
                # Cached 60 s in Redis so the dashboard read is cheap.
                # Falls back to None on any failure so the chip just
                # hides instead of breaking the dashboard.
                "confidence": _safe_confidence_snapshot(),
            }
        )


# ── Dashboard panel helpers ──────────────────────────────────────
# Extracted from DashboardView.get to keep that handler under the
# 50-line lint budget AND make each panel independently testable.


def _dashboard_suggestion_counts() -> dict[str, int]:
    """Phase 2.18 — read from the matview (with live-ORM fallback).

    Returns a dict shaped for the frontend with every status the UI
    knows about, even when the count is 0 — so downstream JS doesn't
    need null-checks.
    """
    from apps.core.services.dashboard_aggregates import (
        get_suggestion_status_counts,
    )

    counts = get_suggestion_status_counts()
    return {
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "applied": counts.get("applied", 0),
        "total": sum(counts.values()),
    }


def _dashboard_content_count() -> int:
    from apps.content.models import ContentItem

    return ContentItem.objects.count()


def _dashboard_open_broken_links() -> int:
    from apps.graph.models import BrokenLink

    return BrokenLink.objects.filter(status="open").count()


def _dashboard_last_completed_sync():
    from apps.sync.models import SyncJob

    return (
        SyncJob.objects.filter(status="completed")
        .values("completed_at", "source", "mode", "items_synced")
        .order_by("-completed_at")
        .first()
    )


def _dashboard_recent_pipeline_runs() -> list[dict]:
    """Last 5 pipeline runs with stringified IDs + duration display."""
    from apps.suggestions.models import PipelineRun

    runs = list(
        PipelineRun.objects.values(
            "run_id",
            "run_state",
            "rerun_mode",
            "suggestions_created",
            "destinations_processed",
            "duration_seconds",
            "created_at",
        ).order_by("-created_at")[:5]
    )
    for run in runs:
        run["run_id"] = str(run["run_id"])
        if run["created_at"]:
            run["created_at"] = run["created_at"].isoformat()
        ds = run.pop("duration_seconds")
        if ds is not None:
            minutes, seconds = divmod(int(ds), 60)
            run["duration_display"] = (
                f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            )
        else:
            run["duration_display"] = None
    return runs


def _dashboard_recent_imports() -> list[dict]:
    """Last 5 SyncJob rows with stringified IDs + ISO timestamps."""
    from apps.sync.models import SyncJob

    jobs = list(
        SyncJob.objects.values(
            "job_id",
            "status",
            "source",
            "mode",
            "items_synced",
            "created_at",
            "completed_at",
        ).order_by("-created_at")[:5]
    )
    for job in jobs:
        job["job_id"] = str(job["job_id"])
        if job["created_at"]:
            job["created_at"] = job["created_at"].isoformat()
        if job["completed_at"]:
            job["completed_at"] = job["completed_at"].isoformat()
    return jobs


def _dashboard_system_health() -> dict:
    """Aggregate per-status counts + overall verdict from health records."""
    from django.db.models import Count

    from apps.health.models import ServiceHealthRecord

    records = ServiceHealthRecord.objects.all()
    status_counts = records.values("status").annotate(count=Count("status"))
    summary = {row["status"]: row["count"] for row in status_counts}
    return {
        "status": _dashboard_overall_health_status(records),
        "summary": summary,
        "total_monitored": records.count(),
    }


def _dashboard_overall_health_status(records) -> str:
    """Pure function: pick the worst severity present across health records."""
    from apps.health.models import ServiceHealthRecord

    if any(r.status == ServiceHealthRecord.STATUS_DOWN for r in records):
        return ServiceHealthRecord.STATUS_DOWN
    if any(
        r.status in (ServiceHealthRecord.STATUS_ERROR, ServiceHealthRecord.STATUS_STALE)
        for r in records
    ):
        return ServiceHealthRecord.STATUS_ERROR
    if any(r.status == ServiceHealthRecord.STATUS_WARNING for r in records):
        return ServiceHealthRecord.STATUS_WARNING
    return ServiceHealthRecord.STATUS_HEALTHY


def _dashboard_freshness_timestamps() -> dict[str, str | None]:
    """Three ISO timestamps for the dashboard's freshness ribbon."""
    from apps.suggestions.models import PipelineRun
    from apps.sync.models import SyncJob

    last_sync = (
        SyncJob.objects.filter(status="completed")
        .values_list("completed_at", flat=True)
        .order_by("-completed_at")
        .first()
    )
    last_pipeline = (
        PipelineRun.objects.filter(run_state="completed")
        .values_list("updated_at", flat=True)
        .order_by("-updated_at")
        .first()
    )
    last_analytics = _dashboard_last_analytics_completed_at()
    return {
        "last_sync_at": last_sync.isoformat() if last_sync else None,
        "last_pipeline_at": last_pipeline.isoformat() if last_pipeline else None,
        "last_analytics_at": last_analytics.isoformat() if last_analytics else None,
    }


def _dashboard_last_analytics_completed_at():
    """Defensive: returns the last GSC sync timestamp or None.

    The GSC analytics model isn't shipped in every install (older
    deployments + minimal configurations); a missing import is normal
    and should not break the dashboard.
    """
    try:
        from apps.analytics.models import GSCSyncRun

        return (
            GSCSyncRun.objects.filter(status="completed")
            .values_list("completed_at", flat=True)
            .order_by("-completed_at")
            .first()
        )
    except Exception:  # noqa: BLE001 — analytics module is optional; missing-import is documented behaviour.
        logger.debug("GSCSyncRun model not available, skipping analytics freshness")
        return None


def _dashboard_runtime_mode_display() -> str:
    """Live effective device (CPU / GPU) — uppercase for the dashboard chip."""
    try:
        from apps.pipeline.services.embeddings import (
            get_effective_runtime_resolution,
        )

        return get_effective_runtime_resolution()["effective_runtime_mode"].upper()
    except Exception:  # noqa: BLE001 — embeddings module unavailable on cold start; CPU is the safe default.
        logger.debug("Embedding runtime unavailable, using default runtime_mode")
        return "CPU"


# ---------------------------------------------------------------------------
# Dashboard operating desk endpoints (Stage 3)
# ---------------------------------------------------------------------------


# ── TodayActionsView priority-rule helpers ──────────────────────
# Each rule is a pure function returning ``list[dict]`` of action items.
# Splitting per rule means each can be unit-tested + a future operator
# tweak (e.g. "raise pending-review threshold to 50") touches one
# place, not an inline-mixed-with-others block.

_PENDING_REVIEW_THRESHOLD = 20
_STALE_SYNC_HOURS = 48
_STALE_PIPELINE_DAYS = 14


def _today_actions_urgent_alerts() -> list[dict]:
    """Top-3 unread urgent / error OperatorAlerts."""
    from apps.notifications.models import OperatorAlert

    alerts = OperatorAlert.objects.filter(
        status="unread", severity__in=["urgent", "error"]
    ).order_by("-first_seen_at")[:3]
    return [
        {
            "title": alert.title,
            "reason": (
                f"Unresolved {alert.severity} alert since "
                f"{alert.first_seen_at:%b %d}"
            ),
            "route": f"/alerts/{alert.alert_id}",
            "severity": alert.severity,
            "isBlocking": alert.severity == "urgent",
        }
        for alert in alerts
    ]


def _today_actions_sync_freshness(now) -> list[dict]:
    """Stale-sync (>48h) or no-sync-yet warning."""
    from apps.sync.models import SyncJob

    last_sync = (
        SyncJob.objects.filter(status="completed").order_by("-completed_at").first()
    )
    if last_sync is None:
        return [
            {
                "title": "No content synced yet",
                "reason": "Run your first content sync to get started.",
                "route": "/jobs",
                "severity": "warning",
                "isBlocking": False,
            }
        ]
    if not last_sync.completed_at:
        return []
    hours_since = (now - last_sync.completed_at).total_seconds() / 3600
    if hours_since <= _STALE_SYNC_HOURS:
        return []
    days = int(hours_since // 24)
    return [
        {
            "title": "Content is getting stale",
            "reason": (
                f"Last sync was {days} days ago. Run a fresh sync to "
                "catch new content."
            ),
            "route": "/jobs",
            "severity": "warning",
            "isBlocking": False,
        }
    ]


def _today_actions_pending_suggestions() -> list[dict]:
    """Pending-review backlog warning when the queue exceeds the threshold."""
    from apps.suggestions.models import Suggestion

    pending_count = Suggestion.objects.filter(status="pending").count()
    if pending_count <= _PENDING_REVIEW_THRESHOLD:
        return []
    return [
        {
            "title": f"{pending_count} suggestions waiting for review",
            "reason": (
                "Review and approve link suggestions to improve your "
                "internal linking."
            ),
            "route": "/review",
            "severity": "info",
            "isBlocking": False,
        }
    ]


def _today_actions_pipeline_freshness(now) -> list[dict]:
    """Stale-pipeline + zero-suggestion-on-last-run warnings (one or both)."""
    from apps.suggestions.models import PipelineRun

    last_run = (
        PipelineRun.objects.filter(run_state="completed")
        .order_by("-updated_at")
        .first()
    )
    if last_run is None:
        return []
    actions: list[dict] = []
    if last_run.updated_at and (now - last_run.updated_at).days > _STALE_PIPELINE_DAYS:
        days_since = (now - last_run.updated_at).days
        actions.append(
            {
                "title": "Pipeline hasn't run in a while",
                "reason": (
                    f"Last pipeline run was {days_since} days ago. Run "
                    "it to generate fresh suggestions."
                ),
                "route": "/jobs",
                "severity": "info",
                "isBlocking": False,
            }
        )
    if last_run.suggestions_created == 0:
        actions.append(
            {
                "title": "Last pipeline produced no suggestions",
                "reason": ("Check your settings — the pipeline may need tuning."),
                "route": "/settings",
                "deepLinkTarget": "ranking-weights",
                "severity": "warning",
                "isBlocking": False,
            }
        )
    return actions


class TodayActionsView(APIView):
    """GET /api/dashboard/today-actions/

    Returns up to 5 priority-ranked action items for the current day.
    Priority waterfall: blocking alert > stale sync > pending review > idle.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return up to 5 priority-ranked action items for the operator.

        Refactored 2026-05-04: was 98 lines walking 5 distinct rule
        blocks inline. Now each rule is its own pure function returning
        ``list[dict]``; the handler concatenates + caps at 5. Each rule
        is independently testable.
        """
        from django.utils import timezone

        now = timezone.now()
        actions: list[dict] = []
        actions.extend(_today_actions_urgent_alerts())
        actions.extend(_today_actions_sync_freshness(now))
        actions.extend(_today_actions_pending_suggestions())
        actions.extend(_today_actions_pipeline_freshness(now))
        return Response(actions[:5])


class WhatChangedView(APIView):
    """GET /api/dashboard/what-changed/

    Returns counts of changes in the last 24 hours plus autotuner outcomes.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta

        since = timezone.now() - timedelta(hours=24)
        return Response(
            {
                "period_hours": 24,
                **_today_summary_counts(since),
                "autotuner_outcome": _today_autotuner_outcome(since),
            }
        )


def _today_summary_counts(since) -> dict[str, int]:
    """Counts of suggestions / reviews / sync items / pipeline runs since ``since``."""
    from apps.suggestions.models import PipelineRun, Suggestion
    from apps.sync.models import SyncJob

    synced_items = SyncJob.objects.filter(
        status="completed",
        completed_at__gte=since,
    ).values_list("items_synced", flat=True)
    return {
        "new_suggestions": Suggestion.objects.filter(created_at__gte=since).count(),
        "reviewed": Suggestion.objects.filter(reviewed_at__gte=since).count(),
        "items_synced": sum(synced_items),
        "pipeline_runs": PipelineRun.objects.filter(created_at__gte=since).count(),
    }


def _today_autotuner_outcome(since) -> dict | None:
    """Most-recent challenger promoted/rolled-back since ``since``; None if none."""
    try:
        from apps.suggestions.models import RankingChallenger
    except Exception:
        logger.debug(
            "RankingChallenger model not available, skipping autotuner outcome"
        )
        return None
    recent_challenger = (
        RankingChallenger.objects.filter(updated_at__gte=since)
        .exclude(status="pending")
        .order_by("-updated_at")
        .first()
    )
    if recent_challenger is None:
        return None
    return {
        "status": recent_challenger.status,
        "label": (
            recent_challenger.label
            if hasattr(recent_challenger, "label")
            else str(recent_challenger.pk)
        ),
        "updated_at": recent_challenger.updated_at.isoformat(),
    }


# ── ResumeStateView helpers (extracted from .get) ────────────────


def _resume_view_interrupted_runs() -> list[dict]:
    """Top-3 pipeline runs still in 'running' state (likely interrupted)."""
    from apps.suggestions.models import PipelineRun

    runs = list(
        PipelineRun.objects.filter(run_state="running")
        .values("run_id", "run_state", "created_at", "updated_at")
        .order_by("-created_at")[:3]
    )
    for run in runs:
        run["run_id"] = str(run["run_id"])
        if run["created_at"]:
            run["created_at"] = run["created_at"].isoformat()
        if run["updated_at"]:
            run["updated_at"] = run["updated_at"].isoformat()
    return runs


def _resume_view_resumable_syncs() -> list[dict]:
    """Top-3 sync jobs flagged resumable + not yet completed."""
    from apps.sync.models import SyncJob

    jobs = list(
        SyncJob.objects.filter(is_resumable=True)
        .exclude(status="completed")
        .values(
            "job_id",
            "status",
            "source",
            "mode",
            "checkpoint_stage",
            "checkpoint_items_processed",
        )
        .order_by("-created_at")[:3]
    )
    for job in jobs:
        job["job_id"] = str(job["job_id"])
    return jobs


def _resume_view_missed_tasks() -> list[dict]:
    """Catch-up registry: tasks past their threshold or never-ran.

    Defensive: catch-up registry / django_celery_beat may not be loaded
    on minimal installs; returns empty list silently in that case.
    """
    try:
        from django.utils import timezone
        from django_celery_beat.models import PeriodicTask

        from config.catchup_registry import CATCHUP_REGISTRY
    except Exception:  # noqa: BLE001 — optional dependency on minimal installs.
        logger.debug("Catch-up registry unavailable, skipping missed tasks check")
        return []

    now = timezone.now()
    missed: list[dict] = []
    for task_name, entry in CATCHUP_REGISTRY.items():
        periodic = PeriodicTask.objects.filter(name=task_name).first()
        if periodic is None:
            continue
        if periodic.last_run_at is None:
            missed.append(
                {
                    "task_name": task_name,
                    "weight_class": entry.weight_class,
                    "hours_overdue": None,
                    "reason": "Never ran",
                }
            )
            continue
        hours_since = (now - periodic.last_run_at).total_seconds() / 3600
        if hours_since > entry.threshold_hours:
            missed.append(
                {
                    "task_name": task_name,
                    "weight_class": entry.weight_class,
                    "hours_overdue": round(hours_since - entry.threshold_hours, 1),
                    "reason": (
                        f"Last ran {int(hours_since)}h ago "
                        f"(threshold: {int(entry.threshold_hours)}h)"
                    ),
                }
            )
    return missed


class ResumeStateView(APIView):
    """GET /api/dashboard/resume-state/

    Returns interrupted pipeline runs, last review position, and missed
    tasks from the catch-up registry.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return interrupted runs + resumable syncs + missed-task breadcrumbs.

        Refactored 2026-05-04: was 78 lines. Each section is now its own
        helper so a future operator-UX tweak (e.g. raise the limit
        from 3 → 10) is one edit per section.
        """
        return Response(
            {
                "interrupted_runs": _resume_view_interrupted_runs(),
                "resumable_syncs": _resume_view_resumable_syncs(),
                "missed_tasks": _resume_view_missed_tasks(),
            }
        )


# ── Status-story helpers (extracted from StatusStoryView.get) ───
# Each query is a thin defensive helper that returns 0 / "unknown" if
# the upstream model isn't loadable (cold start, optional-app missing).
# Each fragment-builder is pure so the narrative copy is testable
# without spinning up a request lifecycle.


def _status_story_alert_count(since: object) -> int:
    """Count today's unread urgent / error / warning alerts."""
    from apps.notifications.models import OperatorAlert

    return OperatorAlert.objects.filter(
        first_seen_at__gte=since,
        status="unread",
        severity__in=["urgent", "error", "warning"],
    ).count()


def _status_story_pending_count() -> int:
    from apps.suggestions.models import Suggestion

    return Suggestion.objects.filter(status="pending").count()


def _status_story_health_status() -> str:
    """Best-effort: 'unknown' when the health app can't compute a summary."""
    try:
        from apps.health.services import compute_system_summary

        return compute_system_summary().get("system_status", "unknown")
    except Exception:  # noqa: BLE001 — health app is optional; narrative gracefully omits the fragment when unknown.
        logger.debug("health summary unavailable for status story")
        return "unknown"


def _status_story_broken_links_count() -> int:
    """Best-effort: 0 when the graph app isn't migrated."""
    try:
        from apps.graph.models import BrokenLink

        return BrokenLink.objects.filter(status="open").count()
    except Exception:  # noqa: BLE001 — graph app is optional on cold start.
        logger.debug("BrokenLink not available for status story")
        return 0


def _status_story_alerts_fragment(alerts_today: int) -> str:
    if alerts_today == 0:
        return "no new alerts"
    if alerts_today == 1:
        return "1 alert fired today"
    return f"{alerts_today} alerts fired today"


def _status_story_health_fragment(health_status: str) -> str | None:
    """Returns ``None`` when health is 'unknown' — narrative omits it."""
    if health_status == "healthy":
        return "all systems healthy"
    if health_status == "degraded":
        return "some services degraded"
    if health_status in ("critical", "error"):
        return "a critical service is down"
    return None  # 'unknown' stays silent rather than mislead


def _status_story_pending_fragment(pending_reviews: int) -> str:
    if pending_reviews == 0:
        return "no suggestions waiting"
    if pending_reviews == 1:
        return "1 suggestion waiting for review"
    return f"{pending_reviews} suggestions waiting for review"


def _status_story_broken_fragment(broken_links_open: int) -> str | None:
    """Only mentioned when broken-link count > 0 — silence is healthy."""
    if broken_links_open <= 0:
        return None
    return _pluralise(broken_links_open, "broken link")


def _status_story_fragments(
    *,
    alerts_today: int,
    health_status: str,
    pending_reviews: int,
    broken_links_open: int,
) -> list[str]:
    """Compose the per-bullet narrative; drop None fragments."""
    candidates = [
        _status_story_alerts_fragment(alerts_today),
        _status_story_health_fragment(health_status),
        _status_story_pending_fragment(pending_reviews),
        _status_story_broken_fragment(broken_links_open),
    ]
    return [f for f in candidates if f]


def _status_story_time_prefix(hour: int) -> str:
    if hour < 12:
        return "This morning"
    if hour < 17:
        return "This afternoon"
    return "This evening"


class StatusStoryView(APIView):
    """GET /api/dashboard/story/

    Phase D1 / Gap 53 — a plain-English narrative summary for the
    dashboard's "Status Story" card.

    Composes one or two sentences from data the frontend already
    has, plus counts that would be awkward to aggregate client-side.
    Refreshed every 5 minutes by the caller (dashboard component).

    Example output:
        "This morning: 3 alerts fired, Celery is healthy, 47
         suggestions are waiting for review."
        "Quiet so far — no alerts, no broken links, 12 suggestions
         ready."
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return a 1-line operator narrative + supporting counts.

        Refactored 2026-05-04: was 95 lines. Each data-source query +
        each fragment-builder is now its own pure function so adding a
        new narrative bullet (or unit-testing the existing ones) is a
        single edit.
        """
        from django.utils import timezone

        now = timezone.now()
        since_morning = now.replace(hour=0, minute=0, second=0, microsecond=0)

        alerts_today = _status_story_alert_count(since_morning)
        pending_reviews = _status_story_pending_count()
        health_status = _status_story_health_status()
        broken_links_open = _status_story_broken_links_count()

        fragments = _status_story_fragments(
            alerts_today=alerts_today,
            health_status=health_status,
            pending_reviews=pending_reviews,
            broken_links_open=broken_links_open,
        )
        return Response(
            {
                "headline": f"{_status_story_time_prefix(now.hour)}: {self._join_fragments(fragments)}.",
                "fragments": fragments,
                "alerts_today": alerts_today,
                "pending_reviews": pending_reviews,
                "broken_links_open": broken_links_open,
                "health_status": health_status,
                "generated_at": now.isoformat(),
            }
        )

    @staticmethod
    def _join_fragments(fragments: list[str]) -> str:
        if not fragments:
            return "nothing to report"
        if len(fragments) == 1:
            return fragments[0]
        if len(fragments) == 2:
            return f"{fragments[0]} and {fragments[1]}"
        return ", ".join(fragments[:-1]) + f", and {fragments[-1]}"


class MissionBriefView(APIView):
    """GET /api/dashboard/mission-brief/

    Phase D1 / Gap 61 — a pinned three-sentence summary for the
    dashboard header. Differs from StatusStoryView by timeframe:
    Mission Brief is the morning executive summary (yesterday's
    outcomes + today's priorities), Status Story is a rolling
    present-tense snapshot.

    Three sentences, plain English:
      1. Yesterday: what the system did (counts).
      2. Today: what's queued (counts).
      3. Watch: the single most pressing thing to fix, if any.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return the 3-sentence "Today" summary + supporting counts.

        Refactored 2026-05-04: was 114 lines. Each sentence + the
        top-alert lookup is now a separate helper so the handler reads
        like a brief — and each helper is independently testable.
        """
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        yesterday_cutoff = now - timedelta(hours=24)

        yesterday = _today_view_yesterday_counts(yesterday_cutoff)
        today_queue = _today_view_today_queue_counts()
        top_alert = _today_view_top_alert()

        return Response(
            {
                "sentences": [
                    _today_view_sentence_yesterday(yesterday),
                    _today_view_sentence_today(today_queue),
                    _today_view_sentence_watch(top_alert),
                ],
                "counts": {
                    "approved_last_24h": yesterday["approved"],
                    "synced_last_24h": yesterday["synced"],
                    "pipeline_runs_last_24h": yesterday["pipeline_runs"],
                    "pending_reviews": today_queue["pending_reviews"],
                    "running_syncs": today_queue["running_syncs"],
                },
                "top_alert": _today_view_top_alert_dict(top_alert),
                "generated_at": now.isoformat(),
            }
        )


# ── Today-actions helpers (extracted from TodayActionsView.get) ──


def _today_view_yesterday_counts(cutoff) -> dict[str, int]:
    """Count approvals / sync completions / pipeline runs since *cutoff*."""
    from apps.suggestions.models import PipelineRun, Suggestion
    from apps.sync.models import SyncJob

    return {
        "approved": Suggestion.objects.filter(
            status="approved", reviewed_at__gte=cutoff
        ).count(),
        "synced": SyncJob.objects.filter(
            status="completed", completed_at__gte=cutoff
        ).count(),
        "pipeline_runs": PipelineRun.objects.filter(created_at__gte=cutoff).count(),
    }


def _today_view_today_queue_counts() -> dict[str, int]:
    """Live queue counts (pending reviews + in-flight syncs)."""
    from apps.suggestions.models import Suggestion
    from apps.sync.models import SyncJob

    return {
        "pending_reviews": Suggestion.objects.filter(status="pending").count(),
        "running_syncs": SyncJob.objects.filter(
            status__in=["running", "pending"]
        ).count(),
    }


def _today_view_top_alert():
    """Most pressing unread alert (urgent or error severity), or None."""
    from apps.notifications.models import OperatorAlert

    return (
        OperatorAlert.objects.filter(status="unread", severity__in=["urgent", "error"])
        .order_by("-first_seen_at")
        .first()
    )


def _today_view_top_alert_dict(top_alert) -> dict | None:
    """Serialise the top-alert object for the JSON payload, or None."""
    if top_alert is None:
        return None
    return {
        "alert_id": str(top_alert.alert_id),
        "severity": top_alert.severity,
        "title": top_alert.title,
    }


def _pluralise(n: int, singular: str, plural: str = "") -> str:
    """Format ``"N word"`` / ``"N words"`` — single source for the
    pluralisation that was inline in 5+ places in the today-view body."""
    word = singular if n == 1 else (plural or f"{singular}s")
    return f"{n} {word}"


def _today_view_sentence_yesterday(counts: dict[str, int]) -> str:
    """Build the plain-English sentence describing the last 24 hours."""
    parts: list[str] = []
    if counts["approved"]:
        parts.append(f"{_pluralise(counts['approved'], 'suggestion')} approved")
    if counts["synced"]:
        parts.append(f"{_pluralise(counts['synced'], 'sync job')} finished")
    if counts["pipeline_runs"]:
        parts.append(_pluralise(counts["pipeline_runs"], "pipeline run"))
    if not parts:
        return "In the last 24 hours nothing was approved or synced."
    return "In the last 24 hours: " + ", ".join(parts) + "."


def _today_view_sentence_today(queue: dict[str, int]) -> str:
    """Build the plain-English sentence describing the right-now queue."""
    parts: list[str] = []
    if queue["pending_reviews"]:
        parts.append(
            f"{_pluralise(queue['pending_reviews'], 'suggestion')} waiting for review"
        )
    if queue["running_syncs"]:
        parts.append(f"{_pluralise(queue['running_syncs'], 'sync')} in flight")
    if not parts:
        return "Right now the queue is clear."
    return "Right now: " + " and ".join(parts) + "."


def _today_view_sentence_watch(top_alert) -> str:
    """Build the plain-English sentence describing the most pressing alert."""
    if top_alert is None:
        return "Nothing is on fire."
    return f'Watch: {top_alert.severity} alert — "{top_alert.title[:80]}".'
