"""Velocity score calculator for content_items.

Velocity v2 uses per-import metric snapshots to approximate actual rate-of-change
instead of relying on lifetime counts alone. The score combines:

- recent engagement rate (views / replies / downloads deltas over snapshot interval)
- recency of last activity
- orphan-page boost
- thin-content penalty

V2 change from V1: replaces raw SQLite queries with Django ORM;
removes Flask config dependency (reads settings from AppSetting model).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import log1p

logger = logging.getLogger(__name__)
NodeKey = tuple[int, str]

SECONDS_PER_DAY = 86400.0
MIN_SNAPSHOT_INTERVAL_DAYS = 1.0
BOOTSTRAP_MIN_DAYS = 7.0
BOOTSTRAP_MAX_DAYS = 30.0
RECENCY_HALF_LIFE_DAYS = 21.0
THREAD_REPLY_WEIGHT = 4.0
RESOURCE_REPLY_WEIGHT = 2.0
RESOURCE_DOWNLOAD_WEIGHT = 6.0
ORPHAN_MULTIPLIER = 1.5
THIN_MULTIPLIER = 0.1
THIN_CONTENT_THRESHOLD_CHARS = 300
SNAPSHOT_RETENTION_COUNT = 2


@dataclass(frozen=True, slots=True)
class VelocitySettings:
    """All tuneable velocity constants, loadable from the AppSetting model."""

    recency_half_life_days: float = RECENCY_HALF_LIFE_DAYS
    orphan_multiplier: float = ORPHAN_MULTIPLIER
    thin_content_threshold_chars: int = THIN_CONTENT_THRESHOLD_CHARS
    thin_content_penalty_multiplier: float = THIN_MULTIPLIER
    thread_reply_weight: float = THREAD_REPLY_WEIGHT
    resource_reply_weight: float = RESOURCE_REPLY_WEIGHT
    resource_download_weight: float = RESOURCE_DOWNLOAD_WEIGHT
    bootstrap_min_days: float = BOOTSTRAP_MIN_DAYS
    bootstrap_max_days: float = BOOTSTRAP_MAX_DAYS
    min_snapshot_interval_days: float = MIN_SNAPSHOT_INTERVAL_DAYS
    snapshot_retention_count: int = SNAPSHOT_RETENTION_COUNT


_SETTING_KEY_MAP: dict[str, str] = {
    "vel_recency_half_life_days": "recency_half_life_days",
    "vel_orphan_multiplier": "orphan_multiplier",
    "vel_thin_content_threshold_chars": "thin_content_threshold_chars",
    "vel_thin_content_penalty_multiplier": "thin_content_penalty_multiplier",
    "vel_thread_reply_weight": "thread_reply_weight",
    "vel_resource_reply_weight": "resource_reply_weight",
    "vel_resource_download_weight": "resource_download_weight",
    "vel_bootstrap_min_days": "bootstrap_min_days",
    "vel_bootstrap_max_days": "bootstrap_max_days",
    "vel_min_snapshot_interval_days": "min_snapshot_interval_days",
    "vel_snapshot_retention_count": "snapshot_retention_count",
}


def load_velocity_settings() -> VelocitySettings:
    """Load velocity settings from AppSetting model, falling back to defaults."""
    from apps.core.models import AppSetting

    rows = AppSetting.objects.filter(category="velocity").values_list(
        "key", "value", "value_type"
    )
    if not rows:
        return VelocitySettings()

    kwargs: dict[str, object] = {}
    for key, value, value_type in rows:
        field_name = _SETTING_KEY_MAP.get(key)
        if field_name is None:
            continue
        try:
            kwargs[field_name] = _coerce(value, value_type)
        except (ValueError, TypeError):
            pass
    return VelocitySettings(**kwargs)


def _coerce(value: str, value_type: str) -> object:
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    if value_type == "bool":
        return value.lower() in ("true", "1", "yes")
    return value


@dataclass(frozen=True, slots=True)
class ContentRow:
    """Subset of ContentItem columns needed for velocity calculation."""

    content_id: int
    content_type: str
    view_count: int
    reply_count: int
    download_count: int
    post_date: int | None
    last_post_date: int | None
    is_deleted: bool


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """Previous import metrics for a content item."""

    captured_at: int
    view_count: int
    reply_count: int
    download_count: int


def calculate_velocity_score(
    row: ContentRow,
    *,
    reference_ts: int,
    previous_snapshot: MetricSnapshot | None,
    has_incoming_link: bool,
    primary_clean_text_len: int | None,
    settings: VelocitySettings = VelocitySettings(),
) -> float:
    """Compute velocity score for a single content item (DB-free, testable)."""
    if row.is_deleted:
        return 0.0

    view_rate, reply_rate, download_rate = _compute_activity_rates(
        row,
        previous_snapshot=previous_snapshot,
        reference_ts=reference_ts,
        settings=settings,
    )

    raw_base = log1p(view_rate)
    if row.content_type == "resource":
        raw_base += settings.resource_reply_weight * log1p(reply_rate)
        raw_base += settings.resource_download_weight * log1p(download_rate)
    else:
        raw_base += settings.thread_reply_weight * log1p(reply_rate)

    freshness_multiplier = _compute_freshness_multiplier(
        row,
        reference_ts=reference_ts,
        settings=settings,
    )
    orphan_multiplier = settings.orphan_multiplier if not has_incoming_link else 1.0

    thin_multiplier = 1.0
    if (
        row.reply_count == 0
        and primary_clean_text_len is not None
        and primary_clean_text_len < settings.thin_content_threshold_chars
    ):
        thin_multiplier = settings.thin_content_penalty_multiplier

    return raw_base * freshness_multiplier * orphan_multiplier * thin_multiplier


def load_and_calculate(
    *,
    reference_ts: int,
    settings: VelocitySettings | None = None,
) -> dict[NodeKey, float]:
    """Load all content items and compute velocity scores via Django ORM."""
    from apps.content.models import ContentItem

    if settings is None:
        settings = load_velocity_settings()

    content_qs = (
        ContentItem.objects.filter()
        .values(
            "pk",
            "content_type",
            "view_count",
            "reply_count",
            "download_count",
            "post_date",
            "last_post_date",
            "is_deleted",
        )
        .order_by("pk", "content_type")
    )

    if not content_qs:
        return {}

    incoming_set = _load_incoming_set()
    previous_snapshots = _load_latest_snapshots()
    primary_text_lens = _load_primary_clean_text_lens()

    scores: dict[NodeKey, float] = {}
    for r in content_qs:
        row = ContentRow(
            content_id=r["pk"],
            content_type=r["content_type"],
            view_count=r["view_count"] or 0,
            reply_count=r["reply_count"] or 0,
            download_count=r["download_count"] or 0,
            post_date=r["post_date"],
            last_post_date=r["last_post_date"],
            is_deleted=bool(r["is_deleted"]),
        )
        key: NodeKey = (row.content_id, row.content_type)
        scores[key] = calculate_velocity_score(
            row,
            reference_ts=reference_ts,
            previous_snapshot=previous_snapshots.get(key),
            has_incoming_link=key in incoming_set,
            primary_clean_text_len=primary_text_lens.get(key),
            settings=settings,
        )
    return scores


def persist_velocity(scores: dict[NodeKey, float]) -> int:
    """Write velocity scores back to content_items via Django ORM.

    Returns the number of items updated.
    """
    from apps.content.models import ContentItem
    from django.db import transaction

    score_map = {pk: score for (pk, _content_type), score in scores.items()}

    with transaction.atomic():
        items_to_update = list(ContentItem.objects.filter(pk__in=score_map.keys()))
        for item in items_to_update:
            item.velocity_score = score_map[item.pk]

        if items_to_update:
            ContentItem.objects.bulk_update(
                items_to_update,
                ["velocity_score"],
                batch_size=1000,
            )

        updated_pks = [item.pk for item in items_to_update]
        ContentItem.objects.exclude(pk__in=updated_pks).update(velocity_score=0.0)

    logger.info("Velocity scores persisted: %d items updated.", len(items_to_update))
    return len(items_to_update)


def persist_metric_snapshots(*, import_job_id: str, captured_at: int) -> int:
    """Persist the current metrics view as one snapshot row per content item."""
    from apps.content.models import ContentItem, ContentMetricSnapshot

    rows = ContentItem.objects.values(
        "pk",
        "content_type",
        "view_count",
        "reply_count",
        "download_count",
        "post_date",
        "last_post_date",
        "is_deleted",
    ).order_by("pk", "content_type")

    snapshots = [
        ContentMetricSnapshot(
            import_job_id=import_job_id,
            captured_at=captured_at,
            content_item_id=row["pk"],
            view_count=row["view_count"] or 0,
            reply_count=row["reply_count"] or 0,
            download_count=row["download_count"] or 0,
            post_date=row["post_date"],
            last_post_date=row["last_post_date"],
            is_deleted=bool(row["is_deleted"]),
        )
        for row in rows
    ]

    ContentMetricSnapshot.objects.bulk_create(
        snapshots,
        update_conflicts=True,
        update_fields=[
            "captured_at",
            "view_count",
            "reply_count",
            "download_count",
            "post_date",
            "last_post_date",
            "is_deleted",
        ],
        unique_fields=["import_job_id", "content_item"],
    )
    return len(snapshots)


def prune_old_snapshots(*, keep: int = SNAPSHOT_RETENTION_COUNT) -> int:
    """Delete old snapshot rows, keeping only the latest *keep* per content item.

    Returns the number of rows deleted.
    """
    from apps.content.models import ContentMetricSnapshot
    from django.db.models import Max

    # Find the IDs to keep per content_item
    latest_ids = (
        ContentMetricSnapshot.objects.values("content_item")
        .annotate(max_id=Max("pk"))
        .values_list("max_id", flat=True)
    )

    # For simplicity, only one snapshot is kept here per item;
    # for the full keep>1 behaviour a raw SQL window function is used below.
    if keep == 1:
        deleted, _ = ContentMetricSnapshot.objects.exclude(pk__in=latest_ids).delete()
        return deleted

    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM content_contentmetricsnapshot
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY content_item_id
                               ORDER BY captured_at DESC, id DESC
                           ) AS rn
                    FROM content_contentmetricsnapshot
                ) ranked
                WHERE rn <= %s
            )
            """,
            [keep],
        )
        return cursor.rowcount


def run_velocity(*, reference_ts: int) -> int:
    """Load, calculate, and persist velocity scores. Returns items updated."""
    settings = load_velocity_settings()
    scores = load_and_calculate(reference_ts=reference_ts, settings=settings)
    return persist_velocity(scores)


def _load_incoming_set() -> set[NodeKey]:
    from apps.graph.models import ExistingLink

    return set(
        ExistingLink.objects.filter(
            from_content_item__is_deleted=False,
            to_content_item__is_deleted=False,
        )
        .values_list("to_content_item__pk", "to_content_item__content_type")
        .distinct()
    )


def _load_latest_snapshots() -> dict[NodeKey, MetricSnapshot]:
    from apps.content.models import ContentMetricSnapshot
    from django.db.models import Max

    latest_ids = (
        ContentMetricSnapshot.objects.values("content_item")
        .annotate(max_id=Max("pk"))
        .values_list("max_id", flat=True)
    )
    rows = ContentMetricSnapshot.objects.filter(pk__in=latest_ids).values(
        "content_item__pk",
        "content_item__content_type",
        "captured_at",
        "view_count",
        "reply_count",
        "download_count",
    )
    return {
        (r["content_item__pk"], r["content_item__content_type"]): MetricSnapshot(
            captured_at=r["captured_at"],
            view_count=r["view_count"] or 0,
            reply_count=r["reply_count"] or 0,
            download_count=r["download_count"] or 0,
        )
        for r in rows
    }


def _load_primary_clean_text_lens() -> dict[NodeKey, int]:
    from apps.content.models import ContentItem, Post
    from django.db.models import OuterRef, Subquery, IntegerField
    from django.db.models.functions import Length

    thread_post_len = (
        Post.objects.filter(
            content_item=OuterRef("pk"),
        )
        .annotate(len=Length("clean_text"))
        .values("len")[:1]
    )

    qs = ContentItem.objects.annotate(
        clean_len=Subquery(thread_post_len, output_field=IntegerField())
    ).values_list("pk", "content_type", "clean_len")

    result: dict[NodeKey, int] = {}
    for pk, content_type, clean_len in qs:
        if clean_len is not None:
            result[(pk, content_type)] = clean_len
    return result


def _compute_activity_rates(
    row: ContentRow,
    *,
    previous_snapshot: MetricSnapshot | None,
    reference_ts: int,
    settings: VelocitySettings,
) -> tuple[float, float, float]:
    if previous_snapshot is not None:
        interval_days = max(
            (reference_ts - previous_snapshot.captured_at) / SECONDS_PER_DAY,
            settings.min_snapshot_interval_days,
        )
        view_delta = max(row.view_count - previous_snapshot.view_count, 0)
        reply_delta = max(row.reply_count - previous_snapshot.reply_count, 0)
        download_delta = max(row.download_count - previous_snapshot.download_count, 0)
        return (
            view_delta / interval_days,
            reply_delta / interval_days,
            download_delta / interval_days,
        )

    bootstrap_days = _estimate_bootstrap_days(
        row, reference_ts=reference_ts, settings=settings
    )
    return (
        max(row.view_count, 0) / bootstrap_days,
        max(row.reply_count, 0) / bootstrap_days,
        max(row.download_count, 0) / bootstrap_days,
    )


def _estimate_bootstrap_days(
    row: ContentRow,
    *,
    reference_ts: int,
    settings: VelocitySettings,
) -> float:
    if row.post_date is None or row.post_date >= reference_ts:
        return settings.bootstrap_max_days
    age_days = (reference_ts - row.post_date) / SECONDS_PER_DAY
    return min(max(age_days, settings.bootstrap_min_days), settings.bootstrap_max_days)


def _compute_freshness_multiplier(
    row: ContentRow,
    *,
    reference_ts: int,
    settings: VelocitySettings,
) -> float:
    activity_ts = (
        row.last_post_date if row.last_post_date is not None else row.post_date
    )
    if activity_ts is None:
        return 1.0
    days_since_activity = max((reference_ts - activity_ts) / SECONDS_PER_DAY, 0.0)
    return 0.5 ** (days_since_activity / settings.recency_half_life_days)
