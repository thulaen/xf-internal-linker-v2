"""Link Freshness scoring based on source-to-destination link history."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import math
from typing import Mapping

from django.utils import timezone


NodeKey = tuple[int, str]
NEUTRAL_LINK_FRESHNESS_SCORE = 0.5


@dataclass(frozen=True, slots=True)
class LinkFreshnessSettings:
    ranking_weight: float = 0.0
    recent_window_days: int = 30
    newest_peer_percent: float = 0.25
    min_peer_count: int = 3
    w_recent: float = 0.35
    w_growth: float = 0.35
    w_cohort: float = 0.20
    w_loss: float = 0.10


@dataclass(frozen=True, slots=True)
class LinkFreshnessPeerRow:
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    last_disappeared_at: datetime | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class LinkFreshnessResult:
    link_freshness_score: float
    freshness_bucket: str
    freshness_data_state: str
    total_peer_count: int
    active_peer_count: int
    recent_new_peer_count: int
    previous_new_peer_count: int
    recent_lost_peer_count: int
    recent_share: float
    growth_delta: float
    cohort_freshness: float
    recent_window_days: int
    newest_peer_percent: float
    min_peer_count: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def load_link_freshness_settings() -> LinkFreshnessSettings:
    """Load link-freshness settings from AppSetting, with safe defaults."""
    from apps.core.models import AppSetting

    rows = AppSetting.objects.filter(
        key__in=[
            "link_freshness.ranking_weight",
            "link_freshness.recent_window_days",
            "link_freshness.newest_peer_percent",
            "link_freshness.min_peer_count",
            "link_freshness.w_recent",
            "link_freshness.w_growth",
            "link_freshness.w_cohort",
            "link_freshness.w_loss",
        ]
    ).values_list("key", "value")
    raw = {key: value for key, value in rows}

    def _read_float(key: str, default: float) -> float:
        try:
            value = float(raw.get(key, default))
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    def _read_int(key: str, default: int) -> int:
        try:
            value = int(float(raw.get(key, default)))
        except (TypeError, ValueError):
            return default
        return value

    settings = LinkFreshnessSettings(
        ranking_weight=_read_float("link_freshness.ranking_weight", 0.0),
        recent_window_days=_read_int("link_freshness.recent_window_days", 30),
        newest_peer_percent=_read_float("link_freshness.newest_peer_percent", 0.25),
        min_peer_count=_read_int("link_freshness.min_peer_count", 3),
        w_recent=_read_float("link_freshness.w_recent", 0.35),
        w_growth=_read_float("link_freshness.w_growth", 0.35),
        w_cohort=_read_float("link_freshness.w_cohort", 0.20),
        w_loss=_read_float("link_freshness.w_loss", 0.10),
    )
    return settings


def classify_freshness_bucket(score: float) -> str:
    """Map a stored score to the public fresh/neutral/stale bucket."""
    if score >= 0.60:
        return "fresh"
    if score <= 0.40:
        return "stale"
    return "neutral"


def score_link_freshness_component(score: float) -> float:
    """Convert stored 0..1 score into the centered ranker component."""
    bounded = min(max(float(score), 0.0), 1.0)
    return 2.0 * (bounded - 0.5)


def neutral_link_freshness_result(
    *,
    data_state: str,
    settings: LinkFreshnessSettings,
    total_peer_count: int = 0,
    active_peer_count: int = 0,
) -> LinkFreshnessResult:
    return LinkFreshnessResult(
        link_freshness_score=NEUTRAL_LINK_FRESHNESS_SCORE,
        freshness_bucket="neutral",
        freshness_data_state=data_state,
        total_peer_count=total_peer_count,
        active_peer_count=active_peer_count,
        recent_new_peer_count=0,
        previous_new_peer_count=0,
        recent_lost_peer_count=0,
        recent_share=0.0,
        growth_delta=0.0,
        cohort_freshness=0.0,
        recent_window_days=settings.recent_window_days,
        newest_peer_percent=settings.newest_peer_percent,
        min_peer_count=settings.min_peer_count,
    )


def calculate_link_freshness(
    peer_rows: list[LinkFreshnessPeerRow],
    *,
    reference_time: datetime | None = None,
    settings: LinkFreshnessSettings = LinkFreshnessSettings(),
) -> LinkFreshnessResult:
    """Compute the bounded FR-007 score for one destination."""
    if reference_time is None:
        reference_time = timezone.now()

    total_peer_count = len(peer_rows)
    active_peer_count = sum(1 for row in peer_rows if row.is_active)
    if total_peer_count == 0:
        return neutral_link_freshness_result(
            data_state="neutral_missing_history",
            settings=settings,
        )

    valid_rows: list[LinkFreshnessPeerRow] = []
    for row in peer_rows:
        first_seen_at = row.first_seen_at
        last_seen_at = row.last_seen_at
        if first_seen_at is None or last_seen_at is None:
            return neutral_link_freshness_result(
                data_state="neutral_invalid_history",
                settings=settings,
                total_peer_count=total_peer_count,
                active_peer_count=active_peer_count,
            )
        if timezone.is_naive(first_seen_at) or timezone.is_naive(last_seen_at):
            return neutral_link_freshness_result(
                data_state="neutral_invalid_history",
                settings=settings,
                total_peer_count=total_peer_count,
                active_peer_count=active_peer_count,
            )
        if (
            first_seen_at > reference_time
            or last_seen_at > reference_time
            or last_seen_at < first_seen_at
        ):
            return neutral_link_freshness_result(
                data_state="neutral_invalid_history",
                settings=settings,
                total_peer_count=total_peer_count,
                active_peer_count=active_peer_count,
            )
        if row.last_disappeared_at is not None:
            if (
                timezone.is_naive(row.last_disappeared_at)
                or row.last_disappeared_at > reference_time
            ):
                return neutral_link_freshness_result(
                    data_state="neutral_invalid_history",
                    settings=settings,
                    total_peer_count=total_peer_count,
                    active_peer_count=active_peer_count,
                )
        valid_rows.append(row)

    if total_peer_count < settings.min_peer_count:
        return neutral_link_freshness_result(
            data_state="neutral_thin_history",
            settings=settings,
            total_peer_count=total_peer_count,
            active_peer_count=active_peer_count,
        )

    recent_window = timedelta(days=settings.recent_window_days)
    recent_cutoff = reference_time - recent_window
    previous_cutoff = reference_time - (recent_window * 2)
    oldest_first_seen = min(
        row.first_seen_at for row in valid_rows if row.first_seen_at is not None
    )
    if oldest_first_seen > previous_cutoff:
        return neutral_link_freshness_result(
            data_state="neutral_thin_history",
            settings=settings,
            total_peer_count=total_peer_count,
            active_peer_count=active_peer_count,
        )

    recent_new_peer_count = sum(
        1
        for row in valid_rows
        if row.first_seen_at is not None and row.first_seen_at >= recent_cutoff
    )
    previous_new_peer_count = sum(
        1
        for row in valid_rows
        if row.first_seen_at is not None
        and previous_cutoff <= row.first_seen_at < recent_cutoff
    )
    recent_lost_peer_count = sum(
        1
        for row in valid_rows
        if not row.is_active
        and row.last_disappeared_at is not None
        and row.last_disappeared_at >= recent_cutoff
    )

    sorted_rows = sorted(
        valid_rows,
        key=lambda row: row.first_seen_at or reference_time,
        reverse=True,
    )
    newest_peer_count = max(
        1, math.ceil(total_peer_count * settings.newest_peer_percent)
    )
    newest_cohort = sorted_rows[:newest_peer_count]
    cohort_oldest_first_seen = min(
        row.first_seen_at for row in newest_cohort if row.first_seen_at is not None
    )

    oldest_peer_age_days = max(_age_days(reference_time, oldest_first_seen), 0.0)
    oldest_recent_cohort_age_days = max(
        _age_days(reference_time, cohort_oldest_first_seen), 0.0
    )

    recent_share = recent_new_peer_count / total_peer_count
    growth_delta = _clamp(
        (recent_new_peer_count - previous_new_peer_count) / total_peer_count,
        -1.0,
        1.0,
    )
    cohort_freshness = 1.0 - _clamp(
        oldest_recent_cohort_age_days / max(oldest_peer_age_days, 1.0),
        0.0,
        1.0,
    )
    loss_share = recent_lost_peer_count / total_peer_count

    recent_component = (2.0 * recent_share) - 1.0
    cohort_component = (2.0 * cohort_freshness) - 1.0
    freshness_centered = _clamp(
        (settings.w_recent * recent_component)
        + (settings.w_growth * growth_delta)
        + (settings.w_cohort * cohort_component)
        - (settings.w_loss * loss_share),
        -1.0,
        1.0,
    )
    link_freshness_score = 0.5 + (0.5 * freshness_centered)

    return LinkFreshnessResult(
        link_freshness_score=link_freshness_score,
        freshness_bucket=classify_freshness_bucket(link_freshness_score),
        freshness_data_state="computed",
        total_peer_count=total_peer_count,
        active_peer_count=active_peer_count,
        recent_new_peer_count=recent_new_peer_count,
        previous_new_peer_count=previous_new_peer_count,
        recent_lost_peer_count=recent_lost_peer_count,
        recent_share=recent_share,
        growth_delta=growth_delta,
        cohort_freshness=cohort_freshness,
        recent_window_days=settings.recent_window_days,
        newest_peer_percent=settings.newest_peer_percent,
        min_peer_count=settings.min_peer_count,
    )


def get_destination_link_freshness_diagnostics(
    destination_id: int,
    *,
    reference_time: datetime | None = None,
    settings: LinkFreshnessSettings | None = None,
) -> LinkFreshnessResult:
    """Compute one destination's live diagnostics from stored history rows."""
    from apps.graph.models import LinkFreshnessEdge

    settings = settings or load_link_freshness_settings()
    rows = [
        LinkFreshnessPeerRow(
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
            last_disappeared_at=row.last_disappeared_at,
            is_active=row.is_active,
        )
        for row in LinkFreshnessEdge.objects.filter(
            to_content_item_id=destination_id
        ).only(
            "first_seen_at",
            "last_seen_at",
            "last_disappeared_at",
            "is_active",
        )
    ]
    return calculate_link_freshness(
        rows, reference_time=reference_time, settings=settings
    )


def load_all_link_freshness_scores(
    *,
    reference_time: datetime | None = None,
    settings: LinkFreshnessSettings | None = None,
) -> dict[NodeKey, LinkFreshnessResult]:
    """Load all destination histories and compute scores for the full content set."""
    from apps.content.models import ContentItem
    from apps.graph.models import LinkFreshnessEdge

    settings = settings or load_link_freshness_settings()
    history_by_destination: dict[int, list[LinkFreshnessPeerRow]] = {}
    for row in LinkFreshnessEdge.objects.order_by("to_content_item_id").values(
        "to_content_item_id",
        "to_content_item__content_type",
        "first_seen_at",
        "last_seen_at",
        "last_disappeared_at",
        "is_active",
    ):
        history_by_destination.setdefault(row["to_content_item_id"], []).append(
            LinkFreshnessPeerRow(
                first_seen_at=row["first_seen_at"],
                last_seen_at=row["last_seen_at"],
                last_disappeared_at=row["last_disappeared_at"],
                is_active=bool(row["is_active"]),
            )
        )

    results: dict[NodeKey, LinkFreshnessResult] = {}
    for pk, content_type in ContentItem.objects.values_list(
        "pk", "content_type"
    ).order_by("pk"):
        results[(pk, content_type)] = calculate_link_freshness(
            history_by_destination.get(pk, []),
            reference_time=reference_time,
            settings=settings,
        )
    return results


def persist_link_freshness_scores(
    results: Mapping[NodeKey, LinkFreshnessResult],
) -> int:
    """Persist link-freshness scores back to content items."""
    from apps.content.models import ContentItem

    ContentItem.objects.all().update(link_freshness_score=NEUTRAL_LINK_FRESHNESS_SCORE)
    updated = 0
    for (pk, content_type), result in results.items():
        updated += ContentItem.objects.filter(pk=pk, content_type=content_type).update(
            link_freshness_score=result.link_freshness_score
        )
    return updated


def run_link_freshness(
    *,
    reference_time: datetime | None = None,
    settings_map: Mapping[str, float | int] | None = None,
) -> dict[str, int | float]:
    """Compute and persist link-freshness scores for all content items."""
    settings = (
        LinkFreshnessSettings(**settings_map)
        if settings_map is not None
        else load_link_freshness_settings()
    )
    results = load_all_link_freshness_scores(
        reference_time=reference_time,
        settings=settings,
    )
    persist_link_freshness_scores(results)

    data_state_counts: dict[str, int] = {}
    for result in results.values():
        data_state_counts[result.freshness_data_state] = (
            data_state_counts.get(result.freshness_data_state, 0) + 1
        )

    return {
        "content_item_count": len(results),
        "computed_count": data_state_counts.get("computed", 0),
        "neutral_missing_history_count": data_state_counts.get(
            "neutral_missing_history", 0
        ),
        "neutral_thin_history_count": data_state_counts.get("neutral_thin_history", 0),
        "neutral_invalid_history_count": data_state_counts.get(
            "neutral_invalid_history", 0
        ),
    }


def _age_days(reference_time: datetime, timestamp: datetime) -> float:
    return max((reference_time - timestamp).total_seconds() / 86400.0, 0.0)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
