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

GA4_DEFAULTS = {
    "behavior_enabled": False,
    "property_id": "",
    "measurement_id": "",
    "api_secret_configured": False,
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
    sync = _latest_sync("ga4")
    status = "not_configured"
    message = "Fill in the GA4 fields and test the connection."
    if measurement_id and api_secret:
        status = "saved"
        message = "Credentials are saved. Run Test Connection to confirm they work."
    if sync and sync["status"] == "completed":
        status = "connected"
        message = "GA4 synced successfully the last time it ran."
    elif sync and sync["status"] == "failed":
        status = "error"
        message = sync["error_message"] or "The last GA4 sync failed."

    return {
        "behavior_enabled": _read_bool("analytics.ga4_behavior_enabled", GA4_DEFAULTS["behavior_enabled"]),
        "property_id": property_id,
        "measurement_id": measurement_id,
        "api_secret_configured": bool(api_secret),
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
    if property_id and not property_id.isdigit():
        raise ValueError("property_id must be numbers only.")
    if measurement_id and not measurement_id.startswith("G-"):
        raise ValueError("measurement_id must start with G-.")

    api_secret_provided = "api_secret" in payload
    api_secret = str(payload.get("api_secret", "")).strip() if api_secret_provided else None

    geo_granularity = str(payload.get("geo_granularity", current["geo_granularity"])).strip()
    if geo_granularity not in {"none", "country", "country_region"}:
        raise ValueError("geo_granularity must be none, country, or country_region.")

    event_schema = str(payload.get("event_schema", current["event_schema"])).strip() or GA4_DEFAULTS["event_schema"]

    validated = {
        "behavior_enabled": _coerce_bool(payload.get("behavior_enabled", current["behavior_enabled"]), "behavior_enabled"),
        "property_id": property_id,
        "measurement_id": measurement_id,
        "sync_enabled": _coerce_bool(payload.get("sync_enabled", current["sync_enabled"]), "sync_enabled"),
        "sync_lookback_days": _coerce_int(payload.get("sync_lookback_days", current["sync_lookback_days"]), "sync_lookback_days", 1, 30),
        "event_schema": event_schema,
        "geo_granularity": geo_granularity,
        "retention_days": _coerce_int(payload.get("retention_days", current["retention_days"]), "retention_days", 1, 800),
        "impression_visible_ratio": _coerce_float(payload.get("impression_visible_ratio", current["impression_visible_ratio"]), "impression_visible_ratio", 0.25, 1.0),
        "impression_min_ms": _coerce_int(payload.get("impression_min_ms", current["impression_min_ms"]), "impression_min_ms", 250, 5000),
        "engaged_min_seconds": _coerce_int(payload.get("engaged_min_seconds", current["engaged_min_seconds"]), "engaged_min_seconds", 5, 60),
    }
    if validated["sync_enabled"] and (not validated["measurement_id"] or not (api_secret_provided and api_secret or current["api_secret_configured"])):
        raise ValueError("GA4 sync needs both measurement_id and api_secret.")
    validated["api_secret"] = api_secret
    return validated, api_secret_provided


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


def _matomo_token() -> str:
    return (_read_setting("analytics.matomo_token_auth", "") or "").strip()


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
            validated, api_secret_provided = _validate_ga4_payload(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        _upsert_setting("analytics.ga4_behavior_enabled", "true" if validated["behavior_enabled"] else "false", "bool", "Whether browser-side GA4 telemetry events are enabled.")
        _upsert_setting("analytics.ga4_property_id", validated["property_id"], "str", "GA4 property ID used for telemetry reporting.")
        _upsert_setting("analytics.ga4_measurement_id", validated["measurement_id"], "str", "GA4 Measurement ID used by the site event bridge.")
        _upsert_setting("analytics.ga4_sync_enabled", "true" if validated["sync_enabled"] else "false", "bool", "Whether scheduled GA4 telemetry sync is enabled.")
        _upsert_setting("analytics.ga4_sync_lookback_days", str(validated["sync_lookback_days"]), "int", "How many days each GA4 sync should reread.")
        _upsert_setting("analytics.telemetry_event_schema", validated["event_schema"], "str", "Telemetry event schema name for FR-016.")
        _upsert_setting("analytics.telemetry_geo_granularity", validated["geo_granularity"], "str", "Telemetry geography granularity.")
        _upsert_setting("analytics.telemetry_retention_days", str(validated["retention_days"]), "int", "How long telemetry rows should be kept.")
        _upsert_setting("analytics.telemetry_impression_visible_ratio", str(validated["impression_visible_ratio"]), "float", "Visible ratio needed before counting an impression.")
        _upsert_setting("analytics.telemetry_impression_min_ms", str(validated["impression_min_ms"]), "int", "How long a link must stay visible before it counts as an impression.")
        _upsert_setting("analytics.telemetry_engaged_min_seconds", str(validated["engaged_min_seconds"]), "int", "How many focused seconds count as engaged destination time.")
        if api_secret_provided:
            _upsert_setting("analytics.ga4_api_secret", validated["api_secret"] or "", "str", "GA4 Measurement Protocol API secret.", is_secret=True)
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
