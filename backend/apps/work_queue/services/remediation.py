from __future__ import annotations

from apps.auto_issues.models import AutoIssue


def historical_fix_suggestions(*, query: str = "", limit: int = 5) -> list[dict]:
    text = (query or "").strip()
    qs = AutoIssue.objects.filter(
        status=AutoIssue.STATUS_RESOLVED,
        lessons_learned__icontains="Trap:",
    ).exclude(lessons_learned="")
    if text:
        qs = qs.filter(title__icontains=text) | qs.filter(description__icontains=text)
    return [_row(issue) for issue in qs.order_by("-resolved_at")[:limit]]


def suggestion_for_item(item) -> str:
    files = getattr(item, "affected_files", None) or []
    title = getattr(item, "title", "")
    if files:
        return f"Read the prior fixes for {files[0]} before editing. Then rehearse the smallest test-first change."
    if title:
        return f"Search resolved lessons for similar wording to '{title[:80]}' before editing."
    return "Start by writing the smallest behavior test that proves the issue."


def _row(issue: AutoIssue) -> dict:
    return {
        "id": issue.id,
        "title": issue.title,
        "source": issue.source,
        "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
        "lessons_learned": issue.lessons_learned,
    }

