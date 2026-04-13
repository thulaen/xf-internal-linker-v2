"""Stage 9 — alert rules that run on schedule (22:30–22:45 UTC).

Each rule checks a specific condition and emits an OperatorAlert if triggered.
Added to CELERY_BEAT_SCHEDULE and the catch-up registry.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="notifications.check_silent_failure")
def check_silent_failure() -> dict:
    """Alert if no sync has completed in 72+ hours."""
    from apps.sync.models import SyncJob
    from apps.notifications.services import emit_operator_alert
    from apps.notifications.models import OperatorAlert

    last_sync = (
        SyncJob.objects.filter(status="completed").order_by("-completed_at").first()
    )

    if last_sync and last_sync.completed_at:
        hours_since = (timezone.now() - last_sync.completed_at).total_seconds() / 3600
        if hours_since > 72:
            emit_operator_alert(
                event_type="system.silent_failure",
                severity="warning",
                title="No sync in 3+ days",
                message=f"Last successful sync was {int(hours_since)} hours ago. Content may be stale.",
                source_area=OperatorAlert.AREA_SYSTEM,
                dedupe_key="system.silent_failure",
                related_route="/jobs",
            )
            return {"triggered": True, "hours_since": hours_since}

    return {"triggered": False}


@shared_task(name="notifications.check_zero_suggestion_run")
def check_zero_suggestion_run() -> dict:
    """Alert if the latest pipeline run produced zero suggestions with decent content."""
    from apps.suggestions.models import PipelineRun
    from apps.content.models import ContentItem
    from apps.notifications.services import emit_operator_alert
    from apps.notifications.models import OperatorAlert

    last_run = (
        PipelineRun.objects.filter(run_state="completed")
        .order_by("-updated_at")
        .first()
    )
    content_count = ContentItem.objects.count()

    if last_run and last_run.suggestions_created == 0 and content_count > 50:
        emit_operator_alert(
            event_type="pipeline.zero_suggestions",
            severity="warning",
            title="Pipeline produced zero suggestions",
            message=(
                f"The last pipeline run finished but created 0 suggestions "
                f"despite {content_count} content items. Check your settings."
            ),
            source_area=OperatorAlert.AREA_PIPELINE,
            dedupe_key="pipeline.zero_suggestions",
            related_route="/settings",
        )
        return {"triggered": True, "content_count": content_count}

    return {"triggered": False}


@shared_task(name="notifications.check_post_link_regression")
def check_post_link_regression() -> dict:
    """Alert if an applied link caused a significant traffic regression."""
    from apps.analytics.models import ImpactReport
    from apps.notifications.services import emit_operator_alert
    from apps.notifications.models import OperatorAlert

    regressions = ImpactReport.objects.filter(
        is_conclusive=True,
        delta_percent__lt=-15,
    ).order_by("-created_at")[:5]

    triggered = False
    for report in regressions:
        emit_operator_alert(
            event_type="analytics.post_link_regression",
            severity="error",
            title="Link may have hurt traffic",
            message=(
                f"Suggestion {str(report.suggestion_id)[:8]} shows a "
                f"{abs(report.delta_percent):.0f}% drop in {report.metric_type}."
            ),
            source_area=OperatorAlert.AREA_ANALYTICS,
            dedupe_key=f"analytics.regression:{report.suggestion_id}",
            related_route="/analytics",
        )
        triggered = True

    return {"triggered": triggered, "count": len(regressions)}


@shared_task(name="notifications.check_autotune_status")
def check_autotune_status() -> dict:
    """Alert when a ranking challenger is promoted or rolled back."""
    from apps.suggestions.models import RankingChallenger
    from apps.notifications.services import emit_operator_alert
    from apps.notifications.models import OperatorAlert

    recent = (
        RankingChallenger.objects.filter(
            updated_at__gte=timezone.now() - timezone.timedelta(hours=26)
        )
        .exclude(status="pending")
        .order_by("-updated_at")[:3]
    )

    triggered = False
    for challenger in recent:
        severity = "success" if challenger.status == "promoted" else "warning"
        emit_operator_alert(
            event_type="pipeline.autotune_status",
            severity=severity,
            title=f"Auto-tuner: {challenger.status}",
            message=f"Ranking challenger was {challenger.status}.",
            source_area=OperatorAlert.AREA_PIPELINE,
            dedupe_key=f"pipeline.autotune:{challenger.pk}",
            related_route="/settings",
        )
        triggered = True

    return {"triggered": triggered}
