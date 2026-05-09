"""FR-016 Slice 3 sync helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import math
from typing import Any
from urllib.parse import urljoin

import requests
from django.db.models import Avg, Sum
from django.utils import timezone

from apps.content.models import ContentItem
from apps.sources.api_rate_limiter import rate_limited
from apps.suggestions.models import Suggestion

from ._polars_helpers import safe_aggregate_columnar, safe_aggregate_grouped_by_outer
from .country_filters import (
    BLOCKED_COUNTRY_CODES_ALPHA2,
    BLOCKED_COUNTRY_CODES_ALPHA3,
    BLOCKED_TELEMETRY_COUNTRY_VALUES,
    is_blocked_country,
)
from .ga4_client import build_ga4_data_service
from .gsc_client import build_gsc_service, fetch_gsc_performance_data
from .models import (
    AnalyticsSyncRun,
    SearchMetric,
    SuggestionTelemetryDaily,
    TelemetryCoverageDaily,
)

MATOMO_EVENT_FIELDS = {
    "suggestion_link_impression": "impressions",
    "suggestion_link_click": "clicks",
    "suggestion_destination_view": "destination_views",
    "suggestion_destination_engaged": "engaged_sessions",
    "suggestion_destination_conversion": "conversions",
    # Phase 2 engagement signals (plans/what-is-other-telemetry-*).
    # Source: Kim, Hassan, White & Zitouni (WSDM 2014).
    "suggestion_destination_quick_exit": "quick_exit_sessions",
    "suggestion_destination_dwell_30s": "dwell_30s_sessions",
    "suggestion_destination_dwell_60s": "dwell_60s_sessions",
}

GA4_EVENT_FIELDS = {
    "suggestion_link_impression": "impressions",
    "suggestion_link_click": "clicks",
    "suggestion_destination_engaged": "engaged_sessions",
    "suggestion_destination_conversion": "conversions",
    # Phase 2 engagement signals — mirror of MATOMO_EVENT_FIELDS.
    "suggestion_destination_quick_exit": "quick_exit_sessions",
    "suggestion_destination_dwell_30s": "dwell_30s_sessions",
    "suggestion_destination_dwell_60s": "dwell_60s_sessions",
}

MATOMO_EXCLUDED_SEGMENT = ";".join(
    f"countryCode!={country_code}" for country_code in BLOCKED_COUNTRY_CODES_ALPHA2
)


def _same_silo(suggestion: Suggestion) -> bool | None:
    destination_scope = getattr(suggestion.destination, "scope", None)
    host_scope = getattr(suggestion.host, "scope", None)
    if destination_scope is None or host_scope is None:
        return None
    if destination_scope.silo_group_id is None or host_scope.silo_group_id is None:
        return None
    return destination_scope.silo_group_id == host_scope.silo_group_id


def _algorithm_version_parts(suggestion: Suggestion) -> tuple[str, date | None, str]:
    if suggestion.pipeline_run and suggestion.pipeline_run.created_at:
        version_date = suggestion.pipeline_run.created_at.date()
        return (
            "pipeline_bundle",
            version_date,
            version_date.isoformat().replace("-", "_"),
        )
    return "pipeline_bundle", None, ""


def _coerce_count(row: dict[str, Any]) -> int:
    for key in ("nb_events", "nb_hits", "nb_actions", "nb_visits", "value"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return 0


def _walk_matomo_rows(
    rows: list[dict[str, Any]], *, current_action: str = ""
) -> list[tuple[str, str, int]]:
    parsed: list[tuple[str, str, int]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        action = current_action
        if label in MATOMO_EVENT_FIELDS:
            action = label
        elif action and label:
            parsed.append((label, action, _coerce_count(row)))

        for key in ("subtable", "subtables", "subRows"):
            nested = row.get(key)
            if isinstance(nested, list):
                parsed.extend(_walk_matomo_rows(nested, current_action=action))
    return parsed


def _normalize_ga4_value(value: str | None) -> str:
    raw = str(value or "").strip()
    if raw.lower() in {"(not set)", "(other)", "not set"}:
        return ""
    return raw


def _ga4_dimension_names(*, geo_granularity: str) -> list[str]:
    dimensions = [
        "date",
        "customEvent:suggestion_id",
        "deviceCategory",
        "sessionDefaultChannelGroup",
        "sessionSourceMedium",
    ]
    if geo_granularity in {"country", "country_region"}:
        dimensions.append("country")
    if geo_granularity == "country_region":
        dimensions.append("region")
    return dimensions


def _ga4_dimensions_from_row(
    *, row: dict[str, Any], dimension_names: list[str], geo_granularity: str
) -> dict[str, str]:
    values = [entry.get("value") for entry in row.get("dimensionValues", [])]
    mapped = dict(zip(dimension_names, values))
    country = _normalize_ga4_value(mapped.get("country"))
    region = (
        _normalize_ga4_value(mapped.get("region"))
        if geo_granularity == "country_region"
        else ""
    )
    return {
        "date": _normalize_ga4_value(mapped.get("date")),
        "suggestion_id": _normalize_ga4_value(mapped.get("customEvent:suggestion_id")),
        "device_category": _normalize_ga4_value(mapped.get("deviceCategory")),
        "default_channel_group": _normalize_ga4_value(
            mapped.get("sessionDefaultChannelGroup")
        ),
        "source_medium": _normalize_ga4_value(mapped.get("sessionSourceMedium")),
        "country": country if geo_granularity in {"country", "country_region"} else "",
        "region": region,
    }


def _ga4_metric_int(row: dict[str, Any], index: int) -> int:
    values = row.get("metricValues", [])
    if index >= len(values):
        return 0
    try:
        return int(float(values[index].get("value") or 0))
    except (TypeError, ValueError):
        return 0


def _ga4_metric_float(row: dict[str, Any], index: int) -> float:
    values = row.get("metricValues", [])
    if index >= len(values):
        return 0.0
    try:
        return float(values[index].get("value") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _fetch_ga4_rows(
    *,
    service,
    property_id: str,
    target_date: date,
    geo_granularity: str,
    event_name: str,
    metrics: list[str],
) -> list[dict[str, Any]]:
    dimension_names = _ga4_dimension_names(geo_granularity=geo_granularity)
    # FR-250: GA4 Data API has a 50,000-token daily quota; honour it via the
    # shared registry so a long lookback window can't blow the budget.
    with rate_limited("ga4_data_api"):
        response = (
            service.properties()
            .runReport(
                property=f"properties/{property_id}",
                body={
                    "dateRanges": [
                        {
                            "startDate": target_date.isoformat(),
                            "endDate": target_date.isoformat(),
                        }
                    ],
                    "dimensions": [{"name": name} for name in dimension_names],
                    "metrics": [{"name": name} for name in metrics],
                    "dimensionFilter": {
                        "filter": {
                            "fieldName": "eventName",
                            "stringFilter": {
                                "matchType": "EXACT",
                                "value": event_name,
                            },
                        }
                    },
                    "limit": 10000,
                },
            )
            .execute()
        )
    return response.get("rows", [])


def _matomo_api_get(
    *, base_url: str, token_auth: str, method: str, params: dict[str, Any]
) -> Any:
    api_url = urljoin(base_url.rstrip("/") + "/", "?module=API&format=JSON")
    # FR-250: every outbound Matomo Reporting-API call passes through the
    # token bucket so a sync loop can never DoS the operator's Matomo
    # instance. Citation in docs/specs/fr250-api-rate-limiter.md.
    with rate_limited("matomo_reporting_api"):
        response = requests.get(
            api_url,
            params={
                "method": method,
                "token_auth": token_auth,
                **params,
            },
            timeout=30,
        )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("result") == "error":
        raise RuntimeError(payload.get("message") or "Matomo returned an error.")
    return payload


def _fetch_matomo_event_rows(
    *, base_url: str, token_auth: str, site_id: str, target_date: date
) -> tuple[list[tuple[str, str, int]], int]:
    payload = _matomo_api_get(
        base_url=base_url,
        token_auth=token_auth,
        method="Events.getAction",
        params={
            "idSite": site_id,
            "period": "day",
            "date": target_date.isoformat(),
            "flat": 1,
            "expanded": 1,
            "secondaryDimension": "eventName",
            "segment": MATOMO_EXCLUDED_SEGMENT,
        },
    )
    rows = payload if isinstance(payload, list) else []
    parsed = _walk_matomo_rows(rows)
    return parsed, len(rows)


def _upsert_telemetry_row(
    *,
    target_date: date,
    suggestion: Suggestion,
    field_totals: dict[str, int],
    event_schema: str,
) -> tuple[int, int]:
    algorithm_key, algorithm_version_date, algorithm_version_slug = (
        _algorithm_version_parts(suggestion)
    )
    defaults = {
        "destination": suggestion.destination,
        "host": suggestion.host,
        "algorithm_key": algorithm_key,
        "algorithm_version_date": algorithm_version_date,
        "event_schema": event_schema,
        "source_label": _source_label_for(suggestion),
        "same_silo": _same_silo(suggestion),
        "impressions": int(field_totals.get("impressions", 0)),
        "clicks": int(field_totals.get("clicks", 0)),
        "destination_views": int(field_totals.get("destination_views", 0)),
        "engaged_sessions": int(field_totals.get("engaged_sessions", 0)),
        "conversions": int(field_totals.get("conversions", 0)),
        # Phase 2 engagement signals — safe defaults so old event sets that
        # predate the new events still upsert cleanly.
        "quick_exit_sessions": int(field_totals.get("quick_exit_sessions", 0)),
        "dwell_30s_sessions": int(field_totals.get("dwell_30s_sessions", 0)),
        "dwell_60s_sessions": int(field_totals.get("dwell_60s_sessions", 0)),
        "event_count": int(sum(field_totals.values())),
        "sessions": int(field_totals.get("destination_views", 0)),
        "is_attributed": True,
    }
    _, created = SuggestionTelemetryDaily.objects.update_or_create(
        date=target_date,
        telemetry_source="matomo",
        suggestion=suggestion,
        algorithm_version_slug=algorithm_version_slug,
        device_category="",
        default_channel_group="",
        source_medium="",
        country="",
        region="",
        is_attributed=True,
        defaults=defaults,
    )
    return (1, 0) if created else (0, 1)


def _source_label_for(suggestion: Suggestion) -> str:
    """Return ``"wordpress"`` when the host is a WP content_type, else ``"xenforo"``."""
    return "wordpress" if suggestion.host.content_type.startswith("wp_") else "xenforo"


def _build_ga4_defaults(
    *,
    suggestion: Suggestion,
    algorithm_key: str,
    algorithm_version_date,
    event_schema: str,
    key_fields: dict[str, str],
    field_totals: dict[str, int | float],
) -> dict:
    """Build the ``defaults=`` payload for a GA4 SuggestionTelemetryDaily upsert."""
    sessions = int(field_totals.get("sessions", 0))
    engaged_sessions = int(field_totals.get("engaged_sessions", 0))
    total_engagement = float(field_totals.get("total_engagement_time_seconds", 0.0))
    return {
        "destination": suggestion.destination,
        "host": suggestion.host,
        "algorithm_key": algorithm_key,
        "algorithm_version_date": algorithm_version_date,
        "event_schema": event_schema,
        "source_label": _source_label_for(suggestion),
        "same_silo": _same_silo(suggestion),
        "device_category": key_fields["device_category"],
        "default_channel_group": key_fields["default_channel_group"],
        "source_medium": key_fields["source_medium"],
        "country": key_fields["country"],
        "region": key_fields["region"],
        "impressions": int(field_totals.get("impressions", 0)),
        "clicks": int(field_totals.get("clicks", 0)),
        "destination_views": int(field_totals.get("destination_views", 0)),
        "engaged_sessions": engaged_sessions,
        "conversions": int(field_totals.get("conversions", 0)),
        "sessions": sessions,
        "bounce_sessions": max(sessions - engaged_sessions, 0),
        # Phase 2 engagement signals — safe defaults so old event sets still
        # upsert cleanly.
        "quick_exit_sessions": int(field_totals.get("quick_exit_sessions", 0)),
        "dwell_30s_sessions": int(field_totals.get("dwell_30s_sessions", 0)),
        "dwell_60s_sessions": int(field_totals.get("dwell_60s_sessions", 0)),
        "avg_engagement_time_seconds": (total_engagement / sessions)
        if sessions
        else 0.0,
        "total_engagement_time_seconds": total_engagement,
        "event_count": int(field_totals.get("event_count", 0)),
        "is_attributed": True,
    }


def _upsert_ga4_row(
    *,
    target_date: date,
    suggestion: Suggestion,
    key_fields: dict[str, str],
    field_totals: dict[str, int | float],
    event_schema: str,
) -> tuple[int, int]:
    algorithm_key, algorithm_version_date, algorithm_version_slug = (
        _algorithm_version_parts(suggestion)
    )
    defaults = _build_ga4_defaults(
        suggestion=suggestion,
        algorithm_key=algorithm_key,
        algorithm_version_date=algorithm_version_date,
        event_schema=event_schema,
        key_fields=key_fields,
        field_totals=field_totals,
    )
    _, created = SuggestionTelemetryDaily.objects.update_or_create(
        date=target_date,
        telemetry_source="ga4",
        suggestion=suggestion,
        algorithm_version_slug=algorithm_version_slug,
        device_category=key_fields["device_category"],
        default_channel_group=key_fields["default_channel_group"],
        source_medium=key_fields["source_medium"],
        country=key_fields["country"],
        region=key_fields["region"],
        is_attributed=True,
        defaults=defaults,
    )
    return (1, 0) if created else (0, 1)


def _validate_matomo_sync_settings_or_raise() -> tuple[str, str, str, str]:
    """Validate the Matomo settings; return (base_url, site_id, token_auth, event_schema)."""
    from .views import get_ga4_telemetry_settings, get_matomo_settings, _matomo_token

    settings = get_matomo_settings()
    base_url = str(settings.get("url") or "").strip()
    site_id = str(settings.get("site_id_xenforo") or "").strip()
    if not settings.get("enabled"):
        raise RuntimeError("Matomo collection is disabled in settings.")
    if not settings.get("sync_enabled"):
        raise RuntimeError("Matomo sync is disabled in settings.")
    if not base_url or not site_id:
        raise RuntimeError("Matomo sync needs the URL and XenForo site ID.")
    token_auth = _matomo_token()
    if not token_auth:
        raise RuntimeError("Matomo sync needs the saved token_auth secret.")
    event_schema = str(get_ga4_telemetry_settings().get("event_schema") or "fr016_v1")
    return base_url, site_id, token_auth, event_schema


def _aggregate_matomo_suggestion_totals(parsed_rows) -> dict[str, dict[str, int]]:
    """Roll up parsed Matomo events into per-suggestion field totals.

    Single Python pass over ``parsed_rows`` builds three parallel column lists,
    handed to ``safe_aggregate_grouped_by_outer`` which produces the nested
    ``dict[suggestion_id][field_name] = total`` directly via one sorted
    iteration over the aggregated Polars frame — no flat-dict intermediate.

    Performance (1M synthetic rows, 2026-05-09): ~1.13x faster than the
    legacy defaultdict loop (~530 ms vs ~600 ms). The earlier migration that
    went via ``safe_aggregate_columnar`` + Python reshape was actually
    *slower* than defaultdict (~1030 ms) because it materialised both the
    flat and nested dicts. The win unlocks for any consumer with the
    ``dict[outer][inner] = total`` shape; see
    ``apps.analytics._polars_helpers.safe_aggregate_grouped_by_outer``.
    """
    sids: list[str] = []
    fields: list[str] = []
    counts: list[int] = []
    for suggestion_id, event_name, count in parsed_rows:
        field = MATOMO_EVENT_FIELDS.get(event_name)
        if field is None:
            continue
        sids.append(str(suggestion_id))
        fields.append(field)
        counts.append(int(count))

    return safe_aggregate_grouped_by_outer(
        {"sid": sids, "field": fields, "count": counts},
        outer_col="sid",
        inner_col="field",
        agg_col="count",
        error_step="matomo_aggregate_suggestion_totals",
        job_type="matomo_polars_aggregation",
    )


def _bulk_load_suggestions_map(suggestion_ids: list[str]) -> dict:
    """Pre-fetch all referenced suggestions in ONE query."""
    return {
        str(s.suggestion_id): s
        for s in Suggestion.objects.select_related(
            "destination",
            "destination__scope",
            "host",
            "host__scope",
            "pipeline_run",
        ).filter(suggestion_id__in=suggestion_ids)
    }


def _persist_matomo_day_writes(
    suggestion_totals: dict,
    suggestions_map: dict,
    target_date,
    event_schema: str,
    touched_destination_ids: set,
    counters: dict,
) -> tuple[int, int]:
    """Write all merged rows for one day; return (rows_written, rows_updated)."""
    rows_written = 0
    rows_updated = 0
    for suggestion_id, field_totals in suggestion_totals.items():
        suggestion = suggestions_map.get(suggestion_id)
        if suggestion is None:
            counters["missing_metadata_events"] += int(sum(field_totals.values()))
            continue
        written, updated = _upsert_telemetry_row(
            target_date=target_date,
            suggestion=suggestion,
            field_totals=field_totals,
            event_schema=event_schema,
        )
        touched_destination_ids.add(suggestion.destination_id)
        rows_written += written
        rows_updated += updated
        if field_totals.get("impressions", 0) > 0:
            counters["observed_impression_links"] += 1
        if field_totals.get("clicks", 0) > 0:
            counters["observed_click_links"] += 1
        counters["attributed_destination_sessions"] += int(
            field_totals.get("destination_views", 0),
        )
    return rows_written, rows_updated


def _record_coverage_row(
    *,
    target_date,
    event_schema: str,
    source_label: str,
    counters: dict,
    rows_updated: int,
) -> None:
    """Persist one TelemetryCoverageDaily row. Shared between GA4 + Matomo paths."""
    has_links = (
        counters["observed_impression_links"] or counters["observed_click_links"]
    )
    TelemetryCoverageDaily.objects.update_or_create(
        date=target_date,
        event_schema=event_schema,
        source_label=source_label,
        algorithm_version_slug="",
        defaults={
            "expected_instrumented_links": 0,
            "observed_impression_links": counters["observed_impression_links"],
            "observed_click_links": counters["observed_click_links"],
            "attributed_destination_sessions": counters[
                "attributed_destination_sessions"
            ],
            "unattributed_destination_sessions": 0,
            "duplicate_event_drops": 0,
            "missing_metadata_events": counters["missing_metadata_events"],
            "delayed_rows_rewritten": rows_updated,
            "coverage_state": "healthy" if has_links else "partial",
        },
    )


def _process_matomo_day(
    *,
    base_url: str,
    token_auth: str,
    site_id: str,
    target_date,
    event_schema: str,
    touched_destination_ids: set,
) -> tuple[int, int, int]:
    """Process one day of Matomo sync. Returns (rows_read, rows_written, rows_updated)."""
    counters = {
        "missing_metadata_events": 0,
        "observed_impression_links": 0,
        "observed_click_links": 0,
        "attributed_destination_sessions": 0,
    }
    parsed_rows, source_rows = _fetch_matomo_event_rows(
        base_url=base_url,
        token_auth=token_auth,
        site_id=site_id,
        target_date=target_date,
    )
    suggestion_totals = _aggregate_matomo_suggestion_totals(parsed_rows)
    suggestions_map = _bulk_load_suggestions_map(list(suggestion_totals.keys()))
    rows_written, rows_updated = _persist_matomo_day_writes(
        suggestion_totals,
        suggestions_map,
        target_date,
        event_schema,
        touched_destination_ids,
        counters,
    )
    _record_coverage_row(
        target_date=target_date,
        event_schema=event_schema,
        source_label="matomo",
        counters=counters,
        rows_updated=rows_updated,
    )
    return source_rows, rows_written, rows_updated


def _matomo_traffic_settings_or_raise() -> tuple[str, str, str, str]:
    """Resolve Matomo URL + token + WP/XF site IDs for the general-traffic sync.

    Returns (base_url, token, site_id_wp, site_id_xf). Raises RuntimeError
    if Matomo collection is disabled or required settings are missing.
    """
    from .views import _matomo_token, get_matomo_settings

    settings = get_matomo_settings()
    if not settings.get("enabled"):
        raise RuntimeError("Matomo collection is disabled in settings.")
    base_url = str(settings.get("url") or "").strip()
    site_wp = str(settings.get("site_id_wordpress") or "").strip()
    site_xf = str(settings.get("site_id_xenforo") or "").strip()
    if not base_url:
        raise RuntimeError("Matomo traffic sync needs the Matomo URL.")
    if not site_wp and not site_xf:
        raise RuntimeError(
            "Matomo traffic sync needs at least one of site_id_wordpress / "
            "site_id_xenforo configured."
        )
    token = _matomo_token()
    if not token:
        raise RuntimeError("Matomo traffic sync needs the saved token_auth secret.")
    return base_url, token, site_wp, site_xf


def _flatten_matomo_url_rows(
    rows: list[dict[str, Any]], parent_path: str = ""
) -> list[tuple[str, dict[str, Any]]]:
    """Walk Matomo's nested ``Actions.getPageUrls`` tree and emit (url, row).

    Matomo returns a forest where each node has ``label`` and may have a
    ``subtable`` of children. Internal nodes typically don't carry stats;
    only leaves do. We follow the path-segment convention by joining
    parent labels with ``/`` so the final URL is reconstructable.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip("/ ").strip()
        path = parent_path.rstrip("/") + "/" + label if parent_path else "/" + label
        children = (
            row.get("subtable") or row.get("subtables") or row.get("subRows") or []
        )
        if isinstance(children, list) and children:
            out.extend(_flatten_matomo_url_rows(children, parent_path=path))
        else:
            out.append((path, row))
    return out


def _persist_matomo_traffic_day(
    *,
    site_id: str,
    target_date: date,
    site_main_url: str,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Upsert one day's worth of per-URL Matomo traffic. Returns (new, updated).

    ``site_main_url`` is the canonical web address of the tracked site
    (e.g. ``https://misc.goldmidi.com`` or ``https://goldmidi.com/community``)
    pulled from Matomo's ``SitesManager.getSiteFromId`` — NOT the Matomo
    instance host. Path segments returned by ``Actions.getPageUrls`` get
    appended to this so the stored URL points at the real page.
    """
    from .models import MatomoDailyTraffic

    # We need the bare scheme+host (e.g. ``https://goldmidi.com``), NOT the
    # main_url which can include a sub-path like ``/community``. Matomo's
    # Actions.getPageUrls already returns paths anchored at the host root
    # (e.g. ``/community/threads/...``), so prepending main_url verbatim
    # would double the sub-path. Strip everything after the host.
    from urllib.parse import urlparse

    parsed = urlparse(site_main_url or "")
    site_origin = (
        f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    )
    new_rows = 0
    updated_rows = 0
    for path, row in _flatten_matomo_url_rows(rows):
        nb_visits = int(row.get("nb_visits") or 0)
        nb_hits = int(row.get("nb_hits") or 0)
        if nb_visits == 0 and nb_hits == 0:
            # Skip noise rows (Matomo sometimes returns zero-count entries).
            continue
        # Matomo returns site-relative paths anchored at the host root;
        # prepend the bare scheme+host so the final URL points at the real
        # page. The UNIQUE is on (site_id, date, page_url).
        page_url = path if path.startswith("http") else (site_origin + path)[:2000]
        defaults = {
            "label": str(row.get("label") or "")[:500],
            "nb_visits": nb_visits,
            "nb_hits": nb_hits,
            "nb_uniq_visitors": int(row.get("nb_uniq_visitors") or 0),
            "bounce_count": int(row.get("bounce_count") or 0),
            "sum_time_spent": int(row.get("sum_time_spent") or 0),
        }
        _, created = MatomoDailyTraffic.objects.update_or_create(
            site_id=site_id,
            date=target_date,
            page_url=page_url,
            defaults=defaults,
        )
        if created:
            new_rows += 1
        else:
            updated_rows += 1
    return new_rows, updated_rows


def _fetch_matomo_pageurls_day(
    *,
    base_url: str,
    token: str,
    site_id: str,
    target_date: date,
) -> list[dict[str, Any]]:
    """Pull a flattened ``Actions.getPageUrls`` list for one site/day.

    ``flat=1`` tells Matomo to flatten the tree so we don't have to walk
    subtables ourselves; ``filter_limit=-1`` removes the default 100-row cap.
    """
    payload = _matomo_api_get(
        base_url=base_url,
        token_auth=token,
        method="Actions.getPageUrls",
        params={
            "idSite": site_id,
            "period": "day",
            "date": target_date.isoformat(),
            "flat": 1,
            "filter_limit": -1,
            "segment": MATOMO_EXCLUDED_SEGMENT,
        },
    )
    return payload if isinstance(payload, list) else []


def _resolve_matomo_site_main_url(
    *,
    base_url: str,
    token: str,
    site_id: str,
) -> str:
    """Look up the tracked-site URL from Matomo's SitesManager API.

    Returns the ``main_url`` field (e.g. ``https://misc.goldmidi.com``).
    On any failure we return an empty string and let the caller fall back
    to a path-only URL — the row still upserts, just without a host prefix.
    """
    try:
        payload = _matomo_api_get(
            base_url=base_url,
            token_auth=token,
            method="SitesManager.getSiteFromId",
            params={"idSite": site_id},
        )
    except Exception as exc:  # noqa: BLE001  # noqa: forbidden-pattern silent-except  # justification: optional metadata lookup; if SitesManager isn't accessible to this token we still want the per-URL traffic to import (with a path-only URL), so we trade a noisy failure for a degraded but functional path.
        logger = __import__("logging").getLogger(__name__)
        logger.warning("matomo: getSiteFromId(%s) failed: %s", site_id, exc)
        return ""
    if isinstance(payload, dict):
        return str(payload.get("main_url") or "").strip()
    return ""


def run_matomo_traffic_sync(sync_run: AnalyticsSyncRun) -> dict[str, int]:
    """Pull per-URL daily traffic from Matomo into ``MatomoDailyTraffic``.

    Distinct from ``run_matomo_sync`` which is FR-016 attribution-only:
    this one mirrors GSC's daily-page totals and is what makes "Matomo
    data is flowing into the Linker DB" actually true for general site
    traffic — independent of whether any Linker suggestions exist yet.
    """
    base_url, token, site_wp, site_xf = _matomo_traffic_settings_or_raise()
    site_ids = [s for s in (site_wp, site_xf) if s]
    # Look up each site's canonical URL once up-front so the loop below
    # doesn't make N redundant SitesManager calls.
    site_main_url_by_id: dict[str, str] = {
        sid: _resolve_matomo_site_main_url(
            base_url=base_url,
            token=token,
            site_id=sid,
        )
        for sid in site_ids
    }
    rows_read = 0
    rows_written = 0
    rows_updated = 0
    for offset in range(max(sync_run.lookback_days, 1)):
        target_date = timezone.now().date() - timedelta(days=offset)
        for site_id in site_ids:
            rows = _fetch_matomo_pageurls_day(
                base_url=base_url,
                token=token,
                site_id=site_id,
                target_date=target_date,
            )
            rows_read += len(rows)
            new_rows, updated = _persist_matomo_traffic_day(
                site_id=site_id,
                target_date=target_date,
                site_main_url=site_main_url_by_id.get(site_id, ""),
                rows=rows,
            )
            rows_written += new_rows
            rows_updated += updated
    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_updated": rows_updated,
    }


def run_matomo_sync(sync_run: AnalyticsSyncRun) -> dict[str, int]:
    base_url, site_id, token_auth, event_schema = (
        _validate_matomo_sync_settings_or_raise()
    )
    rows_read = 0
    rows_written = 0
    rows_updated = 0
    touched_destination_ids: set[int] = set()
    for offset in range(max(sync_run.lookback_days, 1)):
        target_date = timezone.now().date() - timedelta(days=offset)
        day_read, day_written, day_updated = _process_matomo_day(
            base_url=base_url,
            token_auth=token_auth,
            site_id=site_id,
            target_date=target_date,
            event_schema=event_schema,
            touched_destination_ids=touched_destination_ids,
        )
        rows_read += day_read
        rows_written += day_written
        rows_updated += day_updated
    _refresh_content_value_scores(destination_ids=touched_destination_ids)
    _refresh_engagement_quality_scores(destination_ids=touched_destination_ids)
    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_updated": rows_updated,
    }


def _build_ga4_service_or_raise(settings: dict):
    """Build a GA4 Data API service via OAuth (preferred) or service-account creds.

    Centralises the OAuth-vs-service-account selection so ``run_ga4_sync``
    stays focused on the per-day fetch loop. Raises RuntimeError with an
    operator-actionable message if neither credential set is complete.
    """
    from .views import (
        _google_oauth_client_secret,
        _google_oauth_refresh_token,
        _read_setting,
    )

    property_id = str(settings.get("property_id") or "").strip()
    refresh_token = settings.get("oauth_connected") and _google_oauth_refresh_token()
    client_id = settings.get("google_oauth_client_id")
    client_secret = _google_oauth_client_secret()

    if refresh_token and client_id and client_secret:
        return build_ga4_data_service(
            property_id=property_id,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
    project_id = str(settings.get("read_project_id") or "").strip()
    client_email = str(settings.get("read_client_email") or "").strip()
    private_key = _read_setting("analytics.ga4_read_private_key", "") or ""
    if not property_id or not project_id or not client_email or not private_key:
        raise RuntimeError(
            "GA4 sync needs the property ID plus saved GA4 read-access "
            "credentials on the settings page.",
        )
    return build_ga4_data_service(
        property_id=property_id,
        project_id=project_id,
        client_email=client_email,
        private_key=private_key,
    )


def _new_ga4_merged_rows() -> dict:
    """Default-dict factory for the per-key field-totals map."""
    return defaultdict(
        lambda: {
            "impressions": 0,
            "clicks": 0,
            "destination_views": 0,
            "engaged_sessions": 0,
            "conversions": 0,
            "sessions": 0,
            "event_count": 0,
            "total_engagement_time_seconds": 0.0,
            # Phase 2 engagement signals.
            "quick_exit_sessions": 0,
            "dwell_30s_sessions": 0,
            "dwell_60s_sessions": 0,
        },
    )


def _ga4_row_key(parsed: dict) -> tuple:
    """Build the 6-tuple key used by ``merged_rows``."""
    return (
        parsed["suggestion_id"],
        parsed["device_category"],
        parsed["default_channel_group"],
        parsed["source_medium"],
        parsed["country"],
        parsed["region"],
    )


def _append_ga4_row_to_columns(
    row: dict[str, Any],
    *,
    dim_names: list[str],
    geo_granularity: str,
    field_name: str,
    cols: dict[str, list[Any]],
) -> None:
    """Append one GA4 API row to the parallel column lists — twice (per-field + event_count).

    Skips blocked-country rows. Mutates ``cols`` in place. Building columns
    directly here (rather than constructing a dict per row first) avoids the
    per-row dict-construction cost that dominates the wall-clock of the
    legacy ``safe_aggregate`` dict-of-rows path.
    """
    parsed = _ga4_dimensions_from_row(
        row=row, dimension_names=dim_names, geo_granularity=geo_granularity
    )
    if is_blocked_country(parsed["country"]):
        return
    count = _ga4_metric_int(row, 0)
    sid = parsed["suggestion_id"]
    device = parsed["device_category"]
    channel = parsed["default_channel_group"]
    source = parsed["source_medium"]
    country = parsed["country"]
    region = parsed["region"]
    for fname in (field_name, "event_count"):
        cols["sid"].append(sid)
        cols["device"].append(device)
        cols["channel"].append(channel)
        cols["source"].append(source)
        cols["country"].append(country)
        cols["region"].append(region)
        cols["field_name"].append(fname)
        cols["count"].append(count)


def _merge_ga4_aggregate_into_rows(
    flat: dict[tuple, int], merged_rows: dict
) -> None:
    """Apply Polars-aggregated totals back into the per-key merged_rows dict."""
    for combo, total in flat.items():
        sid, device, channel, source, country, region, field_name = combo
        key = (sid, device, channel, source, country, region)
        merged_rows[key][field_name] = int(merged_rows[key][field_name]) + int(total)


def _accumulate_ga4_event_rows(
    *,
    service,
    property_id: str,
    target_date,
    geo_granularity: str,
    merged_rows: dict,
) -> int:
    """Fetch + merge per-event GA4 rows; return total rows_read across event names.

    Builds parallel column lists in one pass over all 8 event-name responses,
    then runs the Polars groupby on already-columnar input. Skipping the
    intermediate ``list[dict]`` form saves ~2x of the per-row Python work
    that dominated the older ``safe_aggregate`` path.
    """
    rows_read = 0
    dim_names = _ga4_dimension_names(geo_granularity=geo_granularity)
    cols: dict[str, list[Any]] = {
        "sid": [], "device": [], "channel": [], "source": [],
        "country": [], "region": [], "field_name": [], "count": [],
    }
    for event_name, field_name in GA4_EVENT_FIELDS.items():
        rows = _fetch_ga4_rows(
            service=service,
            property_id=property_id,
            target_date=target_date,
            geo_granularity=geo_granularity,
            event_name=event_name,
            metrics=["eventCount"],
        )
        rows_read += len(rows)
        for row in rows:
            _append_ga4_row_to_columns(
                row,
                dim_names=dim_names,
                geo_granularity=geo_granularity,
                field_name=field_name,
                cols=cols,
            )

    flat = safe_aggregate_columnar(
        cols,
        group_cols=["sid", "device", "channel", "source", "country", "region", "field_name"],
        agg_col="count",
        error_step="ga4_aggregate_event_rows",
        job_type="ga4_polars_aggregation",
    )
    _merge_ga4_aggregate_into_rows(flat, merged_rows)
    return rows_read


def _accumulate_ga4_session_rows(
    *,
    service,
    property_id: str,
    target_date,
    geo_granularity: str,
    merged_rows: dict,
) -> int:
    """Fetch + merge GA4 destination_view session rows; return rows_read."""
    session_rows = _fetch_ga4_rows(
        service=service,
        property_id=property_id,
        target_date=target_date,
        geo_granularity=geo_granularity,
        event_name="suggestion_destination_view",
        metrics=[
            "eventCount",
            "sessions",
            "engagedSessions",
            "userEngagementDuration",
        ],
    )
    dim_names = _ga4_dimension_names(geo_granularity=geo_granularity)
    for row in session_rows:
        parsed = _ga4_dimensions_from_row(
            row=row,
            dimension_names=dim_names,
            geo_granularity=geo_granularity,
        )
        if is_blocked_country(parsed["country"]):
            continue
        key = _ga4_row_key(parsed)
        merged_rows[key]["destination_views"] = _ga4_metric_int(row, 0)
        merged_rows[key]["sessions"] = _ga4_metric_int(row, 1)
        merged_rows[key]["engaged_sessions"] = max(
            int(merged_rows[key]["engaged_sessions"]),
            _ga4_metric_int(row, 2),
        )
        merged_rows[key]["total_engagement_time_seconds"] = _ga4_metric_float(row, 3)
    return len(session_rows)


def _bulk_load_ga4_suggestions(merged_rows: dict) -> dict:
    """Pre-fetch every Suggestion referenced in merged_rows in ONE query."""
    suggestion_ids = [key[0] for key in merged_rows if key[0]]
    return {
        str(suggestion.suggestion_id): suggestion
        for suggestion in Suggestion.objects.select_related(
            "destination",
            "destination__scope",
            "host",
            "host__scope",
            "pipeline_run",
        ).filter(suggestion_id__in=suggestion_ids)
    }


def _persist_ga4_day_writes(
    merged_rows: dict,
    suggestions: dict,
    target_date,
    event_schema: str,
    touched_destination_ids: set,
    counters: dict,
) -> tuple[int, int]:
    """Write all merged rows for one day; return (rows_written, rows_updated)."""
    rows_written = 0
    rows_updated = 0
    for key, field_totals in merged_rows.items():
        (
            suggestion_id,
            device_category,
            default_channel_group,
            source_medium,
            country,
            region,
        ) = key
        event_count = int(field_totals.get("event_count", 0))
        if not suggestion_id:
            counters["missing_metadata_events"] += event_count
            continue
        suggestion = suggestions.get(suggestion_id)
        if suggestion is None:
            counters["missing_metadata_events"] += event_count
            continue
        written, updated = _upsert_ga4_row(
            target_date=target_date,
            suggestion=suggestion,
            key_fields={
                "device_category": device_category,
                "default_channel_group": default_channel_group,
                "source_medium": source_medium,
                "country": country,
                "region": region,
            },
            field_totals=field_totals,
            event_schema=event_schema,
        )
        touched_destination_ids.add(suggestion.destination_id)
        rows_written += written
        rows_updated += updated
        if int(field_totals.get("impressions", 0)) > 0:
            counters["observed_impression_links"] += 1
        if int(field_totals.get("clicks", 0)) > 0:
            counters["observed_click_links"] += 1
        counters["attributed_destination_sessions"] += int(
            field_totals.get("destination_views", 0),
        )
    return rows_written, rows_updated


def _process_ga4_day(
    *,
    service,
    property_id: str,
    target_date,
    geo_granularity: str,
    event_schema: str,
    touched_destination_ids: set,
) -> tuple[int, int, int]:
    """Process one day of GA4 sync. Returns (rows_read, rows_written, rows_updated)."""
    merged_rows = _new_ga4_merged_rows()
    counters = {
        "missing_metadata_events": 0,
        "observed_impression_links": 0,
        "observed_click_links": 0,
        "attributed_destination_sessions": 0,
    }
    rows_read = _accumulate_ga4_event_rows(
        service=service,
        property_id=property_id,
        target_date=target_date,
        geo_granularity=geo_granularity,
        merged_rows=merged_rows,
    )
    rows_read += _accumulate_ga4_session_rows(
        service=service,
        property_id=property_id,
        target_date=target_date,
        geo_granularity=geo_granularity,
        merged_rows=merged_rows,
    )
    suggestions = _bulk_load_ga4_suggestions(merged_rows)
    rows_written, rows_updated = _persist_ga4_day_writes(
        merged_rows,
        suggestions,
        target_date,
        event_schema,
        touched_destination_ids,
        counters,
    )
    _record_coverage_row(
        target_date=target_date,
        event_schema=event_schema,
        source_label="ga4",
        counters=counters,
        rows_updated=rows_updated,
    )
    return rows_read, rows_written, rows_updated


def run_ga4_sync(sync_run: AnalyticsSyncRun) -> dict[str, int]:
    from .views import get_ga4_telemetry_settings

    settings = get_ga4_telemetry_settings()
    service = _build_ga4_service_or_raise(settings)
    property_id = str(settings.get("property_id") or "").strip()
    geo_granularity = str(settings.get("geo_granularity") or "country").strip()
    event_schema = str(settings.get("event_schema") or "fr016_v1")
    touched_destination_ids: set[int] = set()
    rows_read = 0
    rows_written = 0
    rows_updated = 0
    for offset in range(max(sync_run.lookback_days, 1)):
        target_date = timezone.now().date() - timedelta(days=offset)
        day_read, day_written, day_updated = _process_ga4_day(
            service=service,
            property_id=property_id,
            target_date=target_date,
            geo_granularity=geo_granularity,
            event_schema=event_schema,
            touched_destination_ids=touched_destination_ids,
        )
        rows_read += day_read
        rows_written += day_written
        rows_updated += day_updated
    _refresh_content_value_scores(destination_ids=touched_destination_ids)
    _refresh_engagement_quality_scores(destination_ids=touched_destination_ids)
    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_updated": rows_updated,
    }


_GSC_LAG_DAYS = 3


def _build_gsc_service_or_raise(settings: dict):
    """Build a GSC API service via OAuth (preferred) or service-account creds."""
    from .views import (
        _google_oauth_client_id,
        _google_oauth_client_secret,
        _google_oauth_refresh_token,
        _gsc_private_key,
    )

    refresh_token = settings.get("oauth_connected") and _google_oauth_refresh_token()
    client_id = _google_oauth_client_id()
    client_secret = _google_oauth_client_secret()
    if refresh_token and client_id and client_secret:
        return build_gsc_service(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
    property_url = settings.get("property_url")
    client_email = settings.get("client_email")
    private_key = _gsc_private_key()
    if not property_url or not client_email or not private_key:
        raise RuntimeError(
            "GSC sync needs property_url, client_email, and private_key.",
        )
    return build_gsc_service(client_email=client_email, private_key=private_key)


# Subdomains under sc-domain:goldmidi.com that we deliberately ignore.
# The user only wants analytics for goldmidi.com (root + /community/) and
# misc.goldmidi.com — every other subdomain captured by the umbrella
# domain-property is dropped here so it never reaches the database.
_GSC_DEFAULT_EXCLUDED_HOSTS: tuple[str, ...] = (
    "business.goldmidi.com",
    "nyuuz.goldmidi.com",
    "tgmnyuuz.blogspot.com",
)


def _gsc_excluded_hosts() -> tuple[str, ...]:
    """Return the comma-separated AppSetting list, or the hard-coded default.

    Operators can override the defaults via the
    ``analytics.gsc_excluded_hosts`` setting (comma-separated hostnames). An
    empty value disables exclusion entirely.
    """
    from apps.core.models import AppSetting

    raw = AppSetting.get_str("analytics.gsc_excluded_hosts", "").strip()
    if not raw:
        return _GSC_DEFAULT_EXCLUDED_HOSTS
    return tuple(h.strip().lower() for h in raw.split(",") if h.strip())


def _gsc_row_is_excluded(row: dict[str, Any], excluded_hosts: tuple[str, ...]) -> bool:
    """True when the row's page URL is on an excluded subdomain.

    GSC rows look like ``{"keys": [date, page_url, ...], ...}``. We pull the
    URL out of position 1 and compare its hostname (case-insensitive) against
    the exclusion list.
    """
    keys = row.get("keys") or []
    if len(keys) < 2:
        return False
    page_url = str(keys[1] or "").lower()
    # Match anywhere in the URL (handles both http/https + path noise).
    return any(host in page_url for host in excluded_hosts)


def _fetch_gsc_dimensions_pair(
    *,
    service,
    property_url: str,
    start_date,
    end_date,
) -> tuple[list, list]:
    """Fetch the (page-totals, query-detail) row pairs from GSC, with the
    subdomain exclusion list applied so we never persist data we don't want.
    """
    excluded_countries = list(BLOCKED_COUNTRY_CODES_ALPHA3)
    excluded_hosts = _gsc_excluded_hosts()
    page_rows = fetch_gsc_performance_data(
        service=service,
        property_url=property_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=["date", "page"],
        excluded_country_codes=excluded_countries,
    )
    query_rows = fetch_gsc_performance_data(
        service=service,
        property_url=property_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=["date", "page", "query"],
        excluded_country_codes=excluded_countries,
    )
    if excluded_hosts:
        page_rows = [
            r for r in page_rows if not _gsc_row_is_excluded(r, excluded_hosts)
        ]
        query_rows = [
            r for r in query_rows if not _gsc_row_is_excluded(r, excluded_hosts)
        ]
    return page_rows, query_rows


def _build_gsc_content_url_map(
    page_rows: list, query_rows: list
) -> dict[str, ContentItem]:
    """Bulk-fetch ContentItems for every page URL in either row set in ONE query."""
    page_urls_in_batch = list(
        {
            row["keys"][1]
            for row in page_rows + query_rows
            if len(row.get("keys", [])) >= 2
        }
    )
    return {
        item.url: item
        for item in ContentItem.objects.filter(url__in=page_urls_in_batch)
    }


def _persist_gsc_page_rows(
    page_rows: list,
    content_map: dict,
    property_url: str,
    page_totals_by_item_date: dict,
    touched_destination_ids: set,
) -> tuple[int, int]:
    """Write GSCDailyPerformance for every page row + cache item totals.

    Returns (rows_written, rows_updated). Bug-safe: no division-by-zero risk.
    """
    from .models import GSCDailyPerformance

    rows_written = 0
    rows_updated = 0
    for row in page_rows:
        dt_str = row["keys"][0]
        page_url = row["keys"][1]
        impressions = int(row.get("impressions", 0))
        clicks = int(row.get("clicks", 0))
        ctr = float(row.get("ctr", 0.0))
        avg_pos = float(row.get("position", 0.0))
        _, created = GSCDailyPerformance.objects.update_or_create(
            page_url=page_url,
            date=dt_str,
            property_url=property_url,
            defaults={
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "avg_position": avg_pos,
            },
        )
        if created:
            rows_written += 1
        else:
            rows_updated += 1
        item = content_map.get(page_url)
        if item:
            page_totals_by_item_date[(item.pk, dt_str)] = {
                "item": item,
                "impressions": impressions,
                "clicks": clicks,
                "ctr": ctr,
                "average_position": avg_pos,
            }
            touched_destination_ids.add(item.pk)
    return rows_written, rows_updated


def _persist_gsc_query_rows(
    query_rows: list,
    content_map: dict,
    item_dates_with_query_rows: set,
) -> None:
    """Write per-query SearchMetric rows + record (item, date) pairs that have queries."""
    for row in query_rows:
        if len(row.get("keys", [])) < 3:
            continue
        dt_str = row["keys"][0]
        page_url = row["keys"][1]
        query_text = str(row["keys"][2] or "").strip()
        item = content_map.get(page_url)
        if item is None or not query_text:
            continue
        item_dates_with_query_rows.add((item.pk, dt_str))
        SearchMetric.objects.update_or_create(
            content_item=item,
            date=dt_str,
            source="gsc",
            query=query_text,
            defaults={
                "impressions": int(row.get("impressions", 0)),
                "clicks": int(row.get("clicks", 0)),
                "ctr": float(row.get("ctr", 0.0)),
                "average_position": float(row.get("position", 0.0)),
            },
        )


def _persist_gsc_page_total_search_metrics(
    page_totals_by_item_date: dict,
    item_dates_with_query_rows: set,
) -> None:
    """Per (item, date) page total: drop any zero-query row + upsert the totals row.

    The drop-empty-query-row path runs when query rows already covered the
    same (item, date) — we don't want both a "" total AND query-detail rows
    confusing the breakdown.
    """
    for (item_pk, dt_str), totals in page_totals_by_item_date.items():
        item = totals["item"]
        if (item_pk, dt_str) in item_dates_with_query_rows:
            SearchMetric.objects.filter(
                content_item=item,
                date=dt_str,
                source="gsc",
                query="",
            ).delete()
            continue
        SearchMetric.objects.update_or_create(
            content_item=item,
            date=dt_str,
            source="gsc",
            query="",
            defaults={
                "impressions": int(totals["impressions"]),
                "clicks": int(totals["clicks"]),
                "ctr": float(totals["ctr"]),
                "average_position": float(totals["average_position"]),
            },
        )


def run_gsc_sync(sync_run: AnalyticsSyncRun) -> dict[str, int]:
    """Fetch GSC search-performance metrics + store them as raw daily logs.

    Powered by the GSCDailyPerformance + SearchMetric tables that feed the
    attribution engine. Cold-start safe: returns an error dict (not an
    exception) if sync is disabled.
    """
    from .views import get_gsc_settings

    settings = get_gsc_settings()
    if not settings.get("sync_enabled"):
        return {
            "rows_read": 0,
            "rows_written": 0,
            "rows_updated": 0,
            "error": "GSC sync is disabled.",
        }
    service = _build_gsc_service_or_raise(settings)
    property_url = settings.get("property_url")
    # GSC has a ~2-3 day processing lag; look back from 3 days ago.
    end_date = timezone.now().date() - timedelta(days=_GSC_LAG_DAYS)
    start_date = end_date - timedelta(days=sync_run.lookback_days)
    page_rows, query_rows = _fetch_gsc_dimensions_pair(
        service=service,
        property_url=property_url,
        start_date=start_date,
        end_date=end_date,
    )
    rows_read = len(page_rows) + len(query_rows)
    content_map = _build_gsc_content_url_map(page_rows, query_rows)
    page_totals_by_item_date: dict[tuple[int, str], dict] = {}
    item_dates_with_query_rows: set[tuple[int, str]] = set()
    touched_destination_ids: set[int] = set()
    rows_written, rows_updated = _persist_gsc_page_rows(
        page_rows,
        content_map,
        property_url,
        page_totals_by_item_date,
        touched_destination_ids,
    )
    _persist_gsc_query_rows(query_rows, content_map, item_dates_with_query_rows)
    _persist_gsc_page_total_search_metrics(
        page_totals_by_item_date,
        item_dates_with_query_rows,
    )
    _refresh_content_value_scores(destination_ids=touched_destination_ids)
    _refresh_engagement_quality_scores(destination_ids=touched_destination_ids)
    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_updated": rows_updated,
    }


def compute_content_value_raw(  # noqa: forbidden-pattern too-many-args  # justification: keyword-only telemetry signature is the public API mirroring compute_content_value_breakdown; collapsing to a kwargs dict would break call-site type checking.
    *,
    gsc_clicks: int,
    gsc_ctr: float,
    gsc_impressions: int,
    destination_views: int,
    engaged_sessions: int,
    conversions: int,
    telemetry_clicks: int,
    quick_exit_sessions: int = 0,
    dwell_30s_sessions: int = 0,
    dwell_60s_sessions: int = 0,
) -> float | None:
    """Compute the raw (pre-normalisation) content-value score for one item.

    Returns ``None`` when every input is zero (the neutral-fallback branch
    that keeps the field at its 0.5 default for items with no activity).

    Phase 3a/3c extension: three terms derived from Phase 2 engagement events.

    # Source: Kim, Hassan, White & Zitouni (2014) "Modeling dwell time to
    # predict click-level satisfaction" (WSDM). Dwell time is modelled as a
    # satisfaction gradient, not a single threshold: the 30-second mark is
    # a partial-confidence positive signal and the 60-second mark is the
    # strong positive. Quick-exit is the strong-negative counterpart.
    # Coefficients: dwell-60s and quick-exit at ``0.05`` (Phase 3a, paired
    # with conversion_rate and click_rate tiers); dwell-30s at ``0.025``
    # (Phase 3c, half-weight — conservative starting value per BLC §1.3,
    # tunable later by FR-018 auto-tuner).
    # Neutral fallback: if all three new counts are zero (no telemetry
    # wired yet or no Phase 2 events fired) all three terms add to 0,
    # leaving the pre-Phase 3a formula intact.

    Body delegates to the shared spec-table helpers used by the breakdown
    counterpart so the formula stays in exactly one place.
    """
    if not any(
        [
            gsc_clicks,
            gsc_impressions,
            destination_views,
            engaged_sessions,
            conversions,
            telemetry_clicks,
            quick_exit_sessions,
            dwell_30s_sessions,
            dwell_60s_sessions,
        ]
    ):
        return None
    inputs = _build_content_value_term_inputs(
        gsc_clicks=gsc_clicks,
        gsc_ctr=gsc_ctr,
        destination_views=destination_views,
        engaged_sessions=engaged_sessions,
        conversions=conversions,
        telemetry_clicks=telemetry_clicks,
        quick_exit_sessions=quick_exit_sessions,
        dwell_30s_sessions=dwell_30s_sessions,
        dwell_60s_sessions=dwell_60s_sessions,
    )
    return sum(
        _term_contribution(inputs[name], weight, sign, multiplier, kind)
        for name, weight, sign, multiplier, kind in _CONTENT_VALUE_TERM_SPEC
    )


# Per-term spec for the content_value breakdown. Each tuple:
# (name, weight, sign, multiplier, kind)
#   kind ∈ {"log1p", "raw_pct", "rate"} — selects how `value` maps into `contribution`.
# Mirrors Kim et al. WSDM 2014 dwell-gradient + quick-exit weights one-for-one.
_CONTENT_VALUE_TERM_SPEC: tuple[tuple[str, float, str, float, str], ...] = (
    ("gsc_clicks", 0.40, "+", 0.0, "log1p"),
    ("gsc_ctr", 0.20, "+", 100.0, "raw_pct"),
    ("destination_views", 0.20, "+", 0.0, "log1p"),
    ("engagement_rate", 0.10, "+", 10.0, "rate"),
    ("conversion_rate", 0.05, "+", 10.0, "rate"),
    ("click_rate", 0.05, "+", 10.0, "rate"),
    ("dwell_30s_rate", 0.025, "+", 10.0, "rate"),
    ("dwell_60s_rate", 0.05, "+", 10.0, "rate"),
    ("quick_exit_rate", 0.05, "-", 10.0, "rate"),
)


def _build_content_value_term_inputs(  # noqa: forbidden-pattern too-many-args  # justification: kwargs mirror compute_content_value_raw 1:1; collapsing breaks call-site type checking.
    *,
    gsc_clicks: int,
    gsc_ctr: float,
    destination_views: int,
    engaged_sessions: int,
    conversions: int,
    telemetry_clicks: int,
    quick_exit_sessions: int,
    dwell_30s_sessions: int,
    dwell_60s_sessions: int,
) -> dict[str, float]:
    """Compute the per-term ``value`` inputs (raw counts + per-view rates)."""
    safe_views = max(destination_views, 1)
    return {
        "gsc_clicks": float(gsc_clicks),
        "gsc_ctr": float(gsc_ctr),
        "destination_views": float(destination_views),
        "engagement_rate": engaged_sessions / safe_views,
        "conversion_rate": conversions / safe_views,
        "click_rate": telemetry_clicks / safe_views,
        "dwell_30s_rate": dwell_30s_sessions / safe_views,
        "dwell_60s_rate": dwell_60s_sessions / safe_views,
        "quick_exit_rate": quick_exit_sessions / safe_views,
    }


def _term_contribution(
    value: float, weight: float, sign: str, multiplier: float, kind: str
) -> float:
    """Map a (value, weight, sign, multiplier, kind) spec row to a signed contribution."""
    if kind == "log1p":
        magnitude = weight * math.log1p(value)
    elif kind == "raw_pct":
        magnitude = weight * value * multiplier
    elif kind == "rate":
        magnitude = weight * value * multiplier
    else:  # pragma: no cover — guarded by the constant table
        raise ValueError(f"Unknown content-value term kind: {kind}")
    return -magnitude if sign == "-" else magnitude


def compute_content_value_breakdown(  # noqa: forbidden-pattern too-many-args  # justification: kwargs mirror compute_content_value_raw 1:1 so callers reuse the same row dict.
    *,
    gsc_clicks: int,
    gsc_ctr: float,
    gsc_impressions: int,
    destination_views: int,
    engaged_sessions: int,
    conversions: int,
    telemetry_clicks: int,
    quick_exit_sessions: int = 0,
    dwell_30s_sessions: int = 0,
    dwell_60s_sessions: int = 0,
) -> dict:
    """Tier 2 slice 5 — per-term decomposition of ``compute_content_value_raw``.

    Mirrors the additive Kim-et-al. WSDM 2014 formula one-for-one. Returns
    ``{"raw": float, "terms": [...], "has_data": bool}``. Empty terms +
    has_data=False when no telemetry is available so the detail dialog
    can render "no data yet" instead of a zero-filled table.
    """
    has_data = any(
        [
            gsc_clicks,
            gsc_impressions,
            destination_views,
            engaged_sessions,
            conversions,
            telemetry_clicks,
            quick_exit_sessions,
            dwell_30s_sessions,
            dwell_60s_sessions,
        ]
    )
    if not has_data:
        return {"raw": 0.0, "terms": [], "has_data": False}
    inputs = _build_content_value_term_inputs(
        gsc_clicks=gsc_clicks,
        gsc_ctr=gsc_ctr,
        destination_views=destination_views,
        engaged_sessions=engaged_sessions,
        conversions=conversions,
        telemetry_clicks=telemetry_clicks,
        quick_exit_sessions=quick_exit_sessions,
        dwell_30s_sessions=dwell_30s_sessions,
        dwell_60s_sessions=dwell_60s_sessions,
    )
    terms = []
    for name, weight, sign, multiplier, kind in _CONTENT_VALUE_TERM_SPEC:
        value = inputs[name]
        terms.append(
            {
                "name": name,
                "value": value,
                "weight": weight,
                "sign": sign,
                "contribution": _term_contribution(
                    value, weight, sign, multiplier, kind
                ),
            }
        )
    raw = sum(term["contribution"] for term in terms)
    return {"raw": raw, "terms": terms, "has_data": True}


_CONTENT_VALUE_LOOKBACK_DEFAULT_DAYS = 28
_CONTENT_VALUE_NEUTRAL_SCORE = 0.5
_CONTENT_VALUE_NORMALIZED_FLOOR = 0.30
_CONTENT_VALUE_NORMALIZED_RANGE = 0.60
_CONTENT_VALUE_SINGLE_ITEM_SCORE = 0.75


def _aggregate_telemetry_for_score(item_ids: list[int], window_start) -> dict:
    """Bulk-sum telemetry per destination + Phase 3a/3c engagement signals."""
    telemetry_rows = (
        SuggestionTelemetryDaily.objects.filter(
            destination_id__in=item_ids,
            date__gte=window_start,
        )
        .exclude(country__in=BLOCKED_TELEMETRY_COUNTRY_VALUES)
        .values("destination_id")
        .annotate(
            clicks=Sum("clicks"),
            destination_views=Sum("destination_views"),
            engaged_sessions=Sum("engaged_sessions"),
            conversions=Sum("conversions"),
            # Phase 3a/3c — dwell-30s/60s credits + quick-exit penalty.
            quick_exit_sessions=Sum("quick_exit_sessions"),
            dwell_30s_sessions=Sum("dwell_30s_sessions"),
            dwell_60s_sessions=Sum("dwell_60s_sessions"),
        )
    )
    return {int(row["destination_id"]): row for row in telemetry_rows}


def _aggregate_gsc_for_score(item_ids: list[int], window_start) -> dict:
    """Bulk-sum GSC clicks/impressions + avg CTR per content item."""
    gsc_rows = (
        SearchMetric.objects.filter(
            content_item_id__in=item_ids,
            source="gsc",
            date__gte=window_start,
        )
        .exclude(query="")
        .values("content_item_id")
        .annotate(
            clicks=Sum("clicks"),
            impressions=Sum("impressions"),
            ctr=Avg("ctr"),
        )
    )
    return {int(row["content_item_id"]): row for row in gsc_rows}


def _build_content_value_kwargs(telemetry: dict, gsc: dict) -> dict:
    """Convert raw aggregated rows into compute_content_value_raw kwargs."""
    return {
        "gsc_clicks": int(gsc.get("clicks") or 0),
        "gsc_ctr": float(gsc.get("ctr") or 0.0),
        "gsc_impressions": int(gsc.get("impressions") or 0),
        "destination_views": int(telemetry.get("destination_views") or 0),
        "engaged_sessions": int(telemetry.get("engaged_sessions") or 0),
        "conversions": int(telemetry.get("conversions") or 0),
        "telemetry_clicks": int(telemetry.get("clicks") or 0),
        "quick_exit_sessions": int(telemetry.get("quick_exit_sessions") or 0),
        "dwell_30s_sessions": int(telemetry.get("dwell_30s_sessions") or 0),
        "dwell_60s_sessions": int(telemetry.get("dwell_60s_sessions") or 0),
    }


def _compute_raw_scores_and_breakdowns(
    item_ids: list[int],
    telemetry_map: dict,
    gsc_map: dict,
) -> tuple[dict[int, float], dict[int, dict]]:
    """Compute raw + breakdown for each item; skip items with no data."""
    raw_scores: dict[int, float] = {}
    breakdowns: dict[int, dict] = {}
    for item_id in item_ids:
        kwargs = _build_content_value_kwargs(
            telemetry_map.get(item_id, {}),
            gsc_map.get(item_id, {}),
        )
        raw = compute_content_value_raw(**kwargs)
        if raw is not None:
            raw_scores[item_id] = raw
            breakdowns[item_id] = compute_content_value_breakdown(**kwargs)
    return raw_scores, breakdowns


def _normalise_content_value_score(raw: float, min_raw: float, max_raw: float) -> float:
    """Min-max normalise a raw score to ``[FLOOR, FLOOR+RANGE]``.

    Returns SINGLE_ITEM_SCORE when min == max (only one item or all-equal).
    """
    if max_raw <= min_raw:
        return _CONTENT_VALUE_SINGLE_ITEM_SCORE
    normalized = (raw - min_raw) / (max_raw - min_raw)
    return _CONTENT_VALUE_NORMALIZED_FLOOR + (
        _CONTENT_VALUE_NORMALIZED_RANGE * normalized
    )


def _persist_content_value_scores(raw_scores: dict, breakdowns: dict) -> int:
    """Min-max normalise raw scores + bulk-update ContentItem rows. Returns count."""
    min_raw = min(raw_scores.values())
    max_raw = max(raw_scores.values())
    updates = []
    for item in ContentItem.objects.filter(pk__in=raw_scores.keys()):
        score = _normalise_content_value_score(
            raw_scores[item.pk],
            min_raw,
            max_raw,
        )
        item.content_value_score = round(score, 6)
        # Tier 2 slice 5 — store per-term breakdown alongside the normalized
        # score so the suggestion-detail dialog can render "why this score"
        # without recomputing.
        breakdown = breakdowns[item.pk]
        breakdown["normalized"] = item.content_value_score
        item.content_value_diagnostics = breakdown
        updates.append(item)
    if updates:
        ContentItem.objects.bulk_update(
            updates,
            ["content_value_score", "content_value_diagnostics"],
            batch_size=500,
        )
    return len(updates)


def _refresh_content_value_scores(
    *,
    destination_ids: set[int] | None = None,
    lookback_days: int = _CONTENT_VALUE_LOOKBACK_DEFAULT_DAYS,
) -> int:
    item_qs = ContentItem.objects.all()
    if destination_ids is not None:
        if not destination_ids:
            return 0
        item_qs = item_qs.filter(pk__in=destination_ids)
    item_ids = list(item_qs.values_list("pk", flat=True))
    if not item_ids:
        return 0
    window_start = timezone.now().date() - timedelta(days=max(lookback_days, 1) - 1)
    telemetry_map = _aggregate_telemetry_for_score(item_ids, window_start)
    gsc_map = _aggregate_gsc_for_score(item_ids, window_start)
    raw_scores, breakdowns = _compute_raw_scores_and_breakdowns(
        item_ids,
        telemetry_map,
        gsc_map,
    )
    item_qs.update(
        content_value_score=_CONTENT_VALUE_NEUTRAL_SCORE,
        content_value_diagnostics={},
    )
    if not raw_scores:
        return 0
    return _persist_content_value_scores(raw_scores, breakdowns)


_ENGAGEMENT_TIME_CAP_SECONDS = 180.0  # cap for avg engagement time normalization


def _engagement_term_contribution(value: float, weight: float, sign: str) -> float:
    """Map an engagement spec row to its signed contribution."""
    magnitude = weight * value
    return -magnitude if sign == "-" else magnitude


def _compute_engagement_raw_score(telemetry: dict) -> float | None:
    """Compute raw engagement quality from a single telemetry aggregate row.

    Returns None when data is insufficient.

    Phase 3b/3c extension: adds three bounded adjustments from Phase 2
    telemetry — ``+0.025 * dwell_30s_rate`` (Phase 3c, half-weight),
    ``+0.05 * dwell_60s_rate`` (Phase 3b, full-weight) credits, and a
    ``-0.05 * quick_exit_rate`` penalty — on top of the existing
    0.50/0.30/0.20 core weights. All three terms are zero when the Phase 2
    event columns are zero, so pre-Phase-2 sites see no behaviour change
    (neutral fallback). Final result clamped to ``[0.0, 1.0]`` so extreme
    inputs cannot push the score beyond the historical range.

    # Source: Kim, Hassan, White & Zitouni (2014) "Modeling dwell time to
    # predict click-level satisfaction" (WSDM). Dwell is modelled as a
    # satisfaction gradient — the 30-second mark is a partial positive
    # signal and the 60-second mark is the strong positive. Coefficients
    # mirror the Phase 3a/3c ``compute_content_value_raw`` extension for
    # cross-signal consistency — conservative starting values per BLC §1.3,
    # tunable later by FR-018 auto-tuner.

    Body delegates to the shared spec-table helpers used by the breakdown
    counterpart so the formula stays in exactly one place.
    """
    inputs = _build_engagement_term_inputs(telemetry)
    if inputs is None:
        return None
    raw = sum(
        _engagement_term_contribution(inputs[name], weight, sign)
        for name, weight, sign in _ENGAGEMENT_QUALITY_TERM_SPEC
    )
    return max(0.0, min(1.0, raw))


# Per-term spec for the engagement-quality breakdown.
# (name, weight, sign) — contribution = weight * value (negated when sign == "-").
_ENGAGEMENT_QUALITY_TERM_SPEC: tuple[tuple[str, float, str], ...] = (
    ("engagement_rate", 0.50, "+"),
    ("normalized_engagement_time", 0.30, "+"),
    ("inverse_bounce", 0.20, "+"),
    ("dwell_30s_rate", 0.025, "+"),
    ("dwell_60s_rate", 0.05, "+"),
    ("quick_exit_rate", 0.05, "-"),
)


def _build_engagement_term_inputs(telemetry: dict) -> dict[str, float] | None:
    """Compute the per-term ``value`` inputs from a telemetry aggregate row.

    Returns None when every input is zero (the no-data short-circuit).
    """
    dest_views = int(telemetry.get("destination_views") or 0)
    engaged = int(telemetry.get("engaged_sessions") or 0)
    bounced = int(telemetry.get("bounce_sessions") or 0)
    total_time = float(telemetry.get("total_engagement_time") or 0.0)
    sessions = int(telemetry.get("sessions") or 0)
    quick_exit_sessions = int(telemetry.get("quick_exit_sessions") or 0)
    dwell_30s_sessions = int(telemetry.get("dwell_30s_sessions") or 0)
    dwell_60s_sessions = int(telemetry.get("dwell_60s_sessions") or 0)
    if (
        dest_views == 0
        and sessions == 0
        and quick_exit_sessions == 0
        and dwell_30s_sessions == 0
        and dwell_60s_sessions == 0
    ):
        return None
    safe_views = max(dest_views, 1)
    safe_sessions = max(sessions, 1)
    avg_time = total_time / safe_sessions
    return {
        "engagement_rate": engaged / safe_views,
        "normalized_engagement_time": min(avg_time / _ENGAGEMENT_TIME_CAP_SECONDS, 1.0),
        "inverse_bounce": 1.0 - min(bounced / safe_sessions, 1.0),
        "dwell_30s_rate": min(dwell_30s_sessions / safe_views, 1.0),
        "dwell_60s_rate": min(dwell_60s_sessions / safe_views, 1.0),
        "quick_exit_rate": min(quick_exit_sessions / safe_views, 1.0),
    }


def compute_engagement_quality_breakdown(telemetry: dict) -> dict:
    """Tier 2 slice 5 — per-term decomposition of ``_compute_engagement_raw_score``.

    Mirrors the six-term additive formula exactly. Returns
    ``{"raw": float, "terms": [...], "has_data": bool}``. ``has_data=False``
    when every input is zero; caller treats this as "no telemetry yet" and
    hides the breakdown. The refresh layer stores the clamped ``normalized``
    alongside the per-term contributions so the dialog can show both numbers.
    """
    inputs = _build_engagement_term_inputs(telemetry)
    if inputs is None:
        return {"raw": 0.0, "terms": [], "has_data": False}
    terms = [
        {
            "name": name,
            "value": inputs[name],
            "weight": weight,
            "sign": sign,
            "contribution": _engagement_term_contribution(inputs[name], weight, sign),
        }
        for name, weight, sign in _ENGAGEMENT_QUALITY_TERM_SPEC
    ]
    raw = sum(term["contribution"] for term in terms)
    return {"raw": raw, "terms": terms, "has_data": True}


_ENGAGEMENT_NEUTRAL_SCORE = 0.5
_ENGAGEMENT_NORMALIZED_FLOOR = 0.30
_ENGAGEMENT_NORMALIZED_RANGE = 0.60
_ENGAGEMENT_SINGLE_ITEM_SCORE = 0.60


def _aggregate_engagement_telemetry(item_ids: list[int], window_start) -> dict:
    """Bulk-sum per-destination engagement telemetry + Phase 3b/3c signals."""
    rows = (
        SuggestionTelemetryDaily.objects.filter(
            destination_id__in=item_ids,
            date__gte=window_start,
        )
        .exclude(country__in=BLOCKED_TELEMETRY_COUNTRY_VALUES)
        .values("destination_id")
        .annotate(
            destination_views=Sum("destination_views"),
            engaged_sessions=Sum("engaged_sessions"),
            bounce_sessions=Sum("bounce_sessions"),
            total_engagement_time=Sum("total_engagement_time_seconds"),
            sessions=Sum("sessions"),
            # Phase 3b/3c — dwell-30s/60s credits + quick-exit penalty.
            quick_exit_sessions=Sum("quick_exit_sessions"),
            dwell_30s_sessions=Sum("dwell_30s_sessions"),
            dwell_60s_sessions=Sum("dwell_60s_sessions"),
        )
    )
    return {int(row["destination_id"]): row for row in rows}


def _compute_engagement_raw_and_breakdowns(
    item_ids: list[int],
    telemetry_map: dict,
) -> tuple[dict[int, float], dict[int, dict]]:
    """For each item with telemetry, compute the raw + breakdown."""
    raw_scores: dict[int, float] = {}
    breakdowns: dict[int, dict] = {}
    for item_id in item_ids:
        telemetry = telemetry_map.get(item_id)
        if telemetry is None:
            continue
        score = _compute_engagement_raw_score(telemetry)
        if score is None:
            continue
        raw_scores[item_id] = score
        breakdowns[item_id] = compute_engagement_quality_breakdown(telemetry)
    return raw_scores, breakdowns


def _normalise_engagement_score(raw: float, min_raw: float, max_raw: float) -> float:
    """Min-max normalise raw score to [FLOOR, FLOOR+RANGE]; SINGLE_ITEM when min==max."""
    if max_raw <= min_raw:
        return _ENGAGEMENT_SINGLE_ITEM_SCORE
    normalized = (raw - min_raw) / (max_raw - min_raw)
    return _ENGAGEMENT_NORMALIZED_FLOOR + (_ENGAGEMENT_NORMALIZED_RANGE * normalized)


def _persist_engagement_quality_scores(raw_scores: dict, breakdowns: dict) -> int:
    """Min-max normalise + bulk-update ContentItem rows. Returns count."""
    min_raw, max_raw = min(raw_scores.values()), max(raw_scores.values())
    updates = []
    for item in ContentItem.objects.filter(pk__in=raw_scores.keys()):
        score = _normalise_engagement_score(raw_scores[item.pk], min_raw, max_raw)
        item.engagement_quality_score = round(score, 6)
        # Tier 2 slice 5 — store per-term breakdown alongside the clamped
        # score so the suggestion-detail dialog renders "why this score"
        # without a second API round-trip.
        breakdown = breakdowns[item.pk]
        breakdown["normalized"] = item.engagement_quality_score
        item.engagement_quality_diagnostics = breakdown
        updates.append(item)
    if updates:
        ContentItem.objects.bulk_update(
            updates,
            ["engagement_quality_score", "engagement_quality_diagnostics"],
            batch_size=500,
        )
    return len(updates)


def _refresh_engagement_quality_scores(
    *,
    destination_ids: set[int] | None = None,
    lookback_days: int = _CONTENT_VALUE_LOOKBACK_DEFAULT_DAYS,
) -> int:
    """Compute a distinct engagement quality score from GA4 behavioural data.

    Isolates user engagement quality (engaged-session rate, avg engagement
    time, inverse bounce) separately from traffic volume.
    """
    import logging

    item_qs = ContentItem.objects.all()
    if destination_ids is not None:
        if not destination_ids:
            return 0
        item_qs = item_qs.filter(pk__in=destination_ids)
    item_ids = list(item_qs.values_list("pk", flat=True))
    if not item_ids:
        return 0
    window_start = timezone.now().date() - timedelta(days=max(lookback_days, 1) - 1)
    telemetry_map = _aggregate_engagement_telemetry(item_ids, window_start)
    raw_scores, breakdowns = _compute_engagement_raw_and_breakdowns(
        item_ids,
        telemetry_map,
    )
    item_qs.update(
        engagement_quality_score=_ENGAGEMENT_NEUTRAL_SCORE,
        engagement_quality_diagnostics={},
    )
    if not raw_scores:
        return 0
    count = _persist_engagement_quality_scores(raw_scores, breakdowns)
    logging.getLogger(__name__).info(
        "Refreshed engagement_quality_score for %s items",
        count,
    )
    return count
