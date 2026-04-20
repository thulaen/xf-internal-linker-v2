"""
Phase MX3 / Gaps 323-330 — Data quality helpers.

Read-only aggregators the Data Quality card (frontend) consumes.
Nothing here persists new state — every metric is computed on demand
from existing tables. That keeps the feature opt-in (no cron cost)
while giving operators a quick "how healthy is the input?" view.

Gap mapping:
  * 323 scorecard per source   → scorecard()
  * 324 freshness dashboard     → freshness_snapshot()
  * 325 anomaly detector        → anomalies()
  * 326 data-volume trend lines → volume_trend()
  * 327 backfill wizard hint    → backfill_gaps()
  * 328 duplicate-detection     → duplicate_counts()
  * 329 stale-data auto-alert   → stale_sources()
  * 330 schema-change detector  → schema_drift()  (stub — filled when
    the ingest layer records observed payload shapes)
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean, stdev
from typing import TypedDict

from django.db.models import Count, Max
from django.utils import timezone


class SourceScorecard(TypedDict):
    source: str
    completeness_pct: float
    freshness_hours: float | None
    accuracy_pct: float
    sample_size: int


class VolumePoint(TypedDict):
    day: str
    count: int


class Anomaly(TypedDict):
    source: str
    plain_english: str
    severity: str  # "info" | "warning" | "error"


class StaleSource(TypedDict):
    source: str
    last_update: str
    hours_since: float


def scorecard() -> list[SourceScorecard]:
    """One row per connector: completeness, freshness, accuracy."""
    from apps.analytics.models import SearchMetric
    from apps.content.models import ContentItem

    out: list[SourceScorecard] = []
    # GSC / GA4 / Matomo — reuse SearchMetric rows.
    for source in ("gsc", "ga4", "matomo"):
        latest = (
            SearchMetric.objects.filter(source=source).aggregate(m=Max("date")).get("m")
        )
        last_dt = (
            timezone.make_aware(
                timezone.datetime.combine(latest, timezone.datetime.min.time())
            )
            if latest
            else None
        )
        sample = SearchMetric.objects.filter(source=source).count()
        freshness = None
        if last_dt:
            freshness = (timezone.now() - last_dt).total_seconds() / 3600
        out.append(
            {
                "source": source,
                "completeness_pct": _clamp_pct(sample / 30) if sample else 0.0,
                "freshness_hours": round(freshness, 1) if freshness else None,
                "accuracy_pct": 100.0,  # Accuracy proxy — all rows pass ingest validation.
                "sample_size": sample,
            }
        )

    # ContentItem — completeness = embedded-of-total, freshness = most-recent created.
    total = ContentItem.objects.count()
    from apps.pipeline.services.embeddings import get_current_embedding_filter

    embedded = ContentItem.objects.filter(
        embedding__isnull=False,
        **get_current_embedding_filter(),
    ).count()
    latest_ci = ContentItem.objects.aggregate(m=Max("created_at")).get("m")
    freshness = None
    if latest_ci:
        freshness = (timezone.now() - latest_ci).total_seconds() / 3600
    out.append(
        {
            "source": "content",
            "completeness_pct": _clamp_pct((embedded / total) * 100) if total else 0.0,
            "freshness_hours": round(freshness, 1) if freshness else None,
            "accuracy_pct": 100.0,
            "sample_size": total,
        }
    )
    return out


def freshness_snapshot() -> list[dict]:
    """Gap 324 — per-entity last-update timestamp, global view."""
    from apps.content.models import ContentItem
    from apps.suggestions.models import Suggestion, PipelineRun

    def _freshness(model) -> str | None:
        row = model.objects.aggregate(m=Max("created_at")).get("m")
        return row.isoformat() if row else None

    return [
        {"entity": "ContentItem", "latest": _freshness(ContentItem)},
        {"entity": "Suggestion", "latest": _freshness(Suggestion)},
        {"entity": "PipelineRun", "latest": _freshness(PipelineRun)},
    ]


def volume_trend(days: int = 14) -> dict[str, list[VolumePoint]]:
    """Gap 326 — ingestion rate per source, one series per connector."""
    from apps.analytics.models import SearchMetric
    from apps.content.models import ContentItem

    cutoff = (timezone.now() - timedelta(days=days)).date()
    out: dict[str, list[VolumePoint]] = {}
    for source in ("gsc", "ga4", "matomo"):
        rows = (
            SearchMetric.objects.filter(source=source, date__gte=cutoff)
            .values("date")
            .annotate(n=Count("id"))
            .order_by("date")
        )
        day_map = {r["date"].isoformat(): r["n"] for r in rows}
        out[source] = _densify(cutoff, days, day_map)

    # ContentItem imports — approximate via created_at by day.
    content_rows = (
        ContentItem.objects.filter(created_at__date__gte=cutoff)
        .extra(select={"day": "DATE(created_at)"})
        .values("day")
        .annotate(n=Count("id"))
    )
    content_map = {str(r["day"]): r["n"] for r in content_rows}
    out["content"] = _densify(cutoff, days, content_map)
    return out


def anomalies() -> list[Anomaly]:
    """Gap 325 — plain-English flag when today's count is >3-sigma off baseline."""
    out: list[Anomaly] = []
    trend = volume_trend(days=14)
    for source, points in trend.items():
        counts = [p["count"] for p in points[:-1]]  # baseline = last 13 days
        today = points[-1]["count"] if points else 0
        if len(counts) < 3:
            continue
        # `stdev` raises only on <2 samples — the length check above
        # already guards against that. Bare calls here keep bandit B112
        # (try/except/continue) from flagging the block.
        avg = mean(counts)
        sigma = stdev(counts)
        if sigma == 0:
            continue
        z = (today - avg) / sigma
        if z >= 3:
            out.append(
                {
                    "source": source,
                    "plain_english": (
                        f"{source.upper()} ingested {today:,} rows today - "
                        f"about {today / max(avg, 1):.1f}x the usual volume. "
                        f"Check the connector for a backlog or a replay."
                    ),
                    "severity": "warning",
                }
            )
        elif z <= -3:
            out.append(
                {
                    "source": source,
                    "plain_english": (
                        f"{source.upper()} ingested only {today:,} rows today - "
                        f"well below the {avg:.0f}-row baseline. "
                        f"Is the connector still healthy?"
                    ),
                    "severity": "error",
                }
            )
    return out


def duplicate_counts() -> dict[str, int]:
    """Gap 328 — per-source counts of likely-dupe rows."""
    from apps.content.models import ContentItem

    dupe_qs = (
        ContentItem.objects.values("external_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    content_dupes = sum(r["n"] - 1 for r in dupe_qs if r.get("external_id"))
    return {"content": content_dupes}


def stale_sources(threshold_hours: int = 48) -> list[StaleSource]:
    """Gap 329 — sources with no update past the threshold."""
    out: list[StaleSource] = []
    for row in scorecard():
        h = row["freshness_hours"]
        if h is not None and h >= threshold_hours:
            out.append(
                {
                    "source": row["source"],
                    "last_update": f"{h:.1f}h ago",
                    "hours_since": h,
                }
            )
    return out


def backfill_gaps(days: int = 30) -> dict[str, list[str]]:
    """Gap 327 — per-source list of days with zero ingestion."""
    trend = volume_trend(days=days)
    out: dict[str, list[str]] = {}
    for source, points in trend.items():
        out[source] = [p["day"] for p in points if p["count"] == 0]
    return out


def schema_drift() -> list[dict]:
    """Gap 330 — schema-change detector stub.

    Real implementation would hash incoming payload shapes per
    connector and raise when a new shape appears. Stubbed here so the
    frontend card doesn't 404; once the ingest layer records shapes
    in a `ConnectorPayloadShape` table, this function aggregates them.
    """
    return []


# ─── helpers ────────────────────────────────────────────────────────


def _clamp_pct(v: float) -> float:
    if v <= 0:
        return 0.0
    if v >= 100:
        return 100.0
    return round(v, 1)


def _densify(start: date, days: int, day_map: dict[str, int]) -> list[VolumePoint]:
    out: list[VolumePoint] = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        out.append({"day": day, "count": day_map.get(day, 0)})
    return out


__all__ = [
    "scorecard",
    "freshness_snapshot",
    "volume_trend",
    "anomalies",
    "duplicate_counts",
    "stale_sources",
    "backfill_gaps",
    "schema_drift",
]
