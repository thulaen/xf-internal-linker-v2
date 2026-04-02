"""FR-016 Slice 3 sync helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any
from urllib.parse import urljoin

import requests
from django.utils import timezone

from apps.suggestions.models import Suggestion

from .models import AnalyticsSyncRun, SuggestionTelemetryDaily, TelemetryCoverageDaily

MATOMO_EVENT_FIELDS = {
    "suggestion_link_impression": "impressions",
    "suggestion_link_click": "clicks",
    "suggestion_destination_view": "destination_views",
    "suggestion_destination_engaged": "engaged_sessions",
    "suggestion_destination_conversion": "conversions",
}


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
        return "pipeline_bundle", version_date, version_date.isoformat().replace("-", "_")
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


def _walk_matomo_rows(rows: list[dict[str, Any]], *, current_action: str = "") -> list[tuple[str, str, int]]:
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


def _matomo_api_get(*, base_url: str, token_auth: str, method: str, params: dict[str, Any]) -> Any:
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


def _fetch_matomo_event_rows(*, base_url: str, token_auth: str, site_id: str, target_date: date) -> tuple[list[tuple[str, str, int]], int]:
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
        },
    )
    rows = payload if isinstance(payload, list) else []
    parsed = _walk_matomo_rows(rows)
    return parsed, len(rows)


def _upsert_telemetry_row(*, target_date: date, suggestion: Suggestion, field_totals: dict[str, int], event_schema: str) -> tuple[int, int]:
    algorithm_key, algorithm_version_date, algorithm_version_slug = _algorithm_version_parts(suggestion)
    defaults = {
        "destination": suggestion.destination,
        "host": suggestion.host,
        "algorithm_key": algorithm_key,
        "algorithm_version_date": algorithm_version_date,
        "event_schema": event_schema,
        "source_label": "wordpress" if suggestion.host.content_type.startswith("wp_") else "xenforo",
        "same_silo": _same_silo(suggestion),
        "impressions": int(field_totals.get("impressions", 0)),
        "clicks": int(field_totals.get("clicks", 0)),
        "destination_views": int(field_totals.get("destination_views", 0)),
        "engaged_sessions": int(field_totals.get("engaged_sessions", 0)),
        "conversions": int(field_totals.get("conversions", 0)),
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
        suggestion_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for suggestion_id, event_name, count in parsed_rows:
            if event_name not in MATOMO_EVENT_FIELDS:
                continue
            suggestion_totals[suggestion_id][MATOMO_EVENT_FIELDS[event_name]] += count

        for suggestion_id, field_totals in suggestion_totals.items():
            try:
                suggestion = Suggestion.objects.select_related(
                    "destination",
                    "destination__scope",
                    "host",
                    "host__scope",
                    "pipeline_run",
                ).get(suggestion_id=suggestion_id)
            except Suggestion.DoesNotExist:
                missing_metadata_events += int(sum(field_totals.values()))
                continue

            written, updated = _upsert_telemetry_row(
                target_date=target_date,
                suggestion=suggestion,
                field_totals=field_totals,
                event_schema=event_schema,
            )
            rows_written += written
            rows_updated += updated
            if field_totals.get("impressions", 0) > 0:
                observed_impression_links += 1
            if field_totals.get("clicks", 0) > 0:
                observed_click_links += 1
            attributed_destination_sessions += int(field_totals.get("destination_views", 0))

        coverage_defaults = {
            "expected_instrumented_links": 0,
            "observed_impression_links": observed_impression_links,
            "observed_click_links": observed_click_links,
            "attributed_destination_sessions": attributed_destination_sessions,
            "unattributed_destination_sessions": 0,
            "duplicate_event_drops": 0,
            "missing_metadata_events": missing_metadata_events,
            "delayed_rows_rewritten": rows_updated,
            "coverage_state": "healthy" if observed_impression_links or observed_click_links else "partial",
        }
        TelemetryCoverageDaily.objects.update_or_create(
            date=target_date,
            event_schema=event_schema,
            source_label="matomo",
            algorithm_version_slug="",
            defaults=coverage_defaults,
        )

    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_updated": rows_updated,
    }


def run_ga4_sync(sync_run: AnalyticsSyncRun) -> dict[str, int]:
    from .views import get_ga4_telemetry_settings

    settings = get_ga4_telemetry_settings()
    if not settings.get("sync_enabled"):
        raise RuntimeError("GA4 sync is disabled in settings.")
    raise RuntimeError(
        "GA4 read sync is not wired yet. The GUI currently stores Measurement Protocol write credentials, "
        "but the GA4 Data API read-auth path still needs its own GUI-safe setup."
    )
