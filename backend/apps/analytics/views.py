"""Analytics views for FR-016 settings, connection tests, and overview data."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urljoin, urlparse

import requests
from django.db.models import Sum
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AppSetting

from .integration_snippet import build_integration_payload
from .models import AnalyticsSyncRun, SuggestionTelemetryDaily, TelemetryCoverageDaily
from .tasks import sync_ga4_telemetry, sync_matomo_telemetry
from .ga4_client import build_ga4_data_service, test_ga4_data_api_access

GA4_DEFAULTS = {
    "behavior_enabled": False,
    "property_id": "",
    "measurement_id": "",
    "api_secret_configured": False,
    "read_project_id": "",
    "read_client_email": "",
    "read_private_key_configured": False,
    "sync_enabled": False,
    "sync_lookback_days": 7,
    "event_schema": "fr016_v1",
    "geo_granularity": "country",
    "retention_days": 400,
    "impression_visible_ratio": 0.5,
    "impression_min_ms": 1000,
    "engaged_min_seconds": 10,
}

MATOMO_DEFAULTS = {
    "enabled": False,
    "url": "",
    "site_id_xenforo": "",
    "site_id_wordpress": "",
    "token_auth_configured": False,
    "sync_enabled": False,
    "sync_lookback_days": 7,
}


def _read_setting(key: str, default: str | None = None) -> str | None:
    row = AppSetting.objects.filter(key=key).first()
    if row is None:
        return default
    return row.value


def _read_bool(key: str, default: bool) -> bool:
    raw = _read_setting(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _read_int(key: str, default: int) -> int:
    raw = _read_setting(key)
    try:
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def _read_float(key: str, default: float) -> float:
    raw = _read_setting(key)
    try:
        return float(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def _latest_sync(source: str) -> dict | None:
    row = AnalyticsSyncRun.objects.filter(source=source).order_by("-started_at").first()
    if row is None:
        return None
    return {
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "rows_read": row.rows_read,
        "rows_written": row.rows_written,
        "rows_updated": row.rows_updated,
        "lookback_days": row.lookback_days,
        "error_message": row.error_message,
    }


def get_ga4_telemetry_settings() -> dict:
    property_id = (_read_setting("analytics.ga4_property_id", "") or "").strip()
    measurement_id = (_read_setting("analytics.ga4_measurement_id", "") or "").strip()
    api_secret = (_read_setting("analytics.ga4_api_secret", "") or "").strip()
    read_project_id = (_read_setting("analytics.ga4_read_project_id", "") or "").strip()
    read_client_email = (_read_setting("analytics.ga4_read_client_email", "") or "").strip()
    read_private_key = (_read_setting("analytics.ga4_read_private_key", "") or "").strip()
    sync = _latest_sync("ga4")
    status = "not_configured"
    message = "Fill in the browser-event fields and test the connection."
    if measurement_id and api_secret:
        status = "saved"
        message = "Browser-event credentials are saved. Run Test Connection to confirm they work."

    read_status = "not_configured"
    read_message = "Fill in the GA4 read-access fields and test read access."
    if property_id and read_client_email and read_private_key:
        read_status = "saved"
        read_message = "Read-access credentials are saved. Run Test Read Access to confirm they work."
    if sync and sync["status"] == "completed":
        read_status = "connected"
        read_message = "GA4 read sync completed successfully the last time it ran."
    elif sync and sync["status"] == "failed":
        read_status = "error"
        read_message = sync["error_message"] or "The last GA4 sync failed."

    return {
        "behavior_enabled": _read_bool("analytics.ga4_behavior_enabled", GA4_DEFAULTS["behavior_enabled"]),
        "property_id": property_id,
        "measurement_id": measurement_id,
        "api_secret_configured": bool(api_secret),
        "read_project_id": read_project_id,
        "read_client_email": read_client_email,
        "read_private_key_configured": bool(read_private_key),
        "sync_enabled": _read_bool("analytics.ga4_sync_enabled", GA4_DEFAULTS["sync_enabled"]),
        "sync_lookback_days": _read_int("analytics.ga4_sync_lookback_days", GA4_DEFAULTS["sync_lookback_days"]),
        "event_schema": (_read_setting("analytics.telemetry_event_schema", GA4_DEFAULTS["event_schema"]) or GA4_DEFAULTS["event_schema"]).strip(),
        "geo_granularity": (_read_setting("analytics.telemetry_geo_granularity", GA4_DEFAULTS["geo_granularity"]) or GA4_DEFAULTS["geo_granularity"]).strip(),
        "retention_days": _read_int("analytics.telemetry_retention_days", GA4_DEFAULTS["retention_days"]),
        "impression_visible_ratio": _read_float("analytics.telemetry_impression_visible_ratio", GA4_DEFAULTS["impression_visible_ratio"]),
        "impression_min_ms": _read_int("analytics.telemetry_impression_min_ms", GA4_DEFAULTS["impression_min_ms"]),
        "engaged_min_seconds": _read_int("analytics.telemetry_engaged_min_seconds", GA4_DEFAULTS["engaged_min_seconds"]),
        "connection_status": status,
        "connection_message": message,
        "read_connection_status": read_status,
        "read_connection_message": read_message,
        "last_sync": sync,
    }


def get_matomo_settings() -> dict:
    base_url = (_read_setting("analytics.matomo_url", "") or "").strip().rstrip("/")
    token_auth = (_read_setting("analytics.matomo_token_auth", "") or "").strip()
    sync = _latest_sync("matomo")
    status = "not_configured"
    message = "Fill in the Matomo fields and test the connection."
    if base_url and token_auth:
        status = "saved"
        message = "Credentials are saved. Run Test Connection to confirm they work."
    if sync and sync["status"] == "completed":
        status = "connected"
        message = "Matomo synced successfully the last time it ran."
    elif sync and sync["status"] == "failed":
        status = "error"
        message = sync["error_message"] or "The last Matomo sync failed."

    return {
        "enabled": _read_bool("analytics.matomo_enabled", MATOMO_DEFAULTS["enabled"]),
        "url": base_url,
        "site_id_xenforo": (_read_setting("analytics.matomo_site_id_xenforo", "") or "").strip(),
        "site_id_wordpress": (_read_setting("analytics.matomo_site_id_wordpress", "") or "").strip(),
        "token_auth_configured": bool(token_auth),
        "sync_enabled": _read_bool("analytics.matomo_sync_enabled", MATOMO_DEFAULTS["sync_enabled"]),
        "sync_lookback_days": _read_int("analytics.matomo_sync_lookback_days", MATOMO_DEFAULTS["sync_lookback_days"]),
        "connection_status": status,
        "connection_message": message,
        "last_sync": sync,
    }


def _coerce_bool(value, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field_name} must be true or false.")


def _coerce_int(value, field_name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a whole number.") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return parsed


def _coerce_float(value, field_name: str, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number.") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return parsed


def _validate_ga4_payload(payload: dict) -> tuple[dict, bool]:
    current = get_ga4_telemetry_settings()
    property_id = str(payload.get("property_id", current["property_id"])).strip()
    measurement_id = str(payload.get("measurement_id", current["measurement_id"])).strip().upper()
    read_project_id = str(payload.get("read_project_id", current["read_project_id"])).strip()
    read_client_email = str(payload.get("read_client_email", current["read_client_email"])).strip()
    if property_id and not property_id.isdigit():
        raise ValueError("property_id must be numbers only.")
    if measurement_id and not measurement_id.startswith("G-"):
        raise ValueError("measurement_id must start with G-.")
    if read_client_email and "@" not in read_client_email:
        raise ValueError("read_client_email must look like an email address.")

    api_secret_provided = "api_secret" in payload
    api_secret = str(payload.get("api_secret", "")).strip() if api_secret_provided else None
    read_private_key_provided = "read_private_key" in payload
    read_private_key = str(payload.get("read_private_key", "")).strip() if read_private_key_provided else None

    geo_granularity = str(payload.get("geo_granularity", current["geo_granularity"])).strip()
    if geo_granularity not in {"none", "country", "country_region"}:
        raise ValueError("geo_granularity must be none, country, or country_region.")

    event_schema = str(payload.get("event_schema", current["event_schema"])).strip() or GA4_DEFAULTS["event_schema"]

    validated = {
        "behavior_enabled": _coerce_bool(payload.get("behavior_enabled", current["behavior_enabled"]), "behavior_enabled"),
        "property_id": property_id,
        "measurement_id": measurement_id,
        "read_project_id": read_project_id,
        "read_client_email": read_client_email,
        "sync_enabled": _coerce_bool(payload.get("sync_enabled", current["sync_enabled"]), "sync_enabled"),
        "sync_lookback_days": _coerce_int(payload.get("sync_lookback_days", current["sync_lookback_days"]), "sync_lookback_days", 1, 30),
        "event_schema": event_schema,
        "geo_granularity": geo_granularity,
        "retention_days": _coerce_int(payload.get("retention_days", current["retention_days"]), "retention_days", 1, 800),
        "impression_visible_ratio": _coerce_float(payload.get("impression_visible_ratio", current["impression_visible_ratio"]), "impression_visible_ratio", 0.25, 1.0),
        "impression_min_ms": _coerce_int(payload.get("impression_min_ms", current["impression_min_ms"]), "impression_min_ms", 250, 5000),
        "engaged_min_seconds": _coerce_int(payload.get("engaged_min_seconds", current["engaged_min_seconds"]), "engaged_min_seconds", 5, 60),
    }
    if validated["behavior_enabled"] and (not validated["measurement_id"] or not (api_secret_provided and api_secret or current["api_secret_configured"])):
        raise ValueError("GA4 browser events need both measurement_id and api_secret.")
    has_saved_read_key = bool(current["read_private_key_configured"])
    has_new_read_key = bool(read_private_key_provided and read_private_key)
    if validated["sync_enabled"] and (
        not validated["property_id"]
        or not validated["read_project_id"]
        or not validated["read_client_email"]
        or not (has_new_read_key or has_saved_read_key)
    ):
        raise ValueError("GA4 sync needs property_id, read_project_id, read_client_email, and read_private_key.")
    validated["api_secret"] = api_secret
    validated["read_private_key"] = read_private_key
    return validated, api_secret_provided or read_private_key_provided


def _validate_matomo_payload(payload: dict) -> tuple[dict, bool]:
    current = get_matomo_settings()
    base_url = str(payload.get("url", current["url"])).strip().rstrip("/")
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be a valid http(s) URL.")

    site_id_xenforo = str(payload.get("site_id_xenforo", current["site_id_xenforo"])).strip()
    site_id_wordpress = str(payload.get("site_id_wordpress", current["site_id_wordpress"])).strip()
    if site_id_xenforo and not site_id_xenforo.isdigit():
        raise ValueError("site_id_xenforo must be a whole number.")
    if site_id_wordpress and not site_id_wordpress.isdigit():
        raise ValueError("site_id_wordpress must be a whole number.")

    token_provided = "token_auth" in payload
    token_auth = str(payload.get("token_auth", "")).strip() if token_provided else None

    validated = {
        "enabled": _coerce_bool(payload.get("enabled", current["enabled"]), "enabled"),
        "url": base_url,
        "site_id_xenforo": site_id_xenforo,
        "site_id_wordpress": site_id_wordpress,
        "sync_enabled": _coerce_bool(payload.get("sync_enabled", current["sync_enabled"]), "sync_enabled"),
        "sync_lookback_days": _coerce_int(payload.get("sync_lookback_days", current["sync_lookback_days"]), "sync_lookback_days", 1, 30),
    }
    if validated["sync_enabled"] and (not validated["url"] or not validated["site_id_xenforo"] or not (token_provided and token_auth or current["token_auth_configured"])):
        raise ValueError("Matomo sync needs url, site_id_xenforo, and token_auth.")
    validated["token_auth"] = token_auth
    return validated, token_provided


def _upsert_setting(key: str, value: str, value_type: str, description: str, *, is_secret: bool = False) -> None:
    AppSetting.objects.update_or_create(
        key=key,
        defaults={
            "value": value,
            "value_type": value_type,
            "category": "analytics",
            "description": description,
            "is_secret": is_secret,
        },
    )


def _ga4_secret() -> str:
    return (_read_setting("analytics.ga4_api_secret", "") or "").strip()


def _ga4_read_private_key() -> str:
    return (_read_setting("analytics.ga4_read_private_key", "") or "").strip()


def _matomo_token() -> str:
    return (_read_setting("analytics.matomo_token_auth", "") or "").strip()


def _sync_analytics_periodic_tasks(*, ga4_config: dict[str, object] | None = None, matomo_config: dict[str, object] | None = None) -> None:
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    if ga4_config is not None:
        hourly_ga4, _ = CrontabSchedule.objects.get_or_create(
            minute="20",
            hour="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone="UTC",
        )
        daily_ga4, _ = CrontabSchedule.objects.get_or_create(
            minute="35",
            hour="2",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone="UTC",
        )
        ga4_enabled = bool(ga4_config["sync_enabled"]) and bool(ga4_config["property_id"]) and bool(ga4_config["read_project_id"]) and bool(ga4_config["read_client_email"]) and bool(ga4_config["read_private_key_configured"])
        PeriodicTask.objects.update_or_create(
            name="analytics-ga4-telemetry-hourly-restatement",
            defaults={
                "task": "analytics.schedule_ga4_telemetry_hourly",
                "crontab": hourly_ga4,
                "queue": "pipeline",
                "enabled": ga4_enabled,
                "description": "Hourly GA4 telemetry reread for the freshest FR-016 days.",
            },
        )
        PeriodicTask.objects.update_or_create(
            name="analytics-ga4-telemetry-daily-catchup",
            defaults={
                "task": "analytics.schedule_ga4_telemetry_daily",
                "crontab": daily_ga4,
                "queue": "pipeline",
                "enabled": ga4_enabled,
                "description": "Daily GA4 telemetry catch-up for delayed FR-016 rows.",
            },
        )

    if matomo_config is not None:
        hourly_matomo, _ = CrontabSchedule.objects.get_or_create(
            minute="10",
            hour="*",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone="UTC",
        )
        daily_matomo, _ = CrontabSchedule.objects.get_or_create(
            minute="25",
            hour="2",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
            timezone="UTC",
        )
        matomo_enabled = bool(matomo_config["enabled"]) and bool(matomo_config["sync_enabled"]) and bool(matomo_config["url"]) and bool(matomo_config["site_id_xenforo"]) and bool(matomo_config["token_auth_configured"])
        PeriodicTask.objects.update_or_create(
            name="analytics-matomo-telemetry-hourly",
            defaults={
                "task": "analytics.schedule_matomo_telemetry_hourly",
                "crontab": hourly_matomo,
                "queue": "pipeline",
                "enabled": matomo_enabled,
                "description": "Hourly Matomo telemetry reread for FR-016.",
            },
        )
        PeriodicTask.objects.update_or_create(
            name="analytics-matomo-telemetry-daily-catchup",
            defaults={
                "task": "analytics.schedule_matomo_telemetry_daily",
                "crontab": daily_matomo,
                "queue": "pipeline",
                "enabled": matomo_enabled,
                "description": "Daily Matomo telemetry catch-up for FR-016.",
            },
        )


class AnalyticsTelemetryOverviewView(APIView):
    """Small overview payload for the analytics page."""

    permission_classes = [AllowAny]

    def get(self, request):
        last_30_days = timezone.now().date() - timedelta(days=30)
        telemetry_rows = SuggestionTelemetryDaily.objects.filter(date__gte=last_30_days)
        coverage_rows = TelemetryCoverageDaily.objects.filter(date__gte=last_30_days)
        totals = telemetry_rows.aggregate(
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
            destination_views=Sum("destination_views"),
            engaged_sessions=Sum("engaged_sessions"),
            conversions=Sum("conversions"),
        )
        return Response(
            {
                "ga4": get_ga4_telemetry_settings(),
                "matomo": get_matomo_settings(),
                "totals_last_30_days": {
                    "impressions": int(totals["impressions"] or 0),
                    "clicks": int(totals["clicks"] or 0),
                    "destination_views": int(totals["destination_views"] or 0),
                    "engaged_sessions": int(totals["engaged_sessions"] or 0),
                    "conversions": int(totals["conversions"] or 0),
                },
                "telemetry_row_count": telemetry_rows.count(),
                "coverage_row_count": coverage_rows.count(),
                "latest_coverage": (
                    coverage_rows.values(
                        "date",
                        "coverage_state",
                        "expected_instrumented_links",
                        "observed_impression_links",
                        "observed_click_links",
                    ).first()
                ),
            }
        )


class AnalyticsTelemetryIntegrationView(APIView):
    """Return copy-ready browser bridge instructions for FR-016 Slice 2."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            build_integration_payload(
                ga4_settings=get_ga4_telemetry_settings(),
                matomo_settings=get_matomo_settings(),
            )
        )


def _queue_sync_run(*, source: str, lookback_days: int) -> AnalyticsSyncRun:
    return AnalyticsSyncRun.objects.create(
        source=source,
        status="pending",
        lookback_days=lookback_days,
    )


class AnalyticsGA4SettingsView(APIView):
    """Get and save GA4 telemetry settings."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_ga4_telemetry_settings())

    def put(self, request):
        try:
            validated, _ = _validate_ga4_payload(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        _upsert_setting("analytics.ga4_behavior_enabled", "true" if validated["behavior_enabled"] else "false", "bool", "Whether browser-side GA4 telemetry events are enabled.")
        _upsert_setting("analytics.ga4_property_id", validated["property_id"], "str", "GA4 property ID used for telemetry reporting.")
        _upsert_setting("analytics.ga4_measurement_id", validated["measurement_id"], "str", "GA4 Measurement ID used by the site event bridge.")
        _upsert_setting("analytics.ga4_read_project_id", validated["read_project_id"], "str", "Google Cloud project ID for GA4 Data API read access.")
        _upsert_setting("analytics.ga4_read_client_email", validated["read_client_email"], "str", "Service-account client email for GA4 Data API read access.")
        _upsert_setting("analytics.ga4_sync_enabled", "true" if validated["sync_enabled"] else "false", "bool", "Whether scheduled GA4 telemetry sync is enabled.")
        _upsert_setting("analytics.ga4_sync_lookback_days", str(validated["sync_lookback_days"]), "int", "How many days each GA4 sync should reread.")
        _upsert_setting("analytics.telemetry_event_schema", validated["event_schema"], "str", "Telemetry event schema name for FR-016.")
        _upsert_setting("analytics.telemetry_geo_granularity", validated["geo_granularity"], "str", "Telemetry geography granularity.")
        _upsert_setting("analytics.telemetry_retention_days", str(validated["retention_days"]), "int", "How long telemetry rows should be kept.")
        _upsert_setting("analytics.telemetry_impression_visible_ratio", str(validated["impression_visible_ratio"]), "float", "Visible ratio needed before counting an impression.")
        _upsert_setting("analytics.telemetry_impression_min_ms", str(validated["impression_min_ms"]), "int", "How long a link must stay visible before it counts as an impression.")
        _upsert_setting("analytics.telemetry_engaged_min_seconds", str(validated["engaged_min_seconds"]), "int", "How many focused seconds count as engaged destination time.")
        if "api_secret" in request.data:
            _upsert_setting("analytics.ga4_api_secret", validated["api_secret"] or "", "str", "GA4 Measurement Protocol API secret.", is_secret=True)
        if "read_private_key" in request.data:
            _upsert_setting("analytics.ga4_read_private_key", validated["read_private_key"] or "", "str", "Service-account private key for GA4 Data API read access.", is_secret=True)
        _sync_analytics_periodic_tasks(ga4_config=get_ga4_telemetry_settings())
        return Response(get_ga4_telemetry_settings())


class AnalyticsGA4TestConnectionView(APIView):
    """Run a lightweight GA4 Measurement Protocol test."""

    permission_classes = [AllowAny]

    def post(self, request):
        measurement_id = str(request.data.get("measurement_id") or _read_setting("analytics.ga4_measurement_id", "") or "").strip().upper()
        api_secret = str(request.data.get("api_secret") or _ga4_secret()).strip()
        if not measurement_id or not api_secret:
            return Response({"status": "not_configured", "message": "Save both Measurement ID and API secret first."}, status=400)

        url = f"https://www.google-analytics.com/debug/mp/collect?measurement_id={measurement_id}&api_secret={api_secret}"
        try:
            response = requests.post(
                url,
                json={
                    "client_id": "xf-internal-linker-test",
                    "events": [
                        {
                            "name": "xfil_connection_test",
                            "params": {
                                "engagement_time_msec": 1,
                                "session_id": "fr016-test",
                            },
                        }
                    ],
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return Response({"status": "error", "message": f"GA4 test failed: {exc}"}, status=502)

        messages = payload.get("validationMessages") or []
        if messages:
            first = messages[0]
            detail = first.get("description") or first.get("fieldPath") or "Google rejected the test event."
            return Response({"status": "error", "message": detail}, status=400)

        return Response({"status": "connected", "message": "GA4 accepted the test event."})


class AnalyticsGA4ReadConnectionView(APIView):
    """Run a lightweight GA4 Data API read test."""

    permission_classes = [AllowAny]

    def post(self, request):
        current = get_ga4_telemetry_settings()
        property_id = str(request.data.get("property_id") or current["property_id"] or "").strip()
        project_id = str(request.data.get("read_project_id") or current["read_project_id"] or "").strip()
        client_email = str(request.data.get("read_client_email") or current["read_client_email"] or "").strip()
        private_key = str(request.data.get("read_private_key") or _ga4_read_private_key()).strip()
        if not property_id or not project_id or not client_email or not private_key:
            return Response(
                {
                    "status": "not_configured",
                    "message": "Save the GA4 property ID, read project ID, client email, and private key first.",
                },
                status=400,
            )

        try:
            service = build_ga4_data_service(
                property_id=property_id,
                project_id=project_id,
                client_email=client_email,
                private_key=private_key,
            )
            test_ga4_data_api_access(service=service, property_id=property_id)
        except Exception as exc:
            return Response({"status": "error", "message": f"GA4 read test failed: {exc}"}, status=502)

        return Response({"status": "connected", "message": "GA4 Data API read access worked."})


class AnalyticsMatomoSettingsView(APIView):
    """Get and save Matomo telemetry settings."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_matomo_settings())

    def put(self, request):
        try:
            validated, token_provided = _validate_matomo_payload(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        _upsert_setting("analytics.matomo_enabled", "true" if validated["enabled"] else "false", "bool", "Whether Matomo telemetry collection is enabled.")
        _upsert_setting("analytics.matomo_url", validated["url"], "str", "Base URL for the Matomo instance.")
        _upsert_setting("analytics.matomo_site_id_xenforo", validated["site_id_xenforo"], "str", "Matomo site ID for XenForo.")
        _upsert_setting("analytics.matomo_site_id_wordpress", validated["site_id_wordpress"], "str", "Matomo site ID for WordPress.")
        _upsert_setting("analytics.matomo_sync_enabled", "true" if validated["sync_enabled"] else "false", "bool", "Whether scheduled Matomo telemetry sync is enabled.")
        _upsert_setting("analytics.matomo_sync_lookback_days", str(validated["sync_lookback_days"]), "int", "How many days each Matomo sync should reread.")
        if token_provided:
            _upsert_setting("analytics.matomo_token_auth", validated["token_auth"] or "", "str", "Matomo API token auth value.", is_secret=True)
        _sync_analytics_periodic_tasks(matomo_config=get_matomo_settings())
        return Response(get_matomo_settings())


class AnalyticsMatomoTestConnectionView(APIView):
    """Run a lightweight Matomo API test."""

    permission_classes = [AllowAny]

    def post(self, request):
        base_url = str(request.data.get("url") or _read_setting("analytics.matomo_url", "") or "").strip().rstrip("/")
        site_id = str(request.data.get("site_id_xenforo") or _read_setting("analytics.matomo_site_id_xenforo", "") or "").strip()
        token_auth = str(request.data.get("token_auth") or _matomo_token()).strip()
        if not base_url or not site_id or not token_auth:
            return Response({"status": "not_configured", "message": "Save the Matomo URL, XenForo site ID, and token first."}, status=400)

        api_url = urljoin(base_url + "/", "?module=API&method=SitesManager.getSiteFromId&format=JSON")
        try:
            response = requests.get(
                api_url,
                params={"idSite": site_id, "token_auth": token_auth},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return Response({"status": "error", "message": f"Matomo test failed: {exc}"}, status=502)

        if isinstance(payload, dict) and payload.get("result") == "error":
            return Response({"status": "error", "message": payload.get("message") or "Matomo rejected the credentials."}, status=400)

        return Response({"status": "connected", "message": "Matomo returned site details successfully."})


class AnalyticsGA4SyncView(APIView):
    """Queue a GA4 telemetry sync run."""

    permission_classes = [AllowAny]

    def post(self, request):
        settings = get_ga4_telemetry_settings()
        sync_run = _queue_sync_run(
            source="ga4",
            lookback_days=int(settings["sync_lookback_days"]),
        )
        task = sync_ga4_telemetry.delay(sync_run.pk)
        return Response(
            {
                "sync_run_id": sync_run.pk,
                "task_id": task.id,
                "source": "ga4",
                "status": "queued",
                "message": "GA4 telemetry sync queued.",
            },
            status=202,
        )


class AnalyticsMatomoSyncView(APIView):
    """Queue a Matomo telemetry sync run."""

    permission_classes = [AllowAny]

    def post(self, request):
        settings = get_matomo_settings()
        sync_run = _queue_sync_run(
            source="matomo",
            lookback_days=int(settings["sync_lookback_days"]),
        )
        task = sync_matomo_telemetry.delay(sync_run.pk)
        return Response(
            {
                "sync_run_id": sync_run.pk,
                "task_id": task.id,
                "source": "matomo",
                "status": "queued",
                "message": "Matomo telemetry sync queued.",
            },
            status=202,
        )
