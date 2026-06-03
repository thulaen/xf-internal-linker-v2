from __future__ import annotations

from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.paper_trail.models import PaperTrailEntry
from apps.work_queue.models import AgentWorkClaim, SourceConfidence
from apps.work_queue.services.agent_attempts import attempt_quality_summary
from apps.work_queue.services.correlation import build_cause_groups, contradiction_count
from apps.work_queue.services.remediation import suggestion_for_item
from apps.work_queue.services.self_healing import latest_self_healing_status

ACTIVE_PAPER_STATUSES = {"open", "picked", "in_progress", "blocked", "deferred"}


def build_overview(limit: int = 12) -> dict:
    now_items = _autoissue_items(limit // 2) + _paper_items(limit // 2)
    now_items.sort(key=lambda row: row["priority_score"], reverse=True)
    blocked = [row for row in now_items if row["blocked"]]
    return {
        "as_of": timezone.now().isoformat(),
        "now": now_items[:limit],
        "blocked": blocked,
        "self_healing": latest_self_healing_status(),
        "live_signals": _live_signals(),
        "agent_claims": _active_claims(),
        "cause_groups": build_cause_groups(6),
        "real_time_topics": [
            "work_queue",
            "work_queue.self_healing",
            "work_queue.agent_claims",
        ],
    }


def build_feed(limit: int = 30) -> dict:
    items = _autoissue_items(limit) + _paper_items(limit)
    items.sort(key=lambda row: row["updated_at"] or "", reverse=True)
    return {"as_of": timezone.now().isoformat(), "items": items[:limit]}


def rehearse_item(item_key: str) -> dict:
    from apps.work_queue.services.items import load_item, parse_item_key

    ref = parse_item_key(item_key)
    item = load_item(ref)
    return {
        "item_key": item_key,
        "next_action": suggestion_for_item(item),
        "required_checks": _required_checks(item),
        "attempt_quality": attempt_quality_summary(item_key),
    }


def _autoissue_items(limit: int) -> list[dict]:
    qs = AutoIssue.objects.exclude(status=AutoIssue.STATUS_RESOLVED).order_by(
        "-priority_score",
        "-last_seen",
    )[:limit]
    return [_autoissue_payload(issue) for issue in qs]


def _paper_items(limit: int) -> list[dict]:
    qs = PaperTrailEntry.objects.filter(status__in=ACTIVE_PAPER_STATUSES).order_by(
        "-priority_score",
        "-last_seen",
    )[:limit]
    return [_paper_payload(entry) for entry in qs]


def _autoissue_payload(issue: AutoIssue) -> dict:
    key = f"autoissue-{issue.id}"
    return {
        "key": key,
        "kind": "autoissue",
        "id": issue.id,
        "title": issue.title,
        "source": issue.source,
        "severity": issue.severity,
        "status": issue.status,
        "priority_score": float(issue.priority_score or 0.0),
        "updated_at": issue.last_seen.isoformat() if issue.last_seen else None,
        "affected_files": issue.affected_files or [],
        "blocked": False,
        "business_impact": _business_impact(issue),
        "next_action": suggestion_for_item(issue),
    }


def _paper_payload(entry: PaperTrailEntry) -> dict:
    key = f"papertrail-{entry.id}"
    return {
        "key": key,
        "kind": "papertrail",
        "id": entry.id,
        "title": entry.title,
        "source": "paper_trail",
        "severity": entry.severity,
        "status": entry.status,
        "priority_score": float(entry.priority_score or 0.0),
        "updated_at": entry.last_seen.isoformat() if entry.last_seen else None,
        "affected_files": entry.affected_files or [],
        "blocked": bool(entry.blockers),
        "business_impact": entry.risk_on_inaction or "Impact not estimated yet.",
        "next_action": suggestion_for_item(entry),
    }


def _live_signals() -> dict:
    return {
        "stale_evidence_count": PaperTrailEntry.objects.filter(status="stale").count(),
        "contradiction_count": contradiction_count(),
        "source_confidence": [
            {
                "source": row.source,
                "trust_score": row.trust_score,
                "reason": row.reason,
            }
            for row in SourceConfidence.objects.all()[:20]
        ],
    }


def _active_claims() -> list[dict]:
    rows = AgentWorkClaim.objects.filter(
        status__in=[AgentWorkClaim.STATUS_CLAIMED, AgentWorkClaim.STATUS_CONFLICTED],
    ).order_by("-claimed_at")[:20]
    return [
        {
            "id": row.id,
            "item_key": row.item_key,
            "agent": row.agent,
            "status": row.status,
            "conflict_reason": row.conflict_reason,
            "claimed_at": row.claimed_at.isoformat(),
        }
        for row in rows
    ]


def _required_checks(item) -> list[str]:
    files = getattr(item, "affected_files", None) or []
    
    def _is_autoissue_fix(affected_files: list[str]) -> bool:
        return any(
            str(f).startswith("apps/work_queue/services/autoissue")
            or str(f).startswith("apps/work_queue/tests_autoissue")
            for f in affected_files
        )

    frontend = ["Run the Angular test or build for the touched page"] if any(str(path).startswith("frontend/") for path in files) else []
    backend = ["Run the focused backend test through Docker"] if any(str(path).startswith("backend/") for path in files) else []
    autoissue = ["Run the AutoIssue specific tests for this bug class"] if _is_autoissue_fix(files) else []
    
    return ["Read the source-backed spec", "Write or update the focused test first"] + frontend + backend + autoissue


def _business_impact(issue: AutoIssue) -> str:
    title = (issue.title or "").lower()
    if "celery" in title or "redis" in title or "queue" in title:
        return "Background work may be delayed; check how many link suggestions or imports were skipped."
    return "No business impact has been calculated yet."

