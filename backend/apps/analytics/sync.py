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
from apps.suggestions.models import Suggestion

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
        "source_label": "wordpress"
        if suggestion.host.content_type.startswith("wp_")
        else "xenforo",
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
    sessions = int(field_totals.get("sessions", 0))
    engaged_sessions = int(field_totals.get("engaged_sessions", 0))
    total_engagement = float(field_totals.get("total_engagement_time_seconds", 0.0))
    defaults = {
        "destination": suggestion.destination,
        "host": suggestion.host,
        "algorithm_key": algorithm_key,
        "algorithm_version_date": algorithm_version_date,
        "event_schema": event_schema,
        "source_label": "wordpress"
        if suggestion.host.content_type.startswith("wp_")
        else "xenforo",
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


def run_matomo_sync(sync_run: AnalyticsSyncRun) -> dict[str, int]:
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
    rows_read = 0
    rows_written = 0
    rows_updated = 0
    touched_destination_ids: set[int] = set()

    for offset in range(max(sync_run.lookback_days, 1)):
        target_date = timezone.now().date() - timedelta(days=offset)
        missing_metadata_events = 0
        observed_impression_links = 0
        observed_click_links = 0
        attributed_destination_sessions = 0
        parsed_rows, source_rows = _fetch_matomo_event_rows(
            base_url=base_url,
            token_auth=token_auth,
            site_id=site_id,
            target_date=target_date,
        )
        rows_read += source_rows
        suggestion_totals: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        for suggestion_id, event_name, count in parsed_rows:
            if event_name not in MATOMO_EVENT_FIELDS:
                continue
            suggestion_totals[suggestion_id][MATOMO_EVENT_FIELDS[event_name]] += count

        # Bulk-load all referenced suggestions in one query instead of one per row.
        suggestion_ids_for_day = list(suggestion_totals.keys())
        suggestions_map = {
            str(s.suggestion_id): s
            for s in Suggestion.objects.select_related(
                "destination",
                "destination__scope",
                "host",
                "host__scope",
                "pipeline_run",
            ).filter(suggestion_id__in=suggestion_ids_for_day)
        }

        for suggestion_id, field_totals in suggestion_totals.items():
            suggestion = suggestions_map.get(suggestion_id)
            if suggestion is None:
                missing_metadata_events += int(sum(field_totals.values()))
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
                observed_impression_links += 1
            if field_totals.get("clicks", 0) > 0:
                observed_click_links += 1
            attributed_destination_sessions += int(
                field_totals.get("destination_views", 0)
            )

        coverage_defaults = {
            "expected_instrumented_links": 0,
            "observed_impression_links": observed_impression_links,
            "observed_click_links": observed_click_links,
            "attributed_destination_sessions": attributed_destination_sessions,
            "unattributed_destination_sessions": 0,
            "duplicate_event_drops": 0,
            "missing_metadata_events": missing_metadata_events,
            "delayed_rows_rewritten": rows_updated,
            "coverage_state": "healthy"
            if observed_impression_links or observed_click_links
            else "partial",
        }
        TelemetryCoverageDaily.objects.update_or_create(
            date=target_date,
            event_schema=event_schema,
            source_label="matomo",
            algorithm_version_slug="",
            defaults=coverage_defaults,
        )

    _refresh_content_value_scores(destination_ids=touched_destination_ids)
    _refresh_engagement_quality_scores(destination_ids=touched_destination_ids)

    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_updated": rows_updated,
    }


def run_ga4_sync(sync_run: AnalyticsSyncRun) -> dict[str, int]:
    from .views import (
        get_ga4_telemetry_settings,
        _google_oauth_client_secret,
        _google_oauth_refresh_token,
        _read_setting,
    )

    settings = get_ga4_telemetry_settings()
    property_id = str(settings.get("property_id") or "").strip()
    project_id = str(settings.get("read_project_id") or "").strip()
    client_email = str(settings.get("read_client_email") or "").strip()
    private_key = _read_setting("analytics.ga4_read_private_key", "") or ""
    geo_granularity = str(settings.get("geo_granularity") or "country").strip()
    # OAuth credentials
    refresh_token = settings.get("oauth_connected") and _google_oauth_refresh_token()
    client_id = settings.get("google_oauth_client_id")
    client_secret = _google_oauth_client_secret()

    if refresh_token and client_id and client_secret:
        service = build_ga4_data_service(
            property_id=property_id,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        if not property_id or not project_id or not client_email or not private_key:
            raise RuntimeError(
                "GA4 sync needs the property ID plus saved GA4 read-access credentials on the settings page."
            )

        service = build_ga4_data_service(
            property_id=property_id,
            project_id=project_id,
            client_email=client_email,
            private_key=private_key,
        )

    rows_read = 0
    rows_written = 0
    rows_updated = 0
    event_schema = str(settings.get("event_schema") or "fr016_v1")
    touched_destination_ids: set[int] = set()

    for offset in range(max(sync_run.lookback_days, 1)):
        target_date = timezone.now().date() - timedelta(days=offset)
        merged_rows: dict[
            tuple[str, str, str, str, str, str], dict[str, int | float]
        ] = defaultdict(
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
            }
        )
        missing_metadata_events = 0
        observed_impression_links = 0
        observed_click_links = 0
        attributed_destination_sessions = 0

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
                parsed = _ga4_dimensions_from_row(
                    row=row,
                    dimension_names=_ga4_dimension_names(
                        geo_granularity=geo_granularity
                    ),
                    geo_granularity=geo_granularity,
                )
                if is_blocked_country(parsed["country"]):
                    continue
                key = (
                    parsed["suggestion_id"],
                    parsed["device_category"],
                    parsed["default_channel_group"],
                    parsed["source_medium"],
                    parsed["country"],
                    parsed["region"],
                )
                count = _ga4_metric_int(row, 0)
                merged_rows[key][field_name] = int(merged_rows[key][field_name]) + count
                merged_rows[key]["event_count"] = (
                    int(merged_rows[key]["event_count"]) + count
                )

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
        rows_read += len(session_rows)
        for row in session_rows:
            parsed = _ga4_dimensions_from_row(
                row=row,
                dimension_names=_ga4_dimension_names(geo_granularity=geo_granularity),
                geo_granularity=geo_granularity,
            )
            if is_blocked_country(parsed["country"]):
                continue
            key = (
                parsed["suggestion_id"],
                parsed["device_category"],
                parsed["default_channel_group"],
                parsed["source_medium"],
                parsed["country"],
                parsed["region"],
            )
            merged_rows[key]["destination_views"] = _ga4_metric_int(row, 0)
            merged_rows[key]["sessions"] = _ga4_metric_int(row, 1)
            merged_rows[key]["engaged_sessions"] = max(
                int(merged_rows[key]["engaged_sessions"]),
                _ga4_metric_int(row, 2),
            )
            merged_rows[key]["total_engagement_time_seconds"] = _ga4_metric_float(
                row, 3
            )

        suggestion_ids = [key[0] for key in merged_rows.keys() if key[0]]
        suggestions = {
            str(suggestion.suggestion_id): suggestion
            for suggestion in Suggestion.objects.select_related(
                "destination",
                "destination__scope",
                "host",
                "host__scope",
                "pipeline_run",
            ).filter(suggestion_id__in=suggestion_ids)
        }

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
                missing_metadata_events += event_count
                continue
            suggestion = suggestions.get(suggestion_id)
            if suggestion is None:
                missing_metadata_events += event_count
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
                observed_impression_links += 1
            if int(field_totals.get("clicks", 0)) > 0:
                observed_click_links += 1
            attributed_destination_sessions += int(
                field_totals.get("destination_views", 0)
            )

        TelemetryCoverageDaily.objects.update_or_create(
            date=target_date,
            event_schema=event_schema,
            source_label="ga4",
            algorithm_version_slug="",
            defaults={
                "expected_instrumented_links": 0,
                "observed_impression_links": observed_impression_links,
                "observed_click_links": observed_click_links,
                "attributed_destination_sessions": attributed_destination_sessions,
                "unattributed_destination_sessions": 0,
                "duplicate_event_drops": 0,
                "missing_metadata_events": missing_metadata_events,
                "delayed_rows_rewritten": rows_updated,
                "coverage_state": "healthy"
                if observed_impression_links or observed_click_links
                else "partial",
            },
        )

    _refresh_content_value_scores(destination_ids=touched_destination_ids)
    _refresh_engagement_quality_scores(destination_ids=touched_destination_ids)

    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_updated": rows_updated,
    }


def run_gsc_sync(sync_run: AnalyticsSyncRun) -> dict[str, int]:
    """
    Fetch search performance metrics from GSC and store them as raw daily logs.
    These logs feed the attribution engine in Slice 4.
    """
    from .views import (
        get_gsc_settings,
        _gsc_private_key,
        _google_oauth_refresh_token,
        _google_oauth_client_id,
        _google_oauth_client_secret,
    )
    from .models import GSCDailyPerformance

    settings = get_gsc_settings()
    if not settings.get("sync_enabled"):
        return {
            "rows_read": 0,
            "rows_written": 0,
            "rows_updated": 0,
            "error": "GSC sync is disabled.",
        }

    property_url = settings.get("property_url")

    # OAuth credentials
    refresh_token = settings.get("oauth_connected") and _google_oauth_refresh_token()
    client_id = _google_oauth_client_id()
    client_secret = _google_oauth_client_secret()

    if refresh_token and client_id and client_secret:
        service = build_gsc_service(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        client_email = settings.get("client_email")
        private_key = _gsc_private_key()

        if not property_url or not client_email or not private_key:
            raise RuntimeError(
                "GSC sync needs property_url, client_email, and private_key."
            )

        service = build_gsc_service(client_email=client_email, private_key=private_key)

    # Search Console data has a ~2-3 day processing lag.
    # We look back from 3 days ago to ensure we have data.
    end_date = timezone.now().date() - timedelta(days=3)
    start_date = end_date - timedelta(days=sync_run.lookback_days)

    # Pull page totals for the raw ingestion table.
    page_rows = fetch_gsc_performance_data(
        service=service,
        property_url=property_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=["date", "page"],
        excluded_country_codes=list(BLOCKED_COUNTRY_CODES_ALPHA3),
    )
    query_rows = fetch_gsc_performance_data(
        service=service,
        property_url=property_url,
        start_date=start_date,
        end_date=end_date,
        dimensions=["date", "page", "query"],
        excluded_country_codes=list(BLOCKED_COUNTRY_CODES_ALPHA3),
    )

    rows_read = len(page_rows) + len(query_rows)
    rows_written = 0
    rows_updated = 0

    # Group by Page URL to find ContentItems efficiently for the legacy SearchMetric link
    page_urls_in_batch = list(
        {
            row["keys"][1]
            for row in page_rows + query_rows
            if len(row.get("keys", [])) >= 2
        }
    )
    content_map = {
        item.url: item
        for item in ContentItem.objects.filter(url__in=page_urls_in_batch)
    }
    page_totals_by_item_date: dict[tuple[int, str], dict[str, float | int]] = {}
    item_dates_with_query_rows: set[tuple[int, str]] = set()
    touched_destination_ids: set[int] = set()

    for row in page_rows:
        # dimensions=['date', 'page']
        dt_str = row["keys"][0]
        page_url = row["keys"][1]

        impressions = int(row.get("impressions", 0))
        clicks = int(row.get("clicks", 0))
        ctr = float(row.get("ctr", 0.0))
        avg_pos = float(row.get("position", 0.0))

        # 1. Store in the new GSCDailyPerformance raw log table (Slice 3 focus)
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

        # 2. Also update legacy SearchMetric if we can map to a ContentItem (for repo stability)
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

    for row in query_rows:
        if len(row.get("keys", [])) < 3:
            continue
        dt_str = row["keys"][0]
        page_url = row["keys"][1]
        query_text = str(row["keys"][2] or "").strip()
        item = content_map.get(page_url)
        if item is None:
            continue
        if query_text:
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

    _refresh_content_value_scores(destination_ids=touched_destination_ids)
    _refresh_engagement_quality_scores(destination_ids=touched_destination_ids)

    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_updated": rows_updated,
    }


def _refresh_content_value_scores(
    *, destination_ids: set[int] | None = None, lookback_days: int = 28
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
    telemetry_rows = (
        SuggestionTelemetryDaily.objects.filter(
            destination_id__in=item_ids, date__gte=window_start
        )
        .exclude(country__in=BLOCKED_TELEMETRY_COUNTRY_VALUES)
        .values("destination_id")
        .annotate(
            clicks=Sum("clicks"),
            destination_views=Sum("destination_views"),
            engaged_sessions=Sum("engaged_sessions"),
            conversions=Sum("conversions"),
        )
    )
    gsc_rows = (
        SearchMetric.objects.filter(
            content_item_id__in=item_ids, source="gsc", date__gte=window_start
        )
        .exclude(query="")
        .values("content_item_id")
        .annotate(
            clicks=Sum("clicks"),
            impressions=Sum("impressions"),
            ctr=Avg("ctr"),
        )
    )
    telemetry_map = {int(row["destination_id"]): row for row in telemetry_rows}
    gsc_map = {int(row["content_item_id"]): row for row in gsc_rows}

    raw_scores: dict[int, float] = {}
    for item_id in item_ids:
        telemetry = telemetry_map.get(item_id, {})
        gsc = gsc_map.get(item_id, {})
        gsc_clicks = int(gsc.get("clicks") or 0)
        gsc_impressions = int(gsc.get("impressions") or 0)
        gsc_ctr = float(gsc.get("ctr") or 0.0)
        destination_views = int(telemetry.get("destination_views") or 0)
        engaged_sessions = int(telemetry.get("engaged_sessions") or 0)
        conversions = int(telemetry.get("conversions") or 0)
        telemetry_clicks = int(telemetry.get("clicks") or 0)

        if not any(
            [
                gsc_clicks,
                gsc_impressions,
                destination_views,
                engaged_sessions,
                conversions,
                telemetry_clicks,
            ]
        ):
            continue

        engagement_rate = engaged_sessions / max(destination_views, 1)
        conversion_rate = conversions / max(destination_views, 1)
        click_rate = telemetry_clicks / max(destination_views, 1)
        raw_scores[item_id] = (
            (0.40 * math.log1p(gsc_clicks))
            + (0.20 * gsc_ctr * 100.0)
            + (0.20 * math.log1p(destination_views))
            + (0.10 * engagement_rate * 10.0)
            + (0.05 * conversion_rate * 10.0)
            + (0.05 * click_rate * 10.0)
        )

    item_qs.update(content_value_score=0.5)
    if not raw_scores:
        return 0

    min_raw = min(raw_scores.values())
    max_raw = max(raw_scores.values())
    updates = []
    for item in ContentItem.objects.filter(pk__in=raw_scores.keys()):
        if max_raw > min_raw:
            normalized = (raw_scores[item.pk] - min_raw) / (max_raw - min_raw)
            score = 0.30 + (0.60 * normalized)
        else:
            score = 0.75
        item.content_value_score = round(score, 6)
        updates.append(item)

    if updates:
        ContentItem.objects.bulk_update(
            updates, ["content_value_score"], batch_size=500
        )
    return len(updates)


_ENGAGEMENT_TIME_CAP_SECONDS = 180.0  # cap for avg engagement time normalization


def _compute_engagement_raw_score(telemetry: dict) -> float | None:
    """Compute raw engagement quality from a single telemetry aggregate row.

    Returns None when data is insufficient.
    """
    dest_views = int(telemetry.get("destination_views") or 0)
    engaged = int(telemetry.get("engaged_sessions") or 0)
    bounced = int(telemetry.get("bounce_sessions") or 0)
    total_time = float(telemetry.get("total_engagement_time") or 0.0)
    sessions = int(telemetry.get("sessions") or 0)

    if dest_views == 0 and sessions == 0:
        return None

    engagement_rate = engaged / max(dest_views, 1)
    avg_time = total_time / max(sessions, 1)
    normalized_time = min(avg_time / _ENGAGEMENT_TIME_CAP_SECONDS, 1.0)
    bounce_rate = bounced / max(sessions, 1)
    inverse_bounce = 1.0 - min(bounce_rate, 1.0)

    return 0.50 * engagement_rate + 0.30 * normalized_time + 0.20 * inverse_bounce


def _refresh_engagement_quality_scores(
    *, destination_ids: set[int] | None = None, lookback_days: int = 28
) -> int:
    """Compute a distinct engagement quality score from GA4 behavioural data.

    Isolates user engagement quality (engaged-session rate, avg engagement
    time, inverse bounce) separately from traffic volume.
    """
    import logging

    logger_local = logging.getLogger(__name__)

    item_qs = ContentItem.objects.all()
    if destination_ids is not None:
        if not destination_ids:
            return 0
        item_qs = item_qs.filter(pk__in=destination_ids)

    item_ids = list(item_qs.values_list("pk", flat=True))
    if not item_ids:
        return 0

    window_start = timezone.now().date() - timedelta(days=max(lookback_days, 1) - 1)
    telemetry_rows = (
        SuggestionTelemetryDaily.objects.filter(
            destination_id__in=item_ids, date__gte=window_start
        )
        .exclude(country__in=BLOCKED_TELEMETRY_COUNTRY_VALUES)
        .values("destination_id")
        .annotate(
            destination_views=Sum("destination_views"),
            engaged_sessions=Sum("engaged_sessions"),
            bounce_sessions=Sum("bounce_sessions"),
            total_engagement_time=Sum("total_engagement_time_seconds"),
            sessions=Sum("sessions"),
        )
    )
    telemetry_map = {int(row["destination_id"]): row for row in telemetry_rows}

    raw_scores: dict[int, float] = {}
    for item_id in item_ids:
        telemetry = telemetry_map.get(item_id)
        if telemetry is not None:
            score = _compute_engagement_raw_score(telemetry)
            if score is not None:
                raw_scores[item_id] = score

    item_qs.update(engagement_quality_score=0.5)
    if not raw_scores:
        return 0

    min_raw, max_raw = min(raw_scores.values()), max(raw_scores.values())
    updates = []
    for item in ContentItem.objects.filter(pk__in=raw_scores.keys()):
        if max_raw > min_raw:
            normalized = (raw_scores[item.pk] - min_raw) / (max_raw - min_raw)
            score = 0.30 + (0.60 * normalized)
        else:
            score = 0.60
        item.engagement_quality_score = round(score, 6)
        updates.append(item)

    if updates:
        ContentItem.objects.bulk_update(
            updates, ["engagement_quality_score"], batch_size=500
        )
    logger_local.info("Refreshed engagement_quality_score for %s items", len(updates))
    return len(updates)
