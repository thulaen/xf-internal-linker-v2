"""Top-10 picker for the paper-trail opening ritual."""

from __future__ import annotations

from apps.paper_trail.models import PaperTrailEntry


def pick_top_n(n: int = 10) -> list[PaperTrailEntry]:
    """Return up to `n` unique active entries ordered by priority then recency."""
    closed_keys = _closed_canonical_keys()
    picked: list[PaperTrailEntry] = []
    seen_keys: set[str] = set()
    for entry in _ordered_active_entries():
        key = _dedupe_key(entry)
        if key in closed_keys or key in seen_keys:
            continue
        picked.append(entry)
        seen_keys.add(key)
        if len(picked) == n:
            break
    return picked


def _ordered_active_entries():
    return (
        PaperTrailEntry.objects.filter(status__in=PaperTrailEntry._ACTIVE_STATUSES)
        .order_by("-priority_score", "-last_seen")
        .iterator()
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


def _closed_canonical_keys() -> set[str]:
    return set(
        PaperTrailEntry.objects.filter(status__in=PaperTrailEntry._TERMINAL_STATUSES)
        .exclude(canonical_fingerprint="")
        .values_list("canonical_fingerprint", flat=True)
        .distinct()
    )


def _dedupe_key(entry: PaperTrailEntry) -> str:
    return entry.canonical_fingerprint or f"paper-trail:{entry.pk}"
