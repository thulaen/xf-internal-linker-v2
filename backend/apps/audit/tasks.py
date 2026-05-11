"""
Periodic audit tasks — reviewer scorecard computation and GlitchTip issue sync.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from datetime import date, timedelta
from typing import Any, Callable

from celery import shared_task
from django.db import connection
from django.utils import timezone

from apps.api.query_params import coerce_int
from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)

# ── Fingerprint normalisation ──────────────────────────────────────────────
_GLITCHTIP_FINGERPRINT_NOISE_RE = re.compile(
    r"(\d{2,}|[0-9a-f]{8,}|/[/\w.\-]+|0x[0-9a-f]+)",
    re.IGNORECASE,
)

# ── Scorecard constants ────────────────────────────────────────────────────
_MAX_REVIEW_TIME_SECONDS: int = (
    604_800  # 7 days — cap to filter re-opened-suggestion outliers
)
_REVIEW_ACTIONS_SAMPLE: int = 200  # max audit rows to scan when averaging review time
_REJECTION_SAMPLE: int = 200  # max rejection rows to scan for reason bucketing
_TOP_REASONS_LIMIT: int = 5

# ── GlitchTip sync constants ───────────────────────────────────────────────
_GLITCHTIP_FETCH_LIMIT: int = 100
_GLITCHTIP_REQUEST_TIMEOUT: int = 15  # seconds

# Spec table: GlitchTip level string → ErrorLog severity string.
# Mirrors the _RULES pattern in fix_suggestions.py — data-driven lookup
# replaces inline conditional logic.  ErrorLog.SEVERITY_* are plain
# strings so no model import is needed at module level.
_GLITCHTIP_SEVERITY_MAP: dict[str, str] = {
    "fatal": "critical",
    "error": "high",
    "warning": "medium",
    "info": "low",
    "debug": "low",
}


# ── Pure helpers: fingerprints ─────────────────────────────────────────────


def _canonicalize_glitchtip_fingerprint(raw_fingerprint: object) -> str:
    if isinstance(raw_fingerprint, (list, tuple)):
        parts = [str(part).strip() for part in raw_fingerprint if str(part).strip()]
        return "|".join(parts)
    if raw_fingerprint is None:
        return ""
    return str(raw_fingerprint).strip()


def _fallback_glitchtip_fingerprint(title: str, culprit: str) -> str:
    normalized = _GLITCHTIP_FINGERPRINT_NOISE_RE.sub("*", f"{title}|{culprit}")
    return hashlib.sha1(
        normalized.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()


# ── Pure helpers: scorecard ────────────────────────────────────────────────


def _scorecard_week_period(today: date) -> tuple[date, date]:
    """Return (period_start, period_end) for the Monday–Sunday week ending yesterday."""
    period_end = today - timedelta(days=1)  # Sunday
    period_start = period_end - timedelta(days=6)  # Monday
    return period_start, period_end


def _compute_rate(numerator: int, denominator: int) -> float:
    """Return numerator/denominator * 100, or 0.0 when denominator is zero."""
    return (numerator / denominator * 100.0) if denominator > 0 else 0.0


def _compute_avg_review_time(pairs: list[tuple]) -> float | None:
    """Mean elapsed seconds from (audit_dt, suggestion_dt) pairs.

    Pairs outside [0, _MAX_REVIEW_TIME_SECONDS] are dropped as outliers.
    Returns None when no valid pairs remain.
    """
    times = [
        (a - s).total_seconds()
        for a, s in pairs
        if 0 <= (a - s).total_seconds() <= _MAX_REVIEW_TIME_SECONDS
    ]
    return (sum(times) / len(times)) if times else None


def _extract_top_rejection_reasons(details: list) -> list[dict[str, Any]]:
    """Count rejection_reason across detail dicts, return top _TOP_REASONS_LIMIT."""
    reason_counts: Counter[str] = Counter()
    for detail in details:
        reason = (detail or {}).get("rejection_reason", "unknown")
        reason_counts[reason] += 1
    return [
        {"reason": r, "count": c}
        for r, c in reason_counts.most_common(_TOP_REASONS_LIMIT)
    ]


# ── DB helpers: scorecard (non-pure — query DB) ────────────────────────────


def _fetch_period_metrics(
    review_actions: Any,
    suggestion_model: Any,
    period_start: date,
    period_end: date,
) -> dict[str, int]:
    """Run count queries for the scorecard period and return a metrics dict."""
    total = review_actions.count()
    approved = review_actions.filter(action="approve").count()
    verified = suggestion_model.objects.filter(
        status__in=("verified", "applied"),
        updated_at__date__gte=period_start,
        updated_at__date__lte=period_end,
    ).count()
    stale = suggestion_model.objects.filter(
        status="stale",
        updated_at__date__gte=period_start,
        updated_at__date__lte=period_end,
    ).count()
    return {
        "total": total,
        "approved": approved,
        "rejected": total - approved,
        "verified": verified,
        "stale": stale,
    }


def _collect_review_pairs(review_actions: Any, suggestion_model: Any) -> list[tuple]:
    """Return (audit_dt, suggestion_dt) datetime pairs for review-time averaging."""
    pairs: list[tuple] = []
    for audit in review_actions.only("target_id", "created_at")[
        :_REVIEW_ACTIONS_SAMPLE
    ]:
        try:
            sug = suggestion_model.objects.only("created_at").get(
                suggestion_id=audit.target_id
            )
            pairs.append((audit.created_at, sug.created_at))
        except (suggestion_model.DoesNotExist, ValueError):
            continue
    return pairs


# ── Pure helpers: GlitchTip sync ──────────────────────────────────────────


def _parse_glitchtip_tags(tags_raw: object) -> dict[str, str]:
    """Convert GlitchTip [[key, val], ...] tag list to a plain dict."""
    return {
        t[0]: t[1]
        for t in (tags_raw or [])
        if isinstance(t, (list, tuple)) and len(t) == 2
    }


def _glitchtip_why_message(level: str, culprit: str, count: int) -> str:
    """Plain-English 'why' string for a GlitchTip error log row."""
    culprit_text = culprit or "unknown"
    return (
        f"GlitchTip captured a '{level}' event. "
        f"Culprit: {culprit_text}. Seen {count} time(s)."
    )


def _build_glitchtip_issue_kwargs(
    issue: dict,
    api_url: str,
    suggest_fn: Callable[[str, str, str], str],
) -> dict[str, Any]:
    """Map a raw GlitchTip issue dict to ErrorLog.objects.create() kwargs.

    Does not include runtime_context — the caller supplies that at create time.
    Uses "glitchtip" (= ErrorLog.SOURCE_GLITCHTIP) as a plain string to avoid
    a model import at module level.
    """
    gt_id = str(issue.get("id", ""))
    title = issue.get("title") or "Untitled"
    culprit = issue.get("culprit", "")
    level = issue.get("level", "error")
    # Bug fix 2026-05-04: coerce_int guards against stringified floats from
    # older GlitchTip API versions (e.g. "1.5"); falls back to 1 (safe min).
    count = coerce_int(issue.get("count"), default=1, min_value=1)
    tags = _parse_glitchtip_tags(issue.get("tags"))
    fingerprint = _canonicalize_glitchtip_fingerprint(issue.get("fingerprint"))
    if not fingerprint:
        fingerprint = _fallback_glitchtip_fingerprint(title, culprit)
    return {
        "source": "glitchtip",  # ErrorLog.SOURCE_GLITCHTIP
        "job_type": (culprit.split(".")[0][:50] if culprit else "unknown"),
        "step": (culprit[:100] if culprit else "unknown"),
        "error_message": title[:4000],
        "why": _glitchtip_why_message(level, culprit, count),
        "how_to_fix": suggest_fn(title, fingerprint, culprit),
        "glitchtip_issue_id": gt_id,
        "glitchtip_url": f"{api_url}/issues/{gt_id}/",
        "fingerprint": fingerprint[:255],
        "occurrence_count": count,
        "severity": _GLITCHTIP_SEVERITY_MAP.get(level, "medium"),
        "node_id": tags.get("node_id", "primary"),
        "node_role": tags.get("node_role", "primary"),
        "node_hostname": tags.get("server_name", ""),
    }


# ── DB helper: GlitchTip sync (non-pure — queries ErrorLog) ───────────────


def _handle_resolved_upstream(existing) -> str:
    """Mark a known issue acknowledged when GT reports it resolved upstream."""
    if existing is not None and not existing.acknowledged:
        existing.acknowledged = True
        existing.save(update_fields=["acknowledged"])
        return "resolved"
    return "skipped"


def _refresh_existing_row(existing, kwargs: dict) -> str:
    """Update mutable fields on an already-tracked GT issue."""
    existing.occurrence_count = kwargs["occurrence_count"]
    existing.severity = kwargs["severity"]
    existing.fingerprint = kwargs["fingerprint"]
    existing.save(update_fields=["occurrence_count", "severity", "fingerprint"])
    return "updated"


def _sync_one_glitchtip_issue(
    issue: dict,
    api_url: str,
    suggest_fn: Callable,
    error_log_cls: Any,
    runtime_snapshot: Callable,
) -> str:
    """Upsert one GlitchTip issue into ErrorLog.

    Returns 'created' | 'updated' | 'resolved' | 'skipped' |
    'merged_into_existing'.

    Collision strategy: PRE-check the unique key (fingerprint, node_id)
    BEFORE INSERT. Avoids the auto-instrumentation false-positive that
    `try INSERT … except IntegrityError` produced (ISS-104).
    """
    gt_id = str(issue.get("id", ""))
    if not gt_id:
        return "skipped"
    existing = error_log_cls.objects.filter(glitchtip_issue_id=gt_id).first()

    if issue.get("status") == "resolved":
        return _handle_resolved_upstream(existing)

    kwargs = _build_glitchtip_issue_kwargs(issue, api_url, suggest_fn)
    if existing is not None:
        return _refresh_existing_row(existing, kwargs)

    fp = kwargs["fingerprint"]
    node_id = kwargs.get("node_id")
    if error_log_cls.objects.filter(fingerprint=fp, node_id=node_id).exists():
        return _merge_glitchtip_id_into_existing_row(
            error_log_cls, gt_id, fp, node_id
        )

    error_log_cls.objects.create(**kwargs, runtime_context=runtime_snapshot())
    return "created"


def _merge_glitchtip_id_into_existing_row(
    error_log_cls: Any,
    gt_id: str,
    fingerprint: str,
    node_id: str | None,
) -> str:
    """Attach the new GlitchTip ID to the existing row sharing the fingerprint."""
    qs = error_log_cls.objects.filter(fingerprint=fingerprint)
    if node_id:
        qs = qs.filter(node_id=node_id)
    target = qs.first()
    if target is None:
        return "skipped_dup_fingerprint"
    if not target.glitchtip_issue_id:
        target.glitchtip_issue_id = gt_id
        target.save(update_fields=["glitchtip_issue_id"])
    return "merged_into_existing"


# ─────────────────────────────────────────────────────────────────────────
# Celery tasks
# ─────────────────────────────────────────────────────────────────────────


def _gather_review_actions(period_start, period_end):
    """All AuditEntry rows for approve/reject actions in the given week."""
    from apps.audit.models import AuditEntry

    return AuditEntry.objects.filter(
        action__in=("approve", "reject"),
        target_type="suggestion",
        created_at__date__gte=period_start,
        created_at__date__lte=period_end,
    )


def _build_scorecard_kwargs(review_actions, period_start, period_end):
    """Compute every numeric field on a ReviewerScorecard from the action set."""
    from apps.suggestions.models import Suggestion

    counts = _fetch_period_metrics(
        review_actions, Suggestion, period_start, period_end
    )
    avg = _compute_avg_review_time(
        _collect_review_pairs(review_actions, Suggestion)
    )
    top_reasons = _extract_top_rejection_reasons(
        [
            a.detail
            for a in review_actions.filter(action="reject").only("detail")[
                :_REJECTION_SAMPLE
            ]
        ]
    )
    return counts, dict(
        period_start=period_start,
        period_end=period_end,
        total_reviewed=counts["total"],
        approved_count=counts["approved"],
        rejected_count=counts["rejected"],
        approval_rate=round(_compute_rate(counts["approved"], counts["total"]), 2),
        verified_rate=round(_compute_rate(counts["verified"], counts["approved"]), 2),
        stale_rate=round(_compute_rate(counts["stale"], counts["approved"]), 2),
        avg_review_time_seconds=round(avg, 1) if avg is not None else None,
        top_rejection_reasons=top_reasons,
    )


@shared_task(name="audit.compute_weekly_reviewer_scorecard")
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=300,
)
def compute_weekly_reviewer_scorecard():
    """Compute ReviewerScorecard for the previous calendar week. Runs Monday 03:00 UTC."""
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    today = timezone.now().date()
    period_start, period_end = _scorecard_week_period(today)
    if ReviewerScorecard.objects.filter(
        period_start=period_start, period_end=period_end
    ).exists():
        logger.info(
            "[reviewer_scorecard] Scorecard already exists for %s–%s",
            period_start, period_end,
        )
        return {"status": "already_exists"}
    review_actions = _gather_review_actions(period_start, period_end)
    counts, kwargs = _build_scorecard_kwargs(review_actions, period_start, period_end)
    scorecard = ReviewerScorecard.objects.create(**kwargs)
    logger.info(
        "[reviewer_scorecard] Created for %s–%s: %d reviewed, %.1f%% approved",
        period_start, period_end, counts["total"],
        _compute_rate(counts["approved"], counts["total"]),
    )
    return {"status": "created", "scorecard_id": scorecard.id}


# ─────────────────────────────────────────────────────────────────────────
# Phase GT Step 7 — GlitchTip issue sync
# ─────────────────────────────────────────────────────────────────────────


def _glitchtip_env() -> tuple[str, str, str, str]:
    """Return (api_url, token, org_slug, project_slug). All four blank when unset."""
    import os

    return (
        os.environ.get("GLITCHTIP_API_URL", "").rstrip("/"),
        os.environ.get("GLITCHTIP_API_TOKEN", ""),
        os.environ.get("GLITCHTIP_ORG_SLUG", ""),
        os.environ.get("GLITCHTIP_PROJECT_SLUG", ""),
    )


def _fetch_glitchtip_issues(api_url: str, token: str, org: str, proj: str):
    """Single HTTP fetch — returns (issues_list, error_dict). One of them is None."""
    import requests

    try:
        response = requests.get(
            f"{api_url}/api/0/projects/{org}/{proj}/issues/",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": _GLITCHTIP_FETCH_LIMIT},
            timeout=_GLITCHTIP_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException as exc:
        logger.warning("[glitchtip-sync] Fetch failed: %s", exc)
        return None, {"status": "error", "detail": str(exc)}
    except ValueError as exc:
        logger.warning("[glitchtip-sync] Response not JSON: %s", exc)
        return None, {"status": "error", "detail": str(exc)}


def _tally_sync_outcomes(issues, api_url, suggest_fn, error_log_cls, runtime_snapshot):
    """Apply `_sync_one_glitchtip_issue` to each issue; return outcome counts."""
    counts = {"created": 0, "updated": 0, "resolved": 0, "merged": 0}
    outcome_to_key = {
        "created": "created",
        "updated": "updated",
        "resolved": "resolved",
        "merged_into_existing": "merged",
    }
    for issue in issues:
        outcome = _sync_one_glitchtip_issue(
            issue, api_url, suggest_fn, error_log_cls, runtime_snapshot
        )
        key = outcome_to_key.get(outcome)
        if key is not None:
            counts[key] += 1
    return counts


@shared_task(name="audit.sync_glitchtip_issues")
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=256,
)
def sync_glitchtip_issues():
    """Pull open GlitchTip issues and mirror them into ErrorLog for operator triage.

    Runs every 30 minutes via Celery Beat. Graceful no-op when env vars are
    missing so a project without GlitchTip doesn't see Beat errors every 30 min.
    """
    # Mandatory Prevention Sweep (#86): close stale connections before task logic.
    connection.close()

    from apps.audit.fix_suggestions import suggest
    from apps.audit.models import ErrorLog
    from apps.audit.runtime_context import snapshot as runtime_snapshot

    api_url, token, org, proj = _glitchtip_env()
    if not all([api_url, token, org, proj]):
        return {"status": "skipped", "reason": "missing_env_vars"}
    issues, err = _fetch_glitchtip_issues(api_url, token, org, proj)
    if err is not None:
        return err
    counts = _tally_sync_outcomes(
        issues, api_url, suggest, ErrorLog, runtime_snapshot
    )
    logger.info(
        "[glitchtip-sync] created=%d updated=%d resolved=%d merged=%d",
        counts["created"], counts["updated"], counts["resolved"], counts["merged"],
    )
    return {"status": "ok", **counts}
