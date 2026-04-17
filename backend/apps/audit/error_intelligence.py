"""
Phase MX2 / Gaps 315-322 — Error intelligence helpers.

Small read-only helpers the Diagnostics page uses to give each ErrorLog
row richer context without calling a second LLM or importing a new
library. Everything here is database arithmetic over the existing
`ErrorLog` table, extended with the fix-suggestion registry from GT
Phase Step 4.

Gap mapping:
  * 316 similar-past-error lookup  → find_similar()
  * 317 was-this-fixed-before      → past_resolutions_for()
  * 318 common-remedies-carousel   → remedies_for()  (wraps fix_suggestions)
  * 320 auto-suggest-runbook       → runbook_match_for()
  * 321 how-many-users-hit-this    → reach_count_for()
  * 322 severity-over-time-per-cat → severity_trend_for()

Gaps 315 (LLM summary) + 319 (ask-for-help) are surfaced by the
frontend component using the existing `how_to_fix` field + runtime
context; no new backend needed for them.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import TypedDict

from django.db.models import Count
from django.utils import timezone


class SimilarError(TypedDict):
    id: int
    fingerprint: str
    error_message: str
    created_at: str
    acknowledged: bool


class RemedyCandidate(TypedDict):
    title: str
    plain_english: str
    source: str  # "fix_rule" | "past_ack"


class RunbookMatch(TypedDict):
    path: str
    heading: str
    confidence: float


class SeverityTrendPoint(TypedDict):
    day: str
    count: int


def find_similar(error_log, limit: int = 5) -> list[SimilarError]:
    """Rows with the same `fingerprint` on any node, newest first.

    Excludes the input row itself so the UI doesn't echo "this error
    looks like itself".
    """
    from .models import ErrorLog

    if not getattr(error_log, "fingerprint", None):
        return []
    qs = (
        ErrorLog.objects.filter(fingerprint=error_log.fingerprint)
        .exclude(pk=error_log.pk)
        .order_by("-created_at")[:limit]
    )
    out: list[SimilarError] = []
    for row in qs:
        out.append(
            {
                "id": row.pk,
                "fingerprint": row.fingerprint or "",
                "error_message": (row.error_message or "")[:200],
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "acknowledged": bool(row.acknowledged),
            }
        )
    return out


def past_resolutions_for(error_log, limit: int = 3) -> list[SimilarError]:
    """Only the acknowledged rows — "we fixed this before" proof."""
    from .models import ErrorLog

    if not getattr(error_log, "fingerprint", None):
        return []
    qs = (
        ErrorLog.objects.filter(fingerprint=error_log.fingerprint, acknowledged=True)
        .exclude(pk=error_log.pk)
        .order_by("-created_at")[:limit]
    )
    return [
        {
            "id": row.pk,
            "fingerprint": row.fingerprint or "",
            "error_message": (row.error_message or "")[:200],
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "acknowledged": True,
        }
        for row in qs
    ]


def remedies_for(error_log) -> list[RemedyCandidate]:
    """Combines `fix_suggestions._RULES` hits with acknowledged-fix
    notes from prior ErrorLog rows into one carousel.
    """
    out: list[RemedyCandidate] = []

    # Rule-based remedies from the GT registry.
    try:
        from .fix_suggestions import _RULES

        msg = (error_log.error_message or "").lower()
        for pattern, remedy in _RULES:
            if pattern.search(msg):
                out.append(
                    {
                        "title": "Recommended fix",
                        "plain_english": remedy,
                        "source": "fix_rule",
                    }
                )
    except Exception:  # noqa: BLE001
        pass

    # Past acknowledgements — the reviewer wrote `why` when they ack'd.
    for resolved in past_resolutions_for(error_log, limit=2):
        out.append(
            {
                "title": f"Previously fixed ({resolved['created_at'][:10]})",
                "plain_english": resolved["error_message"],
                "source": "past_ack",
            }
        )
    return out[:5]


def runbook_match_for(error_log) -> RunbookMatch | None:
    """Phase MX2 / Gap 320 — guess a `docs/runbooks/*.md` match.

    We don't crawl the filesystem at request time — that would be a
    flaky dependency. Instead, `error_log.how_to_fix` already contains
    a curated suggestion; we derive a probable runbook filename from
    the first word of the job_type + step for deep-link navigation.
    The runbook library (Phase MX3 Gap 339) is where real content
    lives; this is just the cross-reference.
    """
    job_type = (error_log.job_type or "").strip().lower().split("_", 1)[0]
    step = (error_log.step or "").strip().lower().split(".", 1)[0]
    if not job_type and not step:
        return None
    slug = "-".join(p for p in (job_type, step) if p)
    if not slug:
        return None
    return {
        "path": f"docs/runbooks/{slug}.md",
        "heading": (job_type + " / " + step).strip("/ "),
        "confidence": 0.6 if job_type and step else 0.3,
    }


def reach_count_for(error_log) -> dict:
    """Phase MX2 / Gap 321 — "how many users hit this?"

    Aggregates by `node_id` so the answer is "N nodes, M occurrences
    total". We don't track end-user identities on ErrorLog rows.
    """
    from .models import ErrorLog

    if not getattr(error_log, "fingerprint", None):
        return {"node_count": 1, "total_occurrences": error_log.occurrence_count}
    agg = ErrorLog.objects.filter(fingerprint=error_log.fingerprint).aggregate(
        nodes=Count("node_id", distinct=True),
        total=Count("id"),
    )
    # `total` above is row count. Actual occurrences sum across rows.
    total_occ = sum(
        r.occurrence_count
        for r in ErrorLog.objects.filter(fingerprint=error_log.fingerprint).only(
            "occurrence_count"
        )
    )
    return {
        "node_count": agg["nodes"] or 1,
        "total_occurrences": total_occ,
    }


def severity_trend_for(error_log, days: int = 14) -> list[SeverityTrendPoint]:
    """Phase MX2 / Gap 322 — per-day counts of this error's category.

    Bucketed by date(created_at) so the chart has one bar per day.
    Uses the severity as the grouping key — "all high-severity errors
    over the last fortnight", not just this fingerprint.
    """
    from .models import ErrorLog

    cutoff = timezone.now() - timedelta(days=days)
    rows = ErrorLog.objects.filter(
        severity=error_log.severity, created_at__gte=cutoff
    ).values_list("created_at", flat=True)
    day_counts: Counter[str] = Counter()
    for ts in rows:
        day_counts[ts.date().isoformat()] += 1
    # Fill gaps so the chart has a contiguous x-axis.
    today = timezone.now().date()
    out: list[SeverityTrendPoint] = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        out.append({"day": day, "count": day_counts.get(day, 0)})
    return out


__all__ = [
    "find_similar",
    "past_resolutions_for",
    "remedies_for",
    "runbook_match_for",
    "reach_count_for",
    "severity_trend_for",
]
