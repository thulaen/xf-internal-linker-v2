"""Priority-score calculation for paper trail entries.

Formula combines severity, age, and occurrence count so older entries
re-deferred multiple times surface above brand-new low-severity ones.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry


_SEVERITY_WEIGHT = {
    PaperTrailEntry.SEVERITY_CRITICAL: 4.0,
    PaperTrailEntry.SEVERITY_HIGH: 3.0,
    PaperTrailEntry.SEVERITY_MEDIUM: 2.0,
    PaperTrailEntry.SEVERITY_LOW: 1.0,
}


def compute_priority_score(entry: PaperTrailEntry) -> float:
    """Return a 0-10 priority score for `entry`.

    Combines (a) severity weight (1-4), (b) days-since-deferred aging
    bonus (1 point per 30 days, capped at 3), and (c) occurrence-count
    boost (0.1 per re-deferral, capped at 2). The 0-10 range matches
    AutoIssue.priority_score conventions.
    """
    severity_score = _SEVERITY_WEIGHT.get(entry.severity, 2.0)
    age = timezone.now() - (entry.deferred_at or timezone.now())
    aging_score = min(age / timedelta(days=30), 3.0)
    repeat_score = min(0.1 * (entry.occurrence_count - 1), 2.0)
    return round(severity_score + aging_score + repeat_score, 4)


def refresh_priority_scores(limit: int | None = None) -> int:
    """Update priority_score on every active entry. Returns count updated."""
    qs = PaperTrailEntry.objects.filter(status__in=PaperTrailEntry._ACTIVE_STATUSES)
    if limit is not None:
        qs = qs[:limit]
    count = 0
    for entry in qs:
        new_score = compute_priority_score(entry)
        if entry.priority_score != new_score:
            entry.priority_score = new_score
            entry.save(update_fields=["priority_score"])
            count += 1
    return count
