"""Top-10 picker for the paper-trail opening ritual."""

from __future__ import annotations

from apps.paper_trail.models import PaperTrailEntry


def pick_top_n(n: int = 10) -> list[PaperTrailEntry]:
    """Return up to `n` active entries ordered by priority then recency."""
    return list(
        PaperTrailEntry.objects.filter(
            status__in=PaperTrailEntry._ACTIVE_STATUSES,
        )
        .order_by("-priority_score", "-last_seen")[:n]
    )


def count_by_category() -> dict[str, int]:
    """Return {category: open_count} for the 16-category breakdown."""
    counts: dict[str, int] = {
        choice[0]: 0 for choice in PaperTrailEntry.CATEGORY_CHOICES
    }
    qs = (
        PaperTrailEntry.objects.filter(
            status__in=PaperTrailEntry._ACTIVE_STATUSES,
        )
        .values_list("category")
    )
    for (cat,) in qs:
        if cat in counts:
            counts[cat] += 1
        else:
            counts[cat] = 1
    return counts


def total_open() -> int:
    return PaperTrailEntry.objects.filter(
        status__in=PaperTrailEntry._ACTIVE_STATUSES
    ).count()


def resolved_this_session_count(since) -> int:
    return PaperTrailEntry.objects.filter(
        status=PaperTrailEntry.STATUS_RESOLVED,
        resolved_at__gte=since,
    ).count()
