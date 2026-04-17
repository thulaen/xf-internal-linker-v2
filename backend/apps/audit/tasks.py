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


# ─────────────────────────────────────────────────────────────────────────
# Phase GT Step 7 — GlitchTip issue sync
# ─────────────────────────────────────────────────────────────────────────


@shared_task(name="audit.sync_glitchtip_issues")
def sync_glitchtip_issues():
    """
    Pull open issues from the GlitchTip REST API and mirror them into
    ErrorLog so the operator can triage internal + third-party errors
    in one Diagnostics view. Runs every 30 minutes via Celery Beat.

    Dedup rule: `source='glitchtip'` + `glitchtip_issue_id` is the unique
    key. An issue that flips to `resolved` upstream auto-acknowledges
    its mirrored row.

    Graceful no-op when any of the required env vars is missing — that
    way a project without GlitchTip doesn't see Beat errors every 30 min.
    """
    import os

    import requests

    from apps.audit.fix_suggestions import suggest
    from apps.audit.models import ErrorLog
    from apps.audit.runtime_context import snapshot as runtime_snapshot

    api_url = os.environ.get("GLITCHTIP_API_URL", "").rstrip("/")
    token = os.environ.get("GLITCHTIP_API_TOKEN", "")
    org = os.environ.get("GLITCHTIP_ORG_SLUG", "")
    proj = os.environ.get("GLITCHTIP_PROJECT_SLUG", "")
    if not all([api_url, token, org, proj]):
        return {"status": "skipped", "reason": "missing_env_vars"}

    try:
        response = requests.get(
            f"{api_url}/api/0/projects/{org}/{proj}/issues/",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 100},
            timeout=15,
        )
        response.raise_for_status()
        issues = response.json()
    except requests.RequestException as exc:
        logger.warning("[glitchtip-sync] Fetch failed: %s", exc)
        return {"status": "error", "detail": str(exc)}
    except ValueError as exc:
        logger.warning("[glitchtip-sync] Response not JSON: %s", exc)
        return {"status": "error", "detail": str(exc)}

    severity_map = {
        "fatal": ErrorLog.SEVERITY_CRITICAL,
        "error": ErrorLog.SEVERITY_HIGH,
        "warning": ErrorLog.SEVERITY_MEDIUM,
        "info": ErrorLog.SEVERITY_LOW,
        "debug": ErrorLog.SEVERITY_LOW,
    }

    created = updated = resolved = 0

    for issue in issues:
        gt_id = str(issue.get("id", ""))
        if not gt_id:
            continue
        status_ = issue.get("status", "")
        title = issue.get("title") or "Untitled"
        culprit = issue.get("culprit", "")
        count = int(issue.get("count", 1))
        level = issue.get("level", "error")
        severity = severity_map.get(level, ErrorLog.SEVERITY_MEDIUM)
        url = f"{api_url}/issues/{gt_id}/"
        fingerprint = str(issue.get("fingerprint") or gt_id)[:255]
        tags = {
            t[0]: t[1]
            for t in (issue.get("tags") or [])
            if isinstance(t, (list, tuple)) and len(t) == 2
        }

        existing = ErrorLog.objects.filter(glitchtip_issue_id=gt_id).first()

        if status_ == "resolved":
            if existing is not None and not existing.acknowledged:
                existing.acknowledged = True
                existing.save(update_fields=["acknowledged"])
                resolved += 1
            continue

        if existing is not None:
            existing.occurrence_count = count
            existing.severity = severity
            existing.save(update_fields=["occurrence_count", "severity"])
            updated += 1
            continue

        ErrorLog.objects.create(
            source=ErrorLog.SOURCE_GLITCHTIP,
            job_type=(culprit.split(".")[0][:50] if culprit else "unknown"),
            step=(culprit[:100] if culprit else "unknown"),
            error_message=title[:4000],
            why=(
                f"GlitchTip captured a '{level}' event. Culprit: "
                f"{culprit or 'unknown'}. Seen {count} time(s)."
            ),
            how_to_fix=suggest(title, fingerprint, culprit),
            glitchtip_issue_id=gt_id,
            glitchtip_url=url,
            fingerprint=fingerprint,
            occurrence_count=count,
            severity=severity,
            node_id=tags.get("node_id", "primary"),
            node_role=tags.get("node_role", "primary"),
            node_hostname=tags.get("server_name", ""),
            runtime_context=runtime_snapshot(),
        )
        created += 1

    logger.info(
        "[glitchtip-sync] created=%d updated=%d resolved=%d",
        created,
        updated,
        resolved,
    )
    return {
        "status": "ok",
        "created": created,
        "updated": updated,
        "resolved": resolved,
    }
