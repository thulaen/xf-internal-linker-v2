from __future__ import annotations

from collections import defaultdict

from apps.auto_issues.models import AutoIssue


def build_cause_groups(limit: int = 10) -> list[dict]:
    rows = AutoIssue.objects.exclude(canonical_fingerprint="").exclude(
        status=AutoIssue.STATUS_RESOLVED,
    ).order_by("-priority_score", "-last_seen")[:200]
    grouped: dict[str, list[AutoIssue]] = defaultdict(list)
    for issue in rows:
        grouped[issue.canonical_fingerprint].append(issue)
    groups = [_group_payload(fp, issues) for fp, issues in grouped.items() if issues]
    groups.sort(key=lambda row: (row["source_count"], row["max_priority"]), reverse=True)
    return groups[:limit]


def contradiction_count() -> int:
    return AutoIssue.objects.filter(title__icontains="contradict").exclude(
        status=AutoIssue.STATUS_RESOLVED,
    ).count()


def _group_payload(fingerprint: str, issues: list[AutoIssue]) -> dict:
    files = sorted({path for issue in issues for path in (issue.affected_files or [])})
    sources = sorted({issue.source for issue in issues})
    return {
        "fingerprint": fingerprint,
        "title": issues[0].title,
        "sources": sources,
        "source_count": len(sources),
        "issue_count": len(issues),
        "affected_files": files,
        "max_priority": max(float(issue.priority_score or 0.0) for issue in issues),
        "next_action": "Fix the shared cause once, then resolve every linked symptom.",
    }

