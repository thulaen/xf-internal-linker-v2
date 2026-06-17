from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone as datetime_timezone
from typing import Any
from urllib.parse import urlparse

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.core.models import AppSetting


@dataclass(frozen=True, slots=True)
class DSTPTransitionCounts:
    transition_counts: dict[tuple[int, int], int]
    out_degrees: dict[int, int]
    visits_processed: int
    actions_seen: int


@dataclass(frozen=True, slots=True)
class AnalyticsTransitionObservation:
    """One ordered page movement seen by Matomo or Google Analytics 4."""

    source: str
    site_id: str
    source_content_id: int
    dest_content_id: int
    occurred_at: datetime | None
    count: int = 1
    visit_id: str = ""


def normalize_analytics_path(raw_url: str | None) -> str:
    """Return a stable path key from a Matomo or GA4 page URL."""
    raw = str(raw_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = parsed.path if parsed.scheme or parsed.netloc else raw.split("?", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    return path.rstrip("/") or "/"


def observations_to_deduped_transition_counts(
    observations: list[AnalyticsTransitionObservation],
) -> DSTPTransitionCounts:
    """Collapse matching Matomo and Google observations before DSTP counts them."""
    by_key: dict[str, tuple[tuple[int, int], int]] = {}
    actions_seen = 0
    for index, observation in enumerate(observations):
        if observation.source_content_id == observation.dest_content_id:
            continue
        count = max(0, int(observation.count))
        if count == 0:
            continue
        key = _transition_dedup_key(observation, index=index)
        pair = (observation.source_content_id, observation.dest_content_id)
        existing = by_key.get(key)
        by_key[key] = (pair, max(count, existing[1] if existing else 0))
        actions_seen += count

    transition_counts: Counter[tuple[int, int]] = Counter()
    out_degrees: Counter[int] = Counter()
    for (source_id, dest_id), count in by_key.values():
        transition_counts[(source_id, dest_id)] += count
        out_degrees[source_id] += count
    return DSTPTransitionCounts(
        transition_counts=dict(transition_counts),
        out_degrees=dict(out_degrees),
        visits_processed=len(by_key),
        actions_seen=actions_seen,
    )


def _transition_dedup_key(
    observation: AnalyticsTransitionObservation,
    *,
    index: int,
) -> str:
    visit_id = observation.visit_id.strip()
    if visit_id:
        return (
            f"visit:{visit_id}:"
            f"{observation.source_content_id}:{observation.dest_content_id}"
        )
    if observation.occurred_at is None:
        return (
            f"{observation.source}:unknown:{index}:"
            f"{observation.source_content_id}:{observation.dest_content_id}"
        )
    bucket = observation.occurred_at.astimezone(datetime_timezone.utc).replace(
        second=0,
        microsecond=0,
    )
    return (
        f"{bucket.isoformat()}:"
        f"{observation.source_content_id}:{observation.dest_content_id}"
    )


def matomo_visits_to_transition_counts(
    visits: list[dict[str, Any]],
    path_to_content_id: dict[str, int],
) -> DSTPTransitionCounts:
    """Convert ordered Matomo visits into immediate page-to-page counts."""
    transition_counts: Counter[tuple[int, int]] = Counter()
    out_degrees: Counter[int] = Counter()
    visits_processed = 0
    actions_seen = 0
    for visit in visits:
        ordered_ids = _content_ids_from_matomo_visit(visit, path_to_content_id)
        actions_seen += len(ordered_ids)
        if len(ordered_ids) < 2:
            continue
        visits_processed += 1
        for source_id, dest_id in zip(ordered_ids, ordered_ids[1:]):
            if source_id == dest_id:
                continue
            transition_counts[(source_id, dest_id)] += 1
            out_degrees[source_id] += 1
    return DSTPTransitionCounts(
        transition_counts=dict(transition_counts),
        out_degrees=dict(out_degrees),
        visits_processed=visits_processed,
        actions_seen=actions_seen,
    )


def matomo_visits_to_transition_observations(
    visits: list[dict[str, Any]],
    path_to_content_id: dict[str, int],
    *,
    site_id: str,
) -> list[AnalyticsTransitionObservation]:
    """Convert ordered Matomo visits into source-neutral transition observations."""
    observations: list[AnalyticsTransitionObservation] = []
    for visit in visits:
        steps = _content_steps_from_matomo_visit(visit, path_to_content_id)
        visit_id = _matomo_shared_visit_id(visit)
        for source_step, dest_step in zip(steps, steps[1:]):
            source_id, _source_time = source_step
            dest_id, dest_time = dest_step
            if source_id == dest_id:
                continue
            observations.append(
                AnalyticsTransitionObservation(
                    source="matomo",
                    site_id=site_id,
                    source_content_id=source_id,
                    dest_content_id=dest_id,
                    occurred_at=dest_time,
                    visit_id=visit_id,
                )
            )
    return observations


def ga4_page_rows_to_transition_observations(
    rows: list[dict[str, Any]],
    path_to_content_id: dict[str, int],
    *,
    site_id: str,
) -> list[AnalyticsTransitionObservation]:
    """Convert GA4 page-view rows into ordered transition observations."""
    observations: list[AnalyticsTransitionObservation] = []
    for row in rows:
        occurred_at = _parse_ga4_date_hour_minute(_ga4_dimension(row, 0))
        source_id = path_to_content_id.get(normalize_analytics_path(_ga4_dimension(row, 1)))
        dest_id = path_to_content_id.get(normalize_analytics_path(_ga4_dimension(row, 2)))
        if source_id is None or dest_id is None or source_id == dest_id:
            continue
        observations.append(
            AnalyticsTransitionObservation(
                source="ga4",
                site_id=site_id,
                source_content_id=source_id,
                dest_content_id=dest_id,
                occurred_at=occurred_at,
                count=_ga4_row_count(row),
                visit_id=_shared_visit_id(_ga4_dimension(row, 3)),
            )
        )
    return observations


def _shared_visit_id(value: Any) -> str:
    return str(value or "").strip()


def _matomo_shared_visit_id(visit: dict[str, Any]) -> str:
    for key in ("xfil_visit_id", "xfilVisitId"):
        visit_id = _shared_visit_id(visit.get(key))
        if visit_id:
            return visit_id
    return _matomo_custom_variable_visit_id(visit.get("customVariables"))


def _matomo_custom_variable_visit_id(value: Any) -> str:
    if isinstance(value, list):
        return _first_matomo_custom_variable_visit_id(value)
    if isinstance(value, dict):
        return _matomo_custom_variable_dict_visit_id(value)
    return ""


def _first_matomo_custom_variable_visit_id(values: list[Any]) -> str:
    for item in values:
        visit_id = _matomo_custom_variable_visit_id(item)
        if visit_id:
            return visit_id
    return ""


def _matomo_custom_variable_dict_visit_id(value: dict[str, Any]) -> str:
    direct = _shared_visit_id(value.get("xfil_visit_id"))
    if direct:
        return direct
    named = _visit_id_from_named_matomo_variable(value)
    if named:
        return named
    nested_values = [item for item in value.values() if isinstance(item, (dict, list))]
    return _first_matomo_custom_variable_visit_id(nested_values)


def _visit_id_from_named_matomo_variable(value: dict[str, Any]) -> str:
    name = _shared_visit_id(value.get("name") or value.get("customVariableName"))
    if name != "xfil_visit_id":
        return ""
    return _shared_visit_id(value.get("value") or value.get("customVariableValue"))


def _content_ids_from_matomo_visit(
    visit: dict[str, Any],
    path_to_content_id: dict[str, int],
) -> list[int]:
    content_ids: list[int] = []
    previous_id: int | None = None
    for action in visit.get("actionDetails") or []:
        if not _is_page_action(action):
            continue
        content_id = path_to_content_id.get(_action_path(action))
        if content_id is None or content_id == previous_id:
            continue
        content_ids.append(content_id)
        previous_id = content_id
    return content_ids


def _content_steps_from_matomo_visit(
    visit: dict[str, Any],
    path_to_content_id: dict[str, int],
) -> list[tuple[int, datetime | None]]:
    content_steps: list[tuple[int, datetime | None]] = []
    previous_id: int | None = None
    for action in visit.get("actionDetails") or []:
        if not _is_page_action(action):
            continue
        content_id = path_to_content_id.get(_action_path(action))
        if content_id is None or content_id == previous_id:
            continue
        content_steps.append((content_id, _action_observed_at(action)))
        previous_id = content_id
    return content_steps


def _is_page_action(action: Any) -> bool:
    if not isinstance(action, dict):
        return False
    action_type = str(action.get("type") or "action").lower()
    return action_type in {"action", "pageview"}


def _action_path(action: dict[str, Any]) -> str:
    for key in ("url", "urlPage", "pageUrl"):
        path = normalize_analytics_path(action.get(key))
        if path:
            return path
    return ""


def _action_observed_at(action: dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "serverTimePretty", "serverDatePretty"):
        parsed = _parse_observed_at(action.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_observed_at(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=datetime_timezone.utc)
    parsed = parse_datetime(raw)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime_timezone.utc)
    return parsed


def _ga4_dimension(row: dict[str, Any], index: int) -> str:
    values = row.get("dimensionValues") or []
    if index >= len(values):
        return ""
    return str(values[index].get("value") or "")


def _ga4_row_count(row: dict[str, Any]) -> int:
    values = row.get("metricValues") or []
    if not values:
        return 0
    try:
        return int(float(values[0].get("value") or 0))
    except (TypeError, ValueError):
        return 0


def _parse_ga4_date_hour_minute(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if len(raw) != 12 or not raw.isdigit():
        return None
    return datetime.strptime(raw, "%Y%m%d%H%M").replace(tzinfo=datetime_timezone.utc)


def content_path_to_id() -> dict[str, int]:
    """Return URL path keys for active content rows."""
    from apps.content.models import ContentItem

    path_to_id: dict[str, int] = {}
    rows = ContentItem.objects.filter(is_deleted=False).values_list("id", "url")
    for content_id, url in rows.iterator(chunk_size=2000):
        path = normalize_analytics_path(url)
        if path:
            path_to_id[path] = int(content_id)
    return path_to_id


def upsert_directional_transition_edges(
    *,
    source: str,
    site_id: str,
    transition_counts: dict[tuple[int, int], int],
    out_degrees: dict[int, int],
    window_start: date,
    window_end: date,
) -> int:
    """Persist compact DSTP transition counts without duplicate pair rows."""
    from apps.graph.models import DirectionalTransitionEdge

    active_pairs = set(transition_counts)
    rows_written = 0
    with transaction.atomic():
        for (source_id, dest_id), count in transition_counts.items():
            DirectionalTransitionEdge.objects.update_or_create(
                source=source,
                site_id=site_id,
                source_content_item_id=source_id,
                dest_content_item_id=dest_id,
                defaults={
                    "transition_count": max(0, int(count)),
                    "source_transition_count": max(0, int(out_degrees.get(source_id, 0))),
                    "data_window_start": window_start,
                    "data_window_end": window_end,
                },
            )
            rows_written += 1
        stale_ids = [
            edge_id
            for edge_id, source_id, dest_id in DirectionalTransitionEdge.objects.filter(
                source=source,
                site_id=site_id,
            )
            .values_list("id", "source_content_item_id", "dest_content_item_id")
            .iterator(chunk_size=2000)
            if (int(source_id), int(dest_id)) not in active_pairs
        ]
        if stale_ids:
            DirectionalTransitionEdge.objects.filter(id__in=stale_ids).delete()
    return rows_written


def store_deduped_dstp_observations(
    *,
    site_id: str,
    observations: list[AnalyticsTransitionObservation],
    window_start: date,
    window_end: date,
) -> DSTPTransitionCounts:
    """Store one combined DSTP edge set from already-fetched analytics rows."""
    counts = observations_to_deduped_transition_counts(observations)
    upsert_directional_transition_edges(
        source="combined",
        site_id=site_id,
        transition_counts=counts.transition_counts,
        out_degrees=counts.out_degrees,
        window_start=window_start,
        window_end=window_end,
    )
    return counts


def fetch_and_store_matomo_dstp_transitions(
    *,
    lookback_days: int | None = None,
) -> DSTPTransitionCounts:
    """Fetch ordered Matomo visits and store DSTP transition counts."""
    base_url, token_auth, site_id, days = _matomo_dstp_settings(lookback_days)
    window_end = timezone.localdate()
    window_start = window_end - timedelta(days=days)
    visits = _fetch_matomo_live_visits(
        base_url=base_url,
        token_auth=token_auth,
        site_id=site_id,
        window_start=window_start,
        window_end=window_end,
    )
    counts = matomo_visits_to_transition_counts(visits, content_path_to_id())
    upsert_directional_transition_edges(
        source="matomo",
        site_id=site_id,
        transition_counts=counts.transition_counts,
        out_degrees=counts.out_degrees,
        window_start=window_start,
        window_end=window_end,
    )
    return counts


def _matomo_dstp_settings(lookback_days: int | None) -> tuple[str, str, str, int]:
    base_url = AppSetting.get_str("analytics.matomo_url", "").strip().rstrip("/")
    token_auth = AppSetting.get_str("analytics.matomo_token_auth", "").strip()
    site_id = AppSetting.get_str("analytics.matomo_site_id_xenforo", "").strip()
    days = lookback_days or AppSetting.get_int("analytics.matomo_sync_lookback_days", 7)
    if not AppSetting.get_bool("analytics.matomo_enabled", False):
        raise RuntimeError("Matomo collection is disabled in settings.")
    if not AppSetting.get_bool("analytics.matomo_sync_enabled", False):
        raise RuntimeError("Matomo sync is disabled in settings.")
    if not base_url or not token_auth or not site_id:
        raise RuntimeError("DSTP needs Matomo URL, XenForo site id, and token.")
    return base_url, token_auth, site_id, max(1, int(days))


def _fetch_matomo_live_visits(
    *,
    base_url: str,
    token_auth: str,
    site_id: str,
    window_start: date,
    window_end: date,
) -> list[dict[str, Any]]:
    from apps.analytics.sync import _matomo_api_get

    payload = _matomo_api_get(
        base_url=base_url,
        token_auth=token_auth,
        method="Live.getLastVisitsDetails",
        params={
            "idSite": site_id,
            "period": "range",
            "date": f"{window_start.isoformat()},{window_end.isoformat()}",
            "filter_limit": "-1",
        },
    )
    return payload if isinstance(payload, list) else []
