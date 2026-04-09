"""
Periodic audit tasks — reviewer scorecard computation.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="audit.compute_weekly_reviewer_scorecard")
def compute_weekly_reviewer_scorecard():
    """Compute and store a weekly ReviewerScorecard for the previous calendar week.

    Runs every Monday 03:00 UTC via Celery beat.
    Period is the previous Monday–Sunday.
    """
    from apps.audit.models import AuditEntry, ReviewerScorecard
    from apps.suggestions.models import Suggestion

    today = timezone.now().date()
    period_end = today - timedelta(days=1)  # Sunday
    period_start = period_end - timedelta(days=6)  # Monday

    # Skip if scorecard already exists for this period
    if ReviewerScorecard.objects.filter(
        period_start=period_start, period_end=period_end
    ).exists():
        logger.info(
            "[reviewer_scorecard] Scorecard already exists for %s–%s",
            period_start,
            period_end,
        )
        return {"status": "already_exists"}

    # ── Gather review actions ──────────────────────────────────
    review_actions = AuditEntry.objects.filter(
        action__in=("approve", "reject"),
        target_type="suggestion",
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    )
    total_reviewed = review_actions.count()
    approved_count = review_actions.filter(action="approve").count()
    rejected_count = total_reviewed - approved_count

    approval_rate = (
        (approved_count / total_reviewed * 100.0) if total_reviewed > 0 else 0.0
    )

    # ── Verified rate: approved suggestions later verified as live ──
    verified_count = Suggestion.objects.filter(
        status__in=("verified", "applied"),
        updated_at__date__gte=period_start,
        updated_at__date__lte=period_end,
    ).count()
    verified_rate = (
        (verified_count / approved_count * 100.0) if approved_count > 0 else 0.0
    )

    # ── Stale rate ──
    stale_count = Suggestion.objects.filter(
        status="stale",
        updated_at__date__gte=period_start,
        updated_at__date__lte=period_end,
    ).count()
    stale_rate = (stale_count / approved_count * 100.0) if approved_count > 0 else 0.0

    # ── Average review time (audit.created_at - suggestion.created_at) ──
    review_times: list[float] = []
    for audit in review_actions.only("target_id", "created_at")[:200]:
        try:
            suggestion = Suggestion.objects.only("created_at").get(
                suggestion_id=audit.target_id
            )
            elapsed = (audit.created_at - suggestion.created_at).total_seconds()
            if 0 <= elapsed <= 604_800:  # cap at 7 days to filter outliers
                review_times.append(elapsed)
        except (Suggestion.DoesNotExist, ValueError):
            continue

    avg_review_time = (sum(review_times) / len(review_times)) if review_times else None

    # ── Top rejection reasons ──
    reason_counts: Counter[str] = Counter()
    for audit in review_actions.filter(action="reject").only("detail")[:200]:
        reason = (audit.detail or {}).get("rejection_reason", "unknown")
        reason_counts[reason] += 1
    top_reasons = [{"reason": r, "count": c} for r, c in reason_counts.most_common(5)]

    # ── Persist ──
    scorecard = ReviewerScorecard.objects.create(
        period_start=period_start,
        period_end=period_end,
        total_reviewed=total_reviewed,
        approved_count=approved_count,
        rejected_count=rejected_count,
        approval_rate=round(approval_rate, 2),
        verified_rate=round(verified_rate, 2),
        stale_rate=round(stale_rate, 2),
        avg_review_time_seconds=round(avg_review_time, 1)
        if avg_review_time is not None
        else None,
        top_rejection_reasons=top_reasons,
    )

    logger.info(
        "[reviewer_scorecard] Created scorecard for %s–%s: %d reviewed, %.1f%% approved",
        period_start,
        period_end,
        total_reviewed,
        approval_rate,
    )
    return {"status": "created", "scorecard_id": scorecard.id}
