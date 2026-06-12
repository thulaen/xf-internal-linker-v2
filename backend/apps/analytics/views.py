"""Analytics views for FR-016 settings, connection tests, and overview data."""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
from django.db.models import Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AppSetting

from .country_filters import BLOCKED_COUNTRY_NAMES, BLOCKED_TELEMETRY_COUNTRY_VALUES
from .gsc_client import build_gsc_service, test_gsc_access
from .integration_snippet import build_integration_payload
from .models import AnalyticsSyncRun, SuggestionTelemetryDaily, TelemetryCoverageDaily
from .tasks import sync_ga4_telemetry, sync_matomo_telemetry
from .ga4_client import build_ga4_data_service, test_ga4_data_api_access

_RETENTION_DAYS_DEFAULT = 400
_RETENTION_DAYS_MAX = 800
_IMPRESSION_MIN_MS_DEFAULT = 1000
_IMPRESSION_MIN_MS_MIN = 250
_IMPRESSION_MIN_MS_MAX = 5000

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
    "retention_days": _RETENTION_DAYS_DEFAULT,
    "impression_visible_ratio": 0.5,
    "impression_min_ms": _IMPRESSION_MIN_MS_DEFAULT,
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


GSC_DEFAULTS = {
    "property_url": "",
    "client_email": "",
    "private_key_configured": False,
    "sync_enabled": False,
    "sync_lookback_days": 14,
}
GSC_MANUAL_BACKFILL_MAX_DAYS = 365
GSC_MANUAL_BACKFILL_SUGGESTED_DAYS = 180


def _sync_sort_key(sync: dict | None) -> tuple[int, str]:
    if sync is None:
        return (0, "")
    stamp = sync.get("completed_at") or sync.get("started_at") or ""
    return (1, str(stamp))


def _google_oauth_refresh_token() -> str:
    return (_read_setting("analytics.google_oauth_refresh_token", "") or "").strip()


def _google_oauth_client_id() -> str:
    return (_read_setting("analytics.google_oauth_client_id", "") or "").strip()


def _google_oauth_client_secret() -> str:
    return (_read_setting("analytics.google_oauth_client_secret", "") or "").strip()


def _read_setting(key: str, default: str | None = None) -> str | None:
    """Group D consolidation (2026-04-28): kept as a thin wrapper that
    preserves the ``None``-on-miss semantics this module's callers rely
    on (``AppSetting.get_str`` returns ``""`` for missing keys, which
    is sometimes — but not always — the same as None)."""
    row = AppSetting.objects.filter(key=key).only("value").first()
    if row is None:
        return default
    return row.value


# Module-local aliases for the new shared classmethods. Keeps existing
# call sites (``_read_bool("foo", True)``) untouched while the cast
# logic moves to the canonical ``AppSetting.get_*`` helpers.
def _read_bool(key: str, default: bool) -> bool:
    return AppSetting.get_bool(key, default)


def _read_int(key: str, default: int) -> int:
    return AppSetting.get_int(key, default)


def _read_float(key: str, default: float) -> float:
    return AppSetting.get_float(key, default)


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


def _frontend_settings_url(request) -> str:
    """Best-effort redirect target for returning to the Angular settings page."""
    saved_origin = (request.session.get("google_oauth_frontend_origin") or "").strip()
    allowed_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", []) or []
    fallback_origin = allowed_origins[0].rstrip("/") if allowed_origins else ""
    candidate = saved_origin or fallback_origin
    parsed = urlparse(candidate)
    if parsed.scheme and parsed.netloc:
        return urljoin(f"{parsed.scheme}://{parsed.netloc}", "/settings")
    return "/settings"


def get_google_oauth_settings() -> dict:
    client_id = _google_oauth_client_id()
    client_secret = _google_oauth_client_secret()
    refresh_token = _google_oauth_refresh_token()
    oauth_connected = bool(client_id and client_secret and refresh_token)
    latest_sync = max(
        [_latest_sync("ga4"), _latest_sync("gsc")],
        key=_sync_sort_key,
    )
    status = (
        "connected"
        if oauth_connected
        else "saved"
        if (client_id or client_secret)
        else "not_configured"
    )
    message = (
        "Connected to Google. This one login can power both GA4 and Search Console."
        if oauth_connected
        else "Google app credentials are saved. Click Sign in with Google once to finish setup."
        if (client_id or client_secret)
        else "Paste the Google OAuth client ID and secret once, then sign in once."
    )
    return {
        "client_id": client_id,
        "client_secret_configured": bool(client_secret),
        "oauth_connected": oauth_connected,
        "status": status,
        "message": message,
        "last_sync": latest_sync,
    }


def _ga4_browser_status(measurement_id: str, api_secret: str) -> tuple[str, str]:
    """Browser-event ``(status, plain-English message)`` for the GA4 settings card."""
    if measurement_id and api_secret:
        return (
            "saved",
            "Browser-event credentials are saved. Run Test Connection to confirm they work.",
        )
    return (
        "not_configured",
        "Fill in the browser-event fields and test the connection.",
    )


def _ga4_read_status(
    *,
    oauth_connected: bool,
    property_id: str,
    read_client_email: str,
    read_private_key: str,
    sync: dict | None,
) -> tuple[str, str]:
    """Read-access ``(status, plain-English message)``. Sync result wins over creds state."""
    if sync and sync["status"] == "completed":
        return (
            "connected",
            "GA4 read sync completed successfully the last time it ran.",
        )
    if sync and sync["status"] == "failed":
        return (
            "error",
            sync["error_message"] or "The last GA4 sync failed.",
        )
    if oauth_connected:
        return (
            "connected",
            "Connected to Google. GA4 read access can reuse this login.",
        )
    if property_id and read_client_email and read_private_key:
        return (
            "saved",
            "Read-access credentials (service account) are saved. "
            "Run Test Read Access to confirm they work.",
        )
    return ("not_configured", "Connect Google once or add a GA4 read key.")


def _read_stripped_setting(key: str, default: str = "") -> str:
    """Read an AppSetting string + strip whitespace + fall back to default."""
    return (_read_setting(key, default) or default).strip()


def _ga4_settings_telemetry_block() -> dict:
    """Return the 12 telemetry config keys (no creds, no statuses, no oauth)."""
    return {
        "behavior_enabled": _read_bool(
            "analytics.ga4_behavior_enabled",
            GA4_DEFAULTS["behavior_enabled"],
        ),
        "sync_enabled": _read_bool(
            "analytics.ga4_sync_enabled",
            GA4_DEFAULTS["sync_enabled"],
        ),
        "sync_lookback_days": _read_int(
            "analytics.ga4_sync_lookback_days",
            GA4_DEFAULTS["sync_lookback_days"],
        ),
        "event_schema": _read_stripped_setting(
            "analytics.telemetry_event_schema",
            GA4_DEFAULTS["event_schema"],
        ),
        "geo_granularity": _read_stripped_setting(
            "analytics.telemetry_geo_granularity",
            GA4_DEFAULTS["geo_granularity"],
        ),
        "retention_days": _read_int(
            "analytics.telemetry_retention_days",
            GA4_DEFAULTS["retention_days"],
        ),
        "impression_visible_ratio": _read_float(
            "analytics.telemetry_impression_visible_ratio",
            GA4_DEFAULTS["impression_visible_ratio"],
        ),
        "impression_min_ms": _read_int(
            "analytics.telemetry_impression_min_ms",
            GA4_DEFAULTS["impression_min_ms"],
        ),
        "engaged_min_seconds": _read_int(
            "analytics.telemetry_engaged_min_seconds",
            GA4_DEFAULTS["engaged_min_seconds"],
        ),
    }


def get_ga4_telemetry_settings() -> dict:
    property_id = _read_stripped_setting("analytics.ga4_property_id")
    measurement_id = _read_stripped_setting("analytics.ga4_measurement_id")
    api_secret = _read_stripped_setting("analytics.ga4_api_secret")
    read_project_id = _read_stripped_setting("analytics.ga4_read_project_id")
    read_client_email = _read_stripped_setting("analytics.ga4_read_client_email")
    read_private_key = _read_stripped_setting("analytics.ga4_read_private_key")
    sync = _latest_sync("ga4")
    oauth_client_id = _google_oauth_client_id()
    oauth_client_secret = _google_oauth_client_secret()
    oauth_connected = bool(
        _google_oauth_refresh_token() and oauth_client_id and oauth_client_secret
    )
    status, message = _ga4_browser_status(measurement_id, api_secret)
    read_status, read_message = _ga4_read_status(
        oauth_connected=oauth_connected,
        property_id=property_id,
        read_client_email=read_client_email,
        read_private_key=read_private_key,
        sync=sync,
    )
    return {
        **_ga4_settings_telemetry_block(),
        "property_id": property_id,
        "measurement_id": measurement_id,
        "api_secret_configured": bool(api_secret),
        "read_project_id": read_project_id,
        "read_client_email": read_client_email,
        "read_private_key_configured": bool(read_private_key),
        "connection_status": status,
        "connection_message": message,
        "read_connection_status": read_status,
        "read_connection_message": read_message,
        "last_sync": sync,
        "oauth_connected": oauth_connected,
        "google_oauth_client_id": oauth_client_id,
        "google_oauth_client_secret_configured": bool(oauth_client_secret),
    }


def _gsc_connection_status(
    *,
    oauth_connected: bool,
    property_url: str,
    client_email: str,
    private_key: str,
    sync: dict | None,
) -> tuple[str, str]:
    """Pick the ``(status, plain-English message)`` for the GSC settings card."""
    if sync and sync["status"] == "completed":
        return (
            "connected",
            "GSC performance sync completed successfully the last time it ran.",
        )
    if sync and sync["status"] == "failed":
        return ("error", sync["error_message"] or "The last GSC sync failed.")
    if oauth_connected:
        if property_url:
            return ("connected", "Connected to Google.")
        return (
            "saved",
            "Connected to Google. Add the Search Console property URL to finish setup.",
        )
    if property_url and client_email and private_key:
        return (
            "saved",
            "GSC credentials (service account) are saved. Run Test Connection to confirm they work.",
        )
    return (
        "not_configured",
        "Connect via Google OAuth or fill in service-account credentials.",
    )


def get_gsc_settings() -> dict:
    property_url = _read_stripped_setting("analytics.gsc_property_url")
    client_email = _read_stripped_setting("analytics.gsc_client_email")
    private_key = _read_stripped_setting("analytics.gsc_private_key")
    sync = _latest_sync("gsc")
    oauth_connected = bool(
        _google_oauth_refresh_token()
        and _google_oauth_client_id()
        and _google_oauth_client_secret()
    )
    status, message = _gsc_connection_status(
        oauth_connected=oauth_connected,
        property_url=property_url,
        client_email=client_email,
        private_key=private_key,
        sync=sync,
    )
    return {
        "ranking_weight": _read_float("analytics.gsc_ranking_weight", 0.05),
        "property_url": property_url,
        "client_email": client_email,
        "private_key_configured": bool(private_key),
        "sync_enabled": _read_bool(
            "analytics.gsc_sync_enabled",
            GSC_DEFAULTS["sync_enabled"],
        ),
        "sync_lookback_days": _read_int(
            "analytics.gsc_sync_lookback_days",
            GSC_DEFAULTS["sync_lookback_days"],
        ),
        "manual_backfill_max_days": GSC_MANUAL_BACKFILL_MAX_DAYS,
        "manual_backfill_suggested_days": GSC_MANUAL_BACKFILL_SUGGESTED_DAYS,
        "excluded_countries": list(BLOCKED_COUNTRY_NAMES),
        "connection_status": status,
        "connection_message": message,
        "last_sync": sync,
        "oauth_connected": oauth_connected,
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
        "site_id_xenforo": (
            _read_setting("analytics.matomo_site_id_xenforo", "") or ""
        ).strip(),
        "site_id_wordpress": (
            _read_setting("analytics.matomo_site_id_wordpress", "") or ""
        ).strip(),
        "token_auth_configured": bool(token_auth),
        "sync_enabled": _read_bool(
            "analytics.matomo_sync_enabled", MATOMO_DEFAULTS["sync_enabled"]
        ),
        "sync_lookback_days": _read_int(
            "analytics.matomo_sync_lookback_days", MATOMO_DEFAULTS["sync_lookback_days"]
        ),
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


def _ga4_extract_identifiers(payload: dict, current: dict) -> dict[str, str]:
    """Pull + normalise the 4 identifier strings; raise on format errors."""
    property_id = str(payload.get("property_id", current["property_id"])).strip()
    measurement_id = (
        str(payload.get("measurement_id", current["measurement_id"])).strip().upper()
    )
    read_project_id = str(
        payload.get("read_project_id", current["read_project_id"])
    ).strip()
    read_client_email = str(
        payload.get("read_client_email", current["read_client_email"])
    ).strip()
    if property_id and not property_id.isdigit():
        raise ValueError("property_id must be numbers only.")
    if measurement_id and not measurement_id.startswith("G-"):
        raise ValueError("measurement_id must start with G-.")
    if read_client_email and "@" not in read_client_email:
        raise ValueError("read_client_email must look like an email address.")
    return {
        "property_id": property_id,
        "measurement_id": measurement_id,
        "read_project_id": read_project_id,
        "read_client_email": read_client_email,
    }


def _ga4_extract_optional_secrets(payload: dict) -> dict:
    """Pull secret + OAuth fields. Each ``*_provided`` flag mirrors operator intent.

    Optional secrets stay ``None`` when not provided so the persist step
    can preserve the existing AppSetting row instead of clobbering it.
    """
    api_secret_provided = "api_secret" in payload
    read_private_key_provided = "read_private_key" in payload
    oauth_client_id_provided = "google_oauth_client_id" in payload
    oauth_client_secret_provided = "google_oauth_client_secret" in payload
    oauth_client_id = str(
        payload.get("google_oauth_client_id", _google_oauth_client_id())
    ).strip()
    if oauth_client_id and ".apps.googleusercontent.com" not in oauth_client_id:
        raise ValueError(
            "google_oauth_client_id must look like a Google OAuth client ID."
        )
    return {
        "api_secret": (
            str(payload.get("api_secret", "")).strip() if api_secret_provided else None
        ),
        "api_secret_provided": api_secret_provided,
        "read_private_key": (
            str(payload.get("read_private_key", "")).strip()
            if read_private_key_provided
            else None
        ),
        "read_private_key_provided": read_private_key_provided,
        "google_oauth_client_id": oauth_client_id,
        "oauth_client_id_provided": oauth_client_id_provided,
        "google_oauth_client_secret": (
            str(payload.get("google_oauth_client_secret", "")).strip()
            if oauth_client_secret_provided
            else None
        ),
        "oauth_client_secret_provided": oauth_client_secret_provided,
    }


def _ga4_build_validated_dict(payload: dict, current: dict, identifiers: dict) -> dict:
    """Assemble the validated dict from coerced enums + bounded numerics."""
    geo_granularity = str(
        payload.get("geo_granularity", current["geo_granularity"])
    ).strip()
    if geo_granularity not in {"none", "country", "country_region"}:
        raise ValueError("geo_granularity must be none, country, or country_region.")
    event_schema = (
        str(payload.get("event_schema", current["event_schema"])).strip()
        or GA4_DEFAULTS["event_schema"]
    )
    return {
        **identifiers,
        "behavior_enabled": _coerce_bool(
            payload.get("behavior_enabled", current["behavior_enabled"]),
            "behavior_enabled",
        ),
        "sync_enabled": _coerce_bool(
            payload.get("sync_enabled", current["sync_enabled"]),
            "sync_enabled",
        ),
        "sync_lookback_days": _coerce_int(
            payload.get("sync_lookback_days", current["sync_lookback_days"]),
            "sync_lookback_days",
            1,
            30,
        ),
        "event_schema": event_schema,
        "geo_granularity": geo_granularity,
        "retention_days": _coerce_int(
            payload.get("retention_days", current["retention_days"]),
            "retention_days",
            1,
            _RETENTION_DAYS_MAX,
        ),
        "impression_visible_ratio": _coerce_float(
            payload.get(
                "impression_visible_ratio",
                current["impression_visible_ratio"],
            ),
            "impression_visible_ratio",
            0.25,
            1.0,
        ),
        "impression_min_ms": _coerce_int(
            payload.get("impression_min_ms", current["impression_min_ms"]),
            "impression_min_ms",
            _IMPRESSION_MIN_MS_MIN,
            _IMPRESSION_MIN_MS_MAX,
        ),
        "engaged_min_seconds": _coerce_int(
            payload.get("engaged_min_seconds", current["engaged_min_seconds"]),
            "engaged_min_seconds",
            5,
            60,
        ),
    }


def _ga4_check_credential_consistency(
    validated: dict,
    current: dict,
    secrets: dict,
) -> None:
    """Cross-field rules: behavior-needs-measurement-id, sync-needs-creds."""
    if validated["behavior_enabled"] and (
        not validated["measurement_id"]
        or not (
            secrets["api_secret_provided"]
            and secrets["api_secret"]
            or current["api_secret_configured"]
        )
    ):
        raise ValueError("GA4 browser events need both measurement_id and api_secret.")
    has_google_login = bool(
        current["oauth_connected"]
        and _google_oauth_refresh_token()
        and secrets["google_oauth_client_id"]
        and (_google_oauth_client_secret() or secrets["google_oauth_client_secret"])
    )
    has_read_key = bool(
        secrets["read_private_key_provided"] and secrets["read_private_key"]
    ) or bool(current["read_private_key_configured"])
    if validated["sync_enabled"] and (
        not validated["property_id"]
        or (
            not has_google_login
            and (
                not validated["read_project_id"]
                or not validated["read_client_email"]
                or not has_read_key
            )
        )
    ):
        raise ValueError(
            "GA4 sync needs property_id plus either Google login or "
            "read_project_id, read_client_email, and read_private_key."
        )


def _validate_ga4_payload(payload: dict) -> tuple[dict, bool]:
    current = get_ga4_telemetry_settings()
    identifiers = _ga4_extract_identifiers(payload, current)
    secrets = _ga4_extract_optional_secrets(payload)
    validated = _ga4_build_validated_dict(payload, current, identifiers)
    _ga4_check_credential_consistency(validated, current, secrets)
    validated["api_secret"] = secrets["api_secret"]
    validated["read_private_key"] = secrets["read_private_key"]
    validated["google_oauth_client_id"] = secrets["google_oauth_client_id"]
    validated["google_oauth_client_secret"] = secrets["google_oauth_client_secret"]
    any_secret_provided = (
        secrets["api_secret_provided"]
        or secrets["read_private_key_provided"]
        or secrets["oauth_client_id_provided"]
        or secrets["oauth_client_secret_provided"]
    )
    return validated, any_secret_provided


def _validate_matomo_payload(payload: dict) -> tuple[dict, bool]:
    current = get_matomo_settings()
    base_url = str(payload.get("url", current["url"])).strip().rstrip("/")
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be a valid http(s) URL.")

    site_id_xenforo = str(
        payload.get("site_id_xenforo", current["site_id_xenforo"])
    ).strip()
    site_id_wordpress = str(
        payload.get("site_id_wordpress", current["site_id_wordpress"])
    ).strip()
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
        "sync_enabled": _coerce_bool(
            payload.get("sync_enabled", current["sync_enabled"]), "sync_enabled"
        ),
        "sync_lookback_days": _coerce_int(
            payload.get("sync_lookback_days", current["sync_lookback_days"]),
            "sync_lookback_days",
            1,
            30,
        ),
    }
    if validated["sync_enabled"] and (
        not validated["url"]
        or not validated["site_id_xenforo"]
        or not (token_provided and token_auth or current["token_auth_configured"])
    ):
        raise ValueError("Matomo sync needs url, site_id_xenforo, and token_auth.")
    validated["token_auth"] = token_auth
    return validated, token_provided


def _check_gsc_sync_credentials_valid(
    validated: dict,
    current: dict,
    private_key_provided: bool,
    private_key: str | None,
) -> None:
    """Cross-field rule: sync needs property_url + (Google login OR service-account creds)."""
    has_google_login = bool(
        current["oauth_connected"]
        and _google_oauth_refresh_token()
        and _google_oauth_client_id()
        and _google_oauth_client_secret()
    )
    if not validated["sync_enabled"]:
        return
    has_service_account_key = bool(private_key_provided and private_key) or bool(
        current["private_key_configured"]
    )
    if not validated["property_url"] or (
        not has_google_login
        and (not validated["client_email"] or not has_service_account_key)
    ):
        raise ValueError(
            "GSC sync needs property_url plus either Google login or "
            "client_email and private_key."
        )


def _validate_gsc_payload(payload: dict) -> tuple[dict, bool]:
    current = get_gsc_settings()
    property_url = (
        str(payload.get("property_url", current["property_url"])).strip().lower()
    )
    client_email = str(payload.get("client_email", current["client_email"])).strip()
    if property_url and not (
        property_url.startswith("http") or property_url.startswith("sc-domain:")
    ):
        raise ValueError(
            "property_url must start with http://, https://, or sc-domain:"
        )
    if client_email and "@" not in client_email:
        raise ValueError("client_email must look like an email address.")
    private_key_provided = "private_key" in payload
    private_key = (
        str(payload.get("private_key", "")).strip() if private_key_provided else None
    )
    validated = {
        "property_url": property_url,
        "client_email": client_email,
        "ranking_weight": _coerce_float(
            payload.get("ranking_weight", current["ranking_weight"]),
            "ranking_weight",
            0.0,
            1.0,
        ),
        "sync_enabled": _coerce_bool(
            payload.get("sync_enabled", current["sync_enabled"]),
            "sync_enabled",
        ),
        "sync_lookback_days": _coerce_int(
            payload.get("sync_lookback_days", current["sync_lookback_days"]),
            "sync_lookback_days",
            1,
            90,
        ),
    }
    _check_gsc_sync_credentials_valid(
        validated,
        current,
        private_key_provided,
        private_key,
    )
    validated["private_key"] = private_key
    return validated, private_key_provided


def _validate_google_oauth_payload(payload: dict) -> tuple[dict[str, str], bool]:
    current = get_google_oauth_settings()
    client_id = str(payload.get("client_id", current["client_id"])).strip()
    secret_provided = "client_secret" in payload
    client_secret = (
        str(payload.get("client_secret", "")).strip() if secret_provided else None
    )
    if client_id and ".apps.googleusercontent.com" not in client_id:
        raise ValueError("client_id must look like a Google OAuth client ID.")
    validated = {
        "client_id": client_id,
        "client_secret": client_secret or "",
    }
    return validated, secret_provided


def _upsert_setting(
    key: str, value: str, value_type: str, description: str, *, is_secret: bool = False
) -> None:
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


def _gsc_private_key() -> str:
    return (_read_setting("analytics.gsc_private_key", "") or "").strip()


def _ensure_daily_crontab(*, minute: str, hour: str):
    """Get-or-create a daily Celery Beat crontab at the given minute/hour (UTC)."""
    from django_celery_beat.models import CrontabSchedule

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    return schedule


def _ensure_hourly_crontab(*, minute: str):
    """Get-or-create an hourly Celery Beat crontab at the given minute (UTC)."""
    return _ensure_daily_crontab(minute=minute, hour="*")


def _upsert_periodic_task(
    name: str, *, task: str, crontab, enabled: bool, description: str
) -> None:
    """Upsert a Celery Beat PeriodicTask row routed through the pipeline queue."""
    from django_celery_beat.models import PeriodicTask

    PeriodicTask.objects.update_or_create(
        name=name,
        defaults={
            "task": task,
            "crontab": crontab,
            "queue": "pipeline",
            "enabled": enabled,
            "description": description,
        },
    )


def _ga4_periodic_enabled(ga4_config: dict[str, object]) -> bool:
    """Truth-table for whether the GA4 periodic tasks should run."""
    return (
        bool(ga4_config["sync_enabled"])
        and bool(ga4_config["property_id"])
        and bool(ga4_config["read_project_id"])
        and bool(ga4_config["read_client_email"])
        and bool(ga4_config["read_private_key_configured"])
    )


def _matomo_periodic_enabled(matomo_config: dict[str, object]) -> bool:
    """Truth-table for whether the Matomo periodic tasks should run."""
    return (
        bool(matomo_config["enabled"])
        and bool(matomo_config["sync_enabled"])
        and bool(matomo_config["url"])
        and bool(matomo_config["site_id_xenforo"])
        and bool(matomo_config["token_auth_configured"])
    )


def _gsc_periodic_enabled(gsc_config: dict[str, object]) -> bool:
    """Truth-table for whether the GSC periodic task should run."""
    return (
        bool(gsc_config["sync_enabled"])
        and bool(gsc_config["property_url"])
        and bool(gsc_config["client_email"])
        and bool(gsc_config["private_key_configured"])
    )


def _sync_ga4_periodic_tasks(ga4_config: dict[str, object]) -> None:
    """Wire the 2 GA4 PeriodicTasks (hourly restatement + daily catch-up)."""
    enabled = _ga4_periodic_enabled(ga4_config)
    _upsert_periodic_task(
        "analytics-ga4-telemetry-hourly-restatement",
        task="analytics.schedule_ga4_telemetry_hourly",
        crontab=_ensure_hourly_crontab(minute="20"),
        enabled=enabled,
        description="Hourly GA4 telemetry reread for the freshest FR-016 days.",
    )
    _upsert_periodic_task(
        "analytics-ga4-telemetry-daily-catchup",
        task="analytics.schedule_ga4_telemetry_daily",
        crontab=_ensure_daily_crontab(minute="35", hour="2"),
        enabled=enabled,
        description="Daily GA4 telemetry catch-up for delayed FR-016 rows.",
    )


def _sync_matomo_periodic_tasks(matomo_config: dict[str, object]) -> None:
    """Wire the 2 Matomo PeriodicTasks (hourly + daily catch-up)."""
    enabled = _matomo_periodic_enabled(matomo_config)
    _upsert_periodic_task(
        "analytics-matomo-telemetry-hourly",
        task="analytics.schedule_matomo_telemetry_hourly",
        crontab=_ensure_hourly_crontab(minute="10"),
        enabled=enabled,
        description="Hourly Matomo telemetry reread for FR-016.",
    )
    _upsert_periodic_task(
        "analytics-matomo-telemetry-daily-catchup",
        task="analytics.schedule_matomo_telemetry_daily",
        crontab=_ensure_daily_crontab(minute="25", hour="2"),
        enabled=enabled,
        description="Daily Matomo telemetry catch-up for FR-016.",
    )


def _sync_gsc_and_spike_periodic_tasks() -> None:
    """Wire the GSC daily sync + traffic-spike-detection PeriodicTasks."""
    _upsert_periodic_task(
        "analytics-gsc-performance-daily",
        task="analytics.sync_gsc_performance_daily",
        crontab=_ensure_daily_crontab(minute="50", hour="2"),
        enabled=_gsc_periodic_enabled(get_gsc_settings()),
        description="Daily GSC search performance sync for FR-017.",
    )
    _upsert_periodic_task(
        "analytics-traffic-spike-detection",
        task="analytics.detect_traffic_spikes",
        crontab=_ensure_daily_crontab(minute="30", hour="4"),
        enabled=True,
        description="Daily momentum-based traffic spike detection for FR-023.",
    )


def _sync_analytics_periodic_tasks(
    *,
    ga4_config: dict[str, object] | None = None,
    matomo_config: dict[str, object] | None = None,
) -> None:
    if ga4_config is not None:
        _sync_ga4_periodic_tasks(ga4_config)
    if matomo_config is not None:
        _sync_matomo_periodic_tasks(matomo_config)
    _sync_gsc_and_spike_periodic_tasks()


def _telemetry_source_filter(request) -> str | None:
    source = str(request.query_params.get("source") or "all").strip().lower()
    if source in {"ga4", "matomo"}:
        return source
    return None


def _telemetry_window_days(
    request, *, default: int = 30, minimum: int = 1, maximum: int = 90
) -> int:
    raw = request.query_params.get("days")
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(min(value, maximum), minimum)


def _telemetry_queryset(request):
    days = _telemetry_window_days(request)
    start_date = timezone.now().date() - timedelta(days=days - 1)
    queryset = SuggestionTelemetryDaily.objects.filter(date__gte=start_date).exclude(
        country__in=BLOCKED_TELEMETRY_COUNTRY_VALUES
    )
    source = _telemetry_source_filter(request)
    if source:
        queryset = queryset.filter(telemetry_source=source)
    return queryset, days, source


def _safe_rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


class AnalyticsTelemetryOverviewView(APIView):
    """Small overview payload for the analytics page."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        last_30_days = timezone.now().date() - timedelta(days=30)
        telemetry_rows = SuggestionTelemetryDaily.objects.filter(
            date__gte=last_30_days
        ).exclude(country__in=BLOCKED_TELEMETRY_COUNTRY_VALUES)
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
                "gsc": get_gsc_settings(),
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


def _summarize_coverage_queryset(queryset) -> dict:
    totals = queryset.aggregate(
        expected_instrumented_links=Sum("expected_instrumented_links"),
        observed_impression_links=Sum("observed_impression_links"),
        observed_click_links=Sum("observed_click_links"),
        attributed_destination_sessions=Sum("attributed_destination_sessions"),
        unattributed_destination_sessions=Sum("unattributed_destination_sessions"),
        duplicate_event_drops=Sum("duplicate_event_drops"),
        missing_metadata_events=Sum("missing_metadata_events"),
        delayed_rows_rewritten=Sum("delayed_rows_rewritten"),
    )
    healthy_days = queryset.filter(coverage_state="healthy").count()
    partial_days = queryset.filter(coverage_state="partial").count()
    degraded_days = queryset.filter(coverage_state="degraded").count()
    latest_row = queryset.values("date", "coverage_state", "event_schema").first()
    expected_links = int(totals["expected_instrumented_links"] or 0)
    observed_impressions = int(totals["observed_impression_links"] or 0)
    observed_clicks = int(totals["observed_click_links"] or 0)
    attributed_sessions = int(totals["attributed_destination_sessions"] or 0)
    unattributed_sessions = int(totals["unattributed_destination_sessions"] or 0)
    total_sessions = attributed_sessions + unattributed_sessions
    return {
        "row_count": queryset.count(),
        "latest_state": latest_row["coverage_state"] if latest_row else "no_data",
        "latest_date": latest_row["date"].isoformat()
        if latest_row and latest_row["date"]
        else None,
        "event_schema": latest_row["event_schema"] if latest_row else "",
        "healthy_days": healthy_days,
        "partial_days": partial_days,
        "degraded_days": degraded_days,
        "expected_instrumented_links": expected_links,
        "observed_impression_links": observed_impressions,
        "observed_click_links": observed_clicks,
        "attributed_destination_sessions": attributed_sessions,
        "unattributed_destination_sessions": unattributed_sessions,
        "duplicate_event_drops": int(totals["duplicate_event_drops"] or 0),
        "missing_metadata_events": int(totals["missing_metadata_events"] or 0),
        "delayed_rows_rewritten": int(totals["delayed_rows_rewritten"] or 0),
        "impression_coverage_rate": _safe_rate(observed_impressions, expected_links),
        "click_coverage_rate": _safe_rate(observed_clicks, expected_links),
        "attribution_rate": _safe_rate(attributed_sessions, total_sessions),
    }


class AnalyticsTelemetryHealthView(APIView):
    """Return simple telemetry-health rollups for the selected time window."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = _telemetry_window_days(request)
        start_date = timezone.now().date() - timedelta(days=days - 1)
        queryset = TelemetryCoverageDaily.objects.filter(date__gte=start_date)
        source_rows = []
        for source in (
            queryset.order_by("source_label")
            .values_list("source_label", flat=True)
            .distinct()
        ):
            source_key = source or "unknown"
            source_rows.append(
                {
                    "source_label": source_key,
                    **_summarize_coverage_queryset(
                        queryset.filter(source_label=source)
                    ),
                }
            )
        return Response(
            {
                "days": days,
                "overall": _summarize_coverage_queryset(queryset),
                "sources": source_rows,
            }
        )


def _label_or_unknown(value: str | None) -> str:
    cleaned = (value or "").strip()
    return cleaned or "Unknown"


class AnalyticsTelemetryBreakdownView(APIView):
    """Return simple device and channel breakdowns for the selected telemetry window."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # DataFusion rewire 2026-06-10: breakdowns come from one SQL
        # pass over a 15-minute Parquet snapshot instead of three live
        # ORM GROUP BY queries per page load (see telemetry_rollups).
        from .telemetry_rollups import breakdown_rows

        days = _telemetry_window_days(request)
        source = _telemetry_source_filter(request)
        return Response(
            {
                "days": days,
                "selected_source": source or "all",
                "device_categories": _format_breakdown_rows(
                    breakdown_rows("device_category", days=days, source=source),
                    "device_category",
                ),
                "channel_groups": _format_breakdown_rows(
                    breakdown_rows(
                        "default_channel_group", days=days, source=source
                    ),
                    "default_channel_group",
                ),
                "countries": _format_breakdown_rows(
                    breakdown_rows("country", days=days, source=source),
                    "country",
                ),
            }
        )


def _format_breakdown_rows(rows, dimension: str) -> list[dict]:
    """Convert aggregated rows into the {label, impressions, clicks, ctr, ...} API shape."""
    return [
        {
            "label": _label_or_unknown(row[dimension]),
            "impressions": int(row["impressions"] or 0),
            "clicks": int(row["clicks"] or 0),
            "engaged_sessions": int(row["engaged_sessions"] or 0),
            "ctr": _safe_rate(row["clicks"] or 0, row["impressions"] or 0),
        }
        for row in rows
    ]


class AnalyticsTelemetryFunnelView(APIView):
    """Return the simple FR-016 funnel for the selected source and time window."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset, days, source = _telemetry_queryset(request)
        totals = queryset.aggregate(
            impressions=Sum("impressions"),
            clicks=Sum("clicks"),
            destination_views=Sum("destination_views"),
            engaged_sessions=Sum("engaged_sessions"),
            conversions=Sum("conversions"),
        )
        by_source_rows = (
            queryset.values("telemetry_source")
            .annotate(
                impressions=Sum("impressions"),
                clicks=Sum("clicks"),
                destination_views=Sum("destination_views"),
                engaged_sessions=Sum("engaged_sessions"),
                conversions=Sum("conversions"),
            )
            .order_by("telemetry_source")
        )
        return Response(
            {
                "days": days,
                "selected_source": source or "all",
                "totals": {
                    "impressions": int(totals["impressions"] or 0),
                    "clicks": int(totals["clicks"] or 0),
                    "destination_views": int(totals["destination_views"] or 0),
                    "engaged_sessions": int(totals["engaged_sessions"] or 0),
                    "conversions": int(totals["conversions"] or 0),
                },
                "by_source": [
                    {
                        "telemetry_source": row["telemetry_source"],
                        "impressions": int(row["impressions"] or 0),
                        "clicks": int(row["clicks"] or 0),
                        "destination_views": int(row["destination_views"] or 0),
                        "engaged_sessions": int(row["engaged_sessions"] or 0),
                        "conversions": int(row["conversions"] or 0),
                    }
                    for row in by_source_rows
                ],
            }
        )


class AnalyticsTelemetryEngagementMixView(APIView):
    """Return the Phase 2 engagement mix for the selected source + time window.

    Surfaces the three new ``SuggestionTelemetryDaily`` columns
    (``quick_exit_sessions``, ``dwell_30s_sessions``, ``dwell_60s_sessions``)
    alongside the existing ``destination_views`` and ``engaged_sessions`` so
    operators can see the dwell-tier distribution per source.

    Rates are computed as ``<tier_count> / destination_views`` via the
    existing ``_safe_rate`` helper (returns 0.0 on zero denominators). Tiers
    are cumulative (a session that reaches 60s also fires the 30s event), so
    the rates are independent tier-reach percentages, not stacked shares.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset, days, source = _telemetry_queryset(request)
        totals = queryset.aggregate(
            destination_views=Sum("destination_views"),
            engaged_sessions=Sum("engaged_sessions"),
            quick_exit_sessions=Sum("quick_exit_sessions"),
            dwell_30s_sessions=Sum("dwell_30s_sessions"),
            dwell_60s_sessions=Sum("dwell_60s_sessions"),
        )
        destination_views = int(totals["destination_views"] or 0)
        engaged_sessions = int(totals["engaged_sessions"] or 0)
        quick_exit_sessions = int(totals["quick_exit_sessions"] or 0)
        dwell_30s_sessions = int(totals["dwell_30s_sessions"] or 0)
        dwell_60s_sessions = int(totals["dwell_60s_sessions"] or 0)

        return Response(
            {
                "days": days,
                "selected_source": source or "all",
                "totals": {
                    "destination_views": destination_views,
                    "engaged_sessions": engaged_sessions,
                    "quick_exit_sessions": quick_exit_sessions,
                    "dwell_30s_sessions": dwell_30s_sessions,
                    "dwell_60s_sessions": dwell_60s_sessions,
                },
                "rates": {
                    "quick_exit_rate": _safe_rate(
                        quick_exit_sessions, destination_views
                    ),
                    "engaged_rate": _safe_rate(engaged_sessions, destination_views),
                    "dwell_30s_rate": _safe_rate(dwell_30s_sessions, destination_views),
                    "dwell_60s_rate": _safe_rate(dwell_60s_sessions, destination_views),
                },
            }
        )


class AnalyticsTelemetryTrendView(APIView):
    """Return a day-by-day telemetry trend for the selected source and time window."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset, days, source = _telemetry_queryset(request)
        rows = (
            queryset.values("date")
            .annotate(
                impressions=Sum("impressions"),
                clicks=Sum("clicks"),
                destination_views=Sum("destination_views"),
                engaged_sessions=Sum("engaged_sessions"),
                conversions=Sum("conversions"),
            )
            .order_by("date")
        )
        items = []
        for row in rows:
            impressions = int(row["impressions"] or 0)
            clicks = int(row["clicks"] or 0)
            destination_views = int(row["destination_views"] or 0)
            engaged_sessions = int(row["engaged_sessions"] or 0)
            conversions = int(row["conversions"] or 0)
            items.append(
                {
                    "date": row["date"].isoformat(),
                    "impressions": impressions,
                    "clicks": clicks,
                    "destination_views": destination_views,
                    "engaged_sessions": engaged_sessions,
                    "conversions": conversions,
                    "ctr": _safe_rate(clicks, impressions),
                    "engagement_rate": _safe_rate(engaged_sessions, destination_views),
                }
            )
        return Response(
            {
                "days": days,
                "selected_source": source or "all",
                "items": items,
            }
        )


class AnalyticsTelemetryTopSuggestionsView(APIView):
    """Return the strongest suggestion rows in the selected telemetry window."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset, days, source = _telemetry_queryset(request)
        order = (request.query_params.get("order") or "clicks").strip().lower()
        if order not in {"clicks", "quick_exit"}:
            order = "clicks"
        grouped = _aggregate_top_suggestions_grouped(queryset)
        rows = _order_top_suggestions_rows(grouped, order)
        return Response(
            {
                "days": days,
                "selected_source": source or "all",
                "items": [_format_top_suggestion_row(row) for row in rows],
            }
        )


_TOP_SUGGESTIONS_LIMIT = 8


def _aggregate_top_suggestions_grouped(queryset):
    """GROUP BY suggestion + telemetry_source with the 7 metric Sum() annotations."""
    return queryset.values(
        "suggestion_id",
        "suggestion__destination_title",
        "suggestion__anchor_phrase",
        "suggestion__status",
        "telemetry_source",
    ).annotate(
        impressions=Sum("impressions"),
        clicks=Sum("clicks"),
        destination_views=Sum("destination_views"),
        engaged_sessions=Sum("engaged_sessions"),
        conversions=Sum("conversions"),
        # Phase 2c — expose the new engagement tiers per suggestion so
        # operators can spot individual bad-match rows (high quick_exit_rate)
        # and standout good-match rows (high dwell_60s_rate).
        quick_exit_sessions=Sum("quick_exit_sessions"),
        dwell_60s_sessions=Sum("dwell_60s_sessions"),
    )


def _order_top_suggestions_rows(grouped, order: str):
    """Apply the per-order sort + top-N slice. Quick-exit needs a derived ratio."""
    if order == "quick_exit":
        from django.db.models import ExpressionWrapper, F, FloatField

        # Sort by the derived quick-exit share of destination views. Filter
        # destination_views > 0 to avoid SQL division-by-zero and to keep
        # impressions-only rows out of the bad-match list.
        return (
            grouped.filter(destination_views__gt=0)
            .annotate(
                _quick_exit_ratio=ExpressionWrapper(
                    F("quick_exit_sessions") * 1.0 / F("destination_views"),
                    output_field=FloatField(),
                ),
            )
            .order_by("-_quick_exit_ratio", "-destination_views", "-clicks")[
                :_TOP_SUGGESTIONS_LIMIT
            ]
        )
    return grouped.order_by("-clicks", "-engaged_sessions", "-impressions")[
        :_TOP_SUGGESTIONS_LIMIT
    ]


def _format_top_suggestion_row(row: dict) -> dict:
    """Convert one aggregated row into the public {suggestion_id, ...} API shape."""
    impressions = int(row["impressions"] or 0)
    clicks = int(row["clicks"] or 0)
    destination_views = int(row["destination_views"] or 0)
    engaged_sessions = int(row["engaged_sessions"] or 0)
    quick_exit_sessions = int(row["quick_exit_sessions"] or 0)
    dwell_60s_sessions = int(row["dwell_60s_sessions"] or 0)
    return {
        "suggestion_id": str(row["suggestion_id"]),
        "telemetry_source": row["telemetry_source"],
        "destination_title": (
            row["suggestion__destination_title"] or "Unknown destination"
        ),
        "anchor_phrase": row["suggestion__anchor_phrase"] or "",
        "status": row["suggestion__status"] or "unknown",
        "impressions": impressions,
        "clicks": clicks,
        "destination_views": destination_views,
        "engaged_sessions": engaged_sessions,
        "conversions": int(row["conversions"] or 0),
        "quick_exit_sessions": quick_exit_sessions,
        "dwell_60s_sessions": dwell_60s_sessions,
        "ctr": _safe_rate(clicks, impressions),
        "engagement_rate": _safe_rate(engaged_sessions, destination_views),
        "quick_exit_rate": _safe_rate(quick_exit_sessions, destination_views),
        "dwell_60s_rate": _safe_rate(dwell_60s_sessions, destination_views),
    }


class AnalyticsTelemetryIntegrationView(APIView):
    """Return copy-ready browser bridge instructions for FR-016 Slice 2."""

    permission_classes = [IsAuthenticated]

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

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_ga4_telemetry_settings())

    def put(self, request):
        try:
            validated, _ = _validate_ga4_payload(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        _persist_ga4_telemetry_settings(validated, request.data)
        _sync_analytics_periodic_tasks(ga4_config=get_ga4_telemetry_settings())
        return Response(get_ga4_telemetry_settings())


def _format_setting_value(value, value_type: str) -> str:
    """Coerce an in-memory value into the on-disk AppSetting string form."""
    if value_type == "bool":
        return "true" if value else "false"
    return str(value)


# (validated_key, setting_key, value_type, description) for GA4 telemetry rows.
# Adding a new GA4 settings row = one entry here, not a new copy of the
# 5-line _upsert_setting block.
_GA4_TELEMETRY_ROW_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (
        "behavior_enabled",
        "analytics.ga4_behavior_enabled",
        "bool",
        "Whether browser-side GA4 telemetry events are enabled.",
    ),
    (
        "property_id",
        "analytics.ga4_property_id",
        "str",
        "GA4 property ID used for telemetry reporting.",
    ),
    (
        "measurement_id",
        "analytics.ga4_measurement_id",
        "str",
        "GA4 Measurement ID used by the site event bridge.",
    ),
    (
        "read_project_id",
        "analytics.ga4_read_project_id",
        "str",
        "Google Cloud project ID for GA4 Data API read access.",
    ),
    (
        "read_client_email",
        "analytics.ga4_read_client_email",
        "str",
        "Service-account client email for GA4 Data API read access.",
    ),
    (
        "sync_enabled",
        "analytics.ga4_sync_enabled",
        "bool",
        "Whether scheduled GA4 telemetry sync is enabled.",
    ),
    (
        "sync_lookback_days",
        "analytics.ga4_sync_lookback_days",
        "int",
        "How many days each GA4 sync should reread.",
    ),
    (
        "event_schema",
        "analytics.telemetry_event_schema",
        "str",
        "Telemetry event schema name for FR-016.",
    ),
    (
        "geo_granularity",
        "analytics.telemetry_geo_granularity",
        "str",
        "Telemetry geography granularity.",
    ),
    (
        "retention_days",
        "analytics.telemetry_retention_days",
        "int",
        "How long telemetry rows should be kept.",
    ),
    (
        "impression_visible_ratio",
        "analytics.telemetry_impression_visible_ratio",
        "float",
        "Visible ratio needed before counting an impression.",
    ),
    (
        "impression_min_ms",
        "analytics.telemetry_impression_min_ms",
        "int",
        "How long a link must stay visible before it counts as an impression.",
    ),
    (
        "engaged_min_seconds",
        "analytics.telemetry_engaged_min_seconds",
        "int",
        "How many focused seconds count as engaged destination time.",
    ),
)

# (validated_key, setting_key, description) for OPTIONAL GA4 secrets.
# Persist only when the operator sent a value, so partial PUTs don't clobber
# existing secrets.
_GA4_OPTIONAL_SECRET_SPEC: tuple[tuple[str, str, str], ...] = (
    ("api_secret", "analytics.ga4_api_secret", "GA4 Measurement Protocol API secret."),
    (
        "read_private_key",
        "analytics.ga4_read_private_key",
        "Service-account private key for GA4 Data API read access.",
    ),
)


def _persist_ga4_telemetry_settings(validated: dict, raw_payload: dict) -> None:
    """Write 13 standard rows + up to 2 optional secret rows for GA4 telemetry."""
    for validated_key, setting_key, value_type, description in _GA4_TELEMETRY_ROW_SPEC:
        _upsert_setting(
            setting_key,
            _format_setting_value(validated[validated_key], value_type),
            value_type,
            description,
        )
    for payload_key, setting_key, description in _GA4_OPTIONAL_SECRET_SPEC:
        if payload_key in raw_payload:
            _upsert_setting(
                setting_key,
                validated[payload_key] or "",
                "str",
                description,
                is_secret=True,
            )


class AnalyticsGoogleOAuthSettingsView(APIView):
    """Get and save the shared Google OAuth app credentials."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_google_oauth_settings())

    def put(self, request):
        try:
            validated, secret_provided = _validate_google_oauth_payload(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        _upsert_setting(
            "analytics.google_oauth_client_id",
            validated["client_id"],
            "str",
            "Google OAuth client ID shared by GA4 and GSC.",
        )
        if secret_provided:
            _upsert_setting(
                "analytics.google_oauth_client_secret",
                validated["client_secret"],
                "str",
                "Google OAuth client secret shared by GA4 and GSC.",
                is_secret=True,
            )
        return Response(get_google_oauth_settings())


class AnalyticsGA4TestConnectionView(APIView):
    """Run a lightweight GA4 Measurement Protocol test."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        measurement_id = (
            str(
                request.data.get("measurement_id")
                or _read_setting("analytics.ga4_measurement_id", "")
                or ""
            )
            .strip()
            .upper()
        )
        api_secret = str(request.data.get("api_secret") or _ga4_secret()).strip()
        if not measurement_id or not api_secret:
            return Response(
                {
                    "status": "not_configured",
                    "message": "Save both Measurement ID and API secret first.",
                },
                status=400,
            )
        return _probe_ga4_browser_endpoint(measurement_id, api_secret)


def _probe_ga4_browser_endpoint(measurement_id: str, api_secret: str) -> Response:
    """POST a debug test event to Google's MP debug endpoint; classify the response."""
    url = (
        "https://www.google-analytics.com/debug/mp/collect"
        f"?measurement_id={measurement_id}&api_secret={api_secret}"
    )
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
        logger.exception("GA4 browser endpoint probe failed")
        return Response(
            {"status": "error", "message": f"GA4 test failed: {exc}"},
            status=502,
        )
    messages = payload.get("validationMessages") or []
    if messages:
        first = messages[0]
        detail = (
            first.get("description")
            or first.get("fieldPath")
            or "Google rejected the test event."
        )
        return Response({"status": "error", "message": detail}, status=400)
    return Response(
        {"status": "connected", "message": "GA4 accepted the test event."},
    )


class AnalyticsGA4ReadConnectionView(APIView):
    """Run a lightweight GA4 Data API read test."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        property_id = str(
            request.data.get("property_id")
            or _read_setting("analytics.ga4_property_id", "")
            or ""
        ).strip()
        try:
            service_or_response = _build_ga4_read_service_or_error_response(
                property_id,
                request.data,
            )
        except Exception as exc:
            logger.exception("GA4 Data API service build failed")
            return Response(
                {"status": "error", "message": f"GA4 read access failed: {exc}"},
                status=502,
            )
        if isinstance(service_or_response, Response):
            return service_or_response
        try:
            test_ga4_data_api_access(
                service=service_or_response,
                property_id=property_id,
            )
        except Exception as exc:
            logger.exception("GA4 Data API read probe failed")
            return Response(
                {"status": "error", "message": f"GA4 read access failed: {exc}"},
                status=502,
            )
        return Response(
            {"status": "connected", "message": "GA4 read access successful."},
        )


def _build_ga4_read_service_or_error_response(property_id: str, data: dict):
    """Build a GA4 Data API service via OAuth (preferred) or service-account creds.

    Returns the service object on success or a 400 ``Response`` to short-circuit.
    """
    refresh_token = _google_oauth_refresh_token()
    client_id = _google_oauth_client_id()
    client_secret = _google_oauth_client_secret()
    if refresh_token and client_id and client_secret:
        return build_ga4_data_service(
            property_id=property_id,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
        )
    project_id = str(
        data.get("read_project_id")
        or _read_setting("analytics.ga4_read_project_id", "")
        or ""
    ).strip()
    client_email = str(
        data.get("read_client_email")
        or _read_setting("analytics.ga4_read_client_email", "")
        or ""
    ).strip()
    private_key = str(data.get("read_private_key") or _ga4_read_private_key()).strip()
    if not property_id or not project_id or not client_email or not private_key:
        return Response(
            {
                "status": "error",
                "message": "Save GA4 read credentials or connect Google account first.",
            },
            status=400,
        )
    return build_ga4_data_service(
        property_id=property_id,
        project_id=project_id,
        client_email=client_email,
        private_key=private_key,
    )


class AnalyticsMatomoSettingsView(APIView):
    """Get and save Matomo telemetry settings."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_matomo_settings())

    def put(self, request):
        try:
            validated, token_provided = _validate_matomo_payload(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        _persist_matomo_settings(validated, token_provided)
        _sync_analytics_periodic_tasks(matomo_config=get_matomo_settings())
        return Response(get_matomo_settings())


_MATOMO_ROW_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (
        "enabled",
        "analytics.matomo_enabled",
        "bool",
        "Whether Matomo telemetry collection is enabled.",
    ),
    ("url", "analytics.matomo_url", "str", "Base URL for the Matomo instance."),
    (
        "site_id_xenforo",
        "analytics.matomo_site_id_xenforo",
        "str",
        "Matomo site ID for XenForo.",
    ),
    (
        "site_id_wordpress",
        "analytics.matomo_site_id_wordpress",
        "str",
        "Matomo site ID for WordPress.",
    ),
    (
        "sync_enabled",
        "analytics.matomo_sync_enabled",
        "bool",
        "Whether scheduled Matomo telemetry sync is enabled.",
    ),
    (
        "sync_lookback_days",
        "analytics.matomo_sync_lookback_days",
        "int",
        "How many days each Matomo sync should reread.",
    ),
)


def _persist_matomo_settings(validated: dict, token_provided: bool) -> None:
    """Persist 6 standard Matomo rows + the optional token (only when supplied)."""
    for validated_key, setting_key, value_type, description in _MATOMO_ROW_SPEC:
        _upsert_setting(
            setting_key,
            _format_setting_value(validated[validated_key], value_type),
            value_type,
            description,
        )
    if token_provided:
        _upsert_setting(
            "analytics.matomo_token_auth",
            validated["token_auth"] or "",
            "str",
            "Matomo API token auth value.",
            is_secret=True,
        )


class AnalyticsMatomoTestConnectionView(APIView):
    """Run a lightweight Matomo API test."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        creds = _resolve_matomo_test_credentials(request.data)
        if not creds["base_url"] or not creds["site_id"] or not creds["token_auth"]:
            return Response(
                {
                    "status": "not_configured",
                    "message": "Save the Matomo URL, XenForo site ID, and token first.",
                },
                status=400,
            )
        return _probe_matomo_endpoint(creds)


def _resolve_matomo_test_credentials(data: dict) -> dict[str, str]:
    """Resolve Matomo test credentials. Precedence: body > AppSetting."""
    return {
        "base_url": (
            str(
                data.get("url") or _read_setting("analytics.matomo_url", "") or "",
            )
            .strip()
            .rstrip("/")
        ),
        "site_id": str(
            data.get("site_id_xenforo")
            or _read_setting("analytics.matomo_site_id_xenforo", "")
            or "",
        ).strip(),
        "token_auth": str(data.get("token_auth") or _matomo_token()).strip(),
    }


def _probe_matomo_endpoint(creds: dict[str, str]) -> Response:
    """Hit Matomo SitesManager.getSiteFromId; classify the response."""
    api_url = urljoin(
        creds["base_url"] + "/",
        "?module=API&method=SitesManager.getSiteFromId&format=JSON",
    )
    try:
        response = requests.get(
            api_url,
            params={"idSite": creds["site_id"], "token_auth": creds["token_auth"]},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.exception("Matomo endpoint probe failed")
        return Response(
            {"status": "error", "message": f"Matomo test failed: {exc}"},
            status=502,
        )
    if isinstance(payload, dict) and payload.get("result") == "error":
        return Response(
            {
                "status": "error",
                "message": payload.get("message") or "Matomo rejected the credentials.",
            },
            status=400,
        )
    return Response(
        {
            "status": "connected",
            "message": "Matomo returned site details successfully.",
        },
    )


class AnalyticsGA4SyncView(APIView):
    """Queue a GA4 telemetry sync run."""

    permission_classes = [IsAuthenticated]

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

    permission_classes = [IsAuthenticated]

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


class AnalyticsGSCSyncView(APIView):
    """Queue a GSC performance sync run."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .tasks import sync_gsc_performance

        settings = get_gsc_settings()
        requested_lookback = request.data.get("lookback_days")
        if requested_lookback in (None, ""):
            lookback_days = int(settings["sync_lookback_days"])
        else:
            try:
                lookback_days = _coerce_int(
                    requested_lookback,
                    "lookback_days",
                    1,
                    GSC_MANUAL_BACKFILL_MAX_DAYS,
                )
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
        sync_run = _queue_sync_run(
            source="gsc",
            lookback_days=lookback_days,
        )
        task = sync_gsc_performance.delay(sync_run.pk)
        return Response(
            {
                "sync_run_id": sync_run.pk,
                "task_id": task.id,
                "source": "gsc",
                "status": "queued",
                "message": f"GSC performance sync queued for {lookback_days} days.",
            },
            status=202,
        )


class AnalyticsTelemetryByVersionView(APIView):
    """Compare performance metrics group by algorithm version."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset, days, source = _telemetry_queryset(request)
        version_rows = (
            queryset.values("algorithm_version_slug")
            .annotate(
                impressions=Sum("impressions"),
                clicks=Sum("clicks"),
                destination_views=Sum("destination_views"),
                engaged_sessions=Sum("engaged_sessions"),
                conversions=Sum("conversions"),
            )
            .order_by("-clicks", "algorithm_version_slug")
        )
        items = []
        for row in version_rows:
            impressions = int(row["impressions"] or 0)
            clicks = int(row["clicks"] or 0)
            destination_views = int(row["destination_views"] or 0)
            engaged_sessions = int(row["engaged_sessions"] or 0)
            conversions = int(row["conversions"] or 0)
            items.append(
                {
                    "version_slug": row["algorithm_version_slug"] or "unknown",
                    "impressions": impressions,
                    "clicks": clicks,
                    "destination_views": destination_views,
                    "engaged_sessions": engaged_sessions,
                    "conversions": conversions,
                    "ctr": _safe_rate(clicks, impressions),
                    "engagement_rate": _safe_rate(engaged_sessions, destination_views),
                    "conversion_rate": _safe_rate(conversions, clicks),
                }
            )
        return Response(
            {
                "days": days,
                "selected_source": source or "all",
                "items": items,
            }
        )


class AnalyticsTelemetryGeoDetailView(APIView):
    """Return a detailed country+region breakdown for the selected telemetry window."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset, days, source = _telemetry_queryset(request)
        # Group by country and region for a deeper look
        rows = (
            queryset.values("country", "region")
            .annotate(
                impressions=Sum("impressions"),
                clicks=Sum("clicks"),
                engaged_sessions=Sum("engaged_sessions"),
                conversions=Sum("conversions"),
            )
            .order_by("-clicks", "-impressions", "country", "region")[:50]
        )
        items = []
        for row in rows:
            items.append(
                {
                    "country": _label_or_unknown(row["country"]),
                    "region": _label_or_unknown(row["region"]),
                    "impressions": int(row["impressions"] or 0),
                    "clicks": int(row["clicks"] or 0),
                    "engaged_sessions": int(row["engaged_sessions"] or 0),
                    "conversions": int(row["conversions"] or 0),
                    "ctr": _safe_rate(row["clicks"] or 0, row["impressions"] or 0),
                }
            )
        return Response(
            {
                "days": days,
                "selected_source": source or "all",
                "items": items,
            }
        )


class AnalyticsGSCSettingsView(APIView):
    """Get and save GSC settings."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_gsc_settings())

    def put(self, request):
        try:
            validated, private_key_provided = _validate_gsc_payload(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        _upsert_setting(
            "analytics.gsc_property_url",
            validated["property_url"],
            "str",
            "Google Search Console property URL (e.g. sc-domain:example.com)",
        )
        _upsert_setting(
            "analytics.gsc_client_email",
            validated["client_email"],
            "str",
            "GSC service account client email.",
        )
        _upsert_setting(
            "analytics.gsc_sync_enabled",
            "true" if validated["sync_enabled"] else "false",
            "bool",
            "Whether GSC performance sync is enabled.",
        )
        _upsert_setting(
            "analytics.gsc_sync_lookback_days",
            str(validated["sync_lookback_days"]),
            "int",
            "GSC sync lookback days.",
        )
        _upsert_setting(
            "analytics.gsc_ranking_weight",
            str(validated["ranking_weight"]),
            "float",
            "GSC search performance ranking weight.",
        )
        if private_key_provided:
            _upsert_setting(
                "analytics.gsc_private_key",
                validated["private_key"] or "",
                "str",
                "GSC service account private key.",
                is_secret=True,
            )
        _sync_analytics_periodic_tasks()
        return Response(get_gsc_settings())


class AnalyticsGSCTestConnectionView(APIView):
    """Test GSC service account access."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        property_url = str(
            request.data.get("property_url")
            or _read_setting("analytics.gsc_property_url", "")
            or ""
        ).strip()
        refresh_token = _google_oauth_refresh_token()
        client_id = _google_oauth_client_id()
        client_secret = _google_oauth_client_secret()

        try:
            if refresh_token and client_id and client_secret:
                service = build_gsc_service(
                    refresh_token=refresh_token,
                    client_id=client_id,
                    client_secret=client_secret,
                )
            else:
                client_email = str(
                    request.data.get("client_email")
                    or _read_setting("analytics.gsc_client_email", "")
                    or ""
                ).strip()
                private_key = str(
                    request.data.get("private_key") or _gsc_private_key()
                ).strip()
                if not property_url or not client_email or not private_key:
                    return Response(
                        {
                            "status": "error",
                            "message": "Save GSC credentials or connect Google account first.",
                        },
                        status=400,
                    )
                service = build_gsc_service(
                    client_email=client_email, private_key=private_key
                )

            test_gsc_access(service, property_url)
        except Exception as exc:
            logger.exception("GSC test access failed")
            return Response(
                {"status": "error", "message": f"GSC connection failed: {exc}"},
                status=502,
            )

        return Response(
            {"status": "connected", "message": "GSC connection successful."}
        )


class AnalyticsSearchImpactListView(APIView):
    """List applied suggestions with GSC impact results."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import GSCImpactSnapshot
        from .serializers import GSCImpactSnapshotSerializer

        window = request.query_params.get("window", "28d")

        # Prefetch suggestion and content item for efficiency
        qs = (
            GSCImpactSnapshot.objects.filter(window_type=window)
            .select_related("suggestion", "suggestion__destination")
            .order_by("-apply_date")
        )

        serializer = GSCImpactSnapshotSerializer(qs, many=True)
        return Response({"items": serializer.data})


class AnalyticsSearchImpactDetailView(APIView):
    """Detailed keyword lift for one suggestion."""

    permission_classes = [IsAuthenticated]

    def get(self, request, suggestion_id):
        from django.shortcuts import get_object_or_404
        from apps.suggestions.models import Suggestion
        from .models import GSCImpactSnapshot
        from .serializers import (
            GSCImpactSnapshotSerializer,
            GSCKeywordImpactSerializer,
            ImpactReportSerializer,
        )

        window = request.query_params.get("window", "28d")
        sug = get_object_or_404(Suggestion, pk=suggestion_id)

        # Get the specific snapshot for the window
        snapshot = GSCImpactSnapshot.objects.filter(
            suggestion=sug, window_type=window
        ).first()
        keywords = sug.keyword_impacts.all().order_by("-lift_percent")[:50]
        impact_reports = sug.impact_reports.all().order_by("-created_at")

        return Response(
            {
                "suggestion_id": sug.suggestion_id,
                "anchor_phrase": sug.anchor_phrase,
                "destination_title": sug.destination_title,
                "applied_at": sug.applied_at,
                "impact": GSCImpactSnapshotSerializer(snapshot).data
                if snapshot
                else None,
                "keywords": GSCKeywordImpactSerializer(keywords, many=True).data,
                "impact_reports": ImpactReportSerializer(
                    impact_reports, many=True
                ).data,
            }
        )


class AnalyticsGoogleOAuthStartView(APIView):
    """
    Generate the Google OAuth authorization URL.
    Requires analytics.google_oauth_client_id and analytics.google_oauth_client_secret to be set.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        client_id = _google_oauth_client_id()
        client_secret = _google_oauth_client_secret()
        if not client_id or not client_secret:
            return Response(
                {
                    "detail": (
                        "Google OAuth Client ID and Secret must be configured "
                        "in settings first."
                    ),
                },
                status=400,
            )
        flow = _build_google_oauth_flow(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=request.build_absolute_uri("/api/analytics/oauth/callback/"),
            scopes=_GOOGLE_OAUTH_SCOPES,
        )
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        # Store state in session for CSRF verification in the callback view.
        request.session["google_oauth_state"] = state
        request.session["google_oauth_frontend_origin"] = (
            request.headers.get("Origin") or ""
        ).strip()
        return Response({"authorization_url": authorization_url})


_GOOGLE_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
)


def _build_google_oauth_flow(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    scopes: tuple | None,
):
    """Construct a google_auth_oauthlib.Flow with the standard XF-internal-linker config."""
    import google_auth_oauthlib.flow

    return google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=list(scopes) if scopes else None,
        redirect_uri=redirect_uri,
    )


class AnalyticsGoogleOAuthCallbackView(APIView):
    """
    Handle the callback from Google OAuth.
    Exchange the code for a refresh token and save it.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.shortcuts import redirect

        frontend_settings_url = _frontend_settings_url(request)
        guard_url = _validate_oauth_callback_inputs(request, frontend_settings_url)
        if guard_url is not None:
            return redirect(guard_url)
        client_id = _google_oauth_client_id()
        client_secret = _google_oauth_client_secret()
        if not client_id or not client_secret:
            return redirect(
                f"{frontend_settings_url}?oauth_error=missing_client_settings",
            )
        return redirect(
            _exchange_oauth_code_and_persist(
                request=request,
                code=request.GET.get("code"),
                client_id=client_id,
                client_secret=client_secret,
                frontend_settings_url=frontend_settings_url,
            )
        )


def _validate_oauth_callback_inputs(request, frontend_settings_url: str) -> str | None:
    """Return an error redirect URL if the callback inputs are invalid, else None."""
    error = request.GET.get("error")
    if error:
        return f"{frontend_settings_url}?oauth_error={error}"
    state = request.GET.get("state")
    code = request.GET.get("code")
    if not state or not code:
        return f"{frontend_settings_url}?oauth_error=missing_params"
    saved_state = request.session.get("google_oauth_state")
    if saved_state and state != saved_state:
        return f"{frontend_settings_url}?oauth_error=invalid_state"
    return None


def _exchange_oauth_code_and_persist(
    *,
    request,
    code: str,
    client_id: str,
    client_secret: str,
    frontend_settings_url: str,
) -> str:
    """Exchange the OAuth code for a refresh token, persist it, return redirect URL."""
    flow = _build_google_oauth_flow(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=request.build_absolute_uri("/api/analytics/oauth/callback/"),
        scopes=None,  # Scopes are already encoded in the auth code.
    )
    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
    except Exception as exc:
        logger.exception("Google OAuth token exchange failed")
        return f"{frontend_settings_url}?oauth_error={exc}"
    if not credentials.refresh_token:
        # prompt="consent" in the start view should always force a fresh token,
        # but a re-authorisation can still skip it; surface as a recoverable error.
        return f"{frontend_settings_url}?oauth_error=no_refresh_token"
    _upsert_setting(
        "analytics.google_oauth_refresh_token",
        credentials.refresh_token,
        "str",
        "Google OAuth Refresh Token for GA4 and GSC access.",
        is_secret=True,
    )
    return f"{frontend_settings_url}?oauth_success=1"


class AnalyticsGoogleOAuthUnlinkView(APIView):
    """Remove the saved Google OAuth refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.core.models import AppSetting

        AppSetting.objects.filter(
            key__in=[
                "analytics.google_oauth_refresh_token",
                "analytics.google_oauth_state",
            ]
        ).delete()
        return Response({"status": "unlinked", "message": "Google account unlinked."})


# ---------------------------------------------------------------------------
# Stage 7 — SEO Proof endpoints
# ---------------------------------------------------------------------------


class ImpactDiaryView(APIView):
    """GET /api/analytics/impacts/ — chronological impact narrative."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import ImpactReport

        reports = ImpactReport.objects.select_related("suggestion").order_by(
            "-created_at"
        )[:50]
        items = []
        for r in reports:
            # RPT-001 Finding 4: stratified attribution model label
            if r.control_match_count >= 3:
                attribution_model = "synthetic_control"
                confidence = "high" if r.is_conclusive else "medium"
            elif r.is_conclusive:
                attribution_model = "site_trend"
                confidence = "medium"
            else:
                attribution_model = "inconclusive"
                confidence = "thin"

            items.append(
                {
                    "suggestion_id": str(r.suggestion_id),
                    "metric_type": r.metric_type,
                    "before_value": r.before_value,
                    "after_value": r.after_value,
                    "delta_percent": round(r.delta_percent, 1),
                    "attribution_model": attribution_model,
                    "confidence": confidence,
                    "is_conclusive": r.is_conclusive,
                    "control_match_count": r.control_match_count,
                    "created_at": r.created_at.isoformat(),
                }
            )
        return Response(items)


class QueryMismatchView(APIView):
    """GET /api/analytics/query-mismatch/ — pages where search intent doesn't match landing page."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import SearchMetric
        from django.db.models import Sum, Avg

        # Find top queries with their landing pages
        top_queries = (
            SearchMetric.objects.filter(source="gsc")
            .values("query", "content_item_id", "content_item__title")
            .annotate(
                total_clicks=Sum("clicks"),
                total_impressions=Sum("impressions"),
                avg_position=Avg("average_position"),
            )
            .order_by("-total_impressions")[:50]
        )

        results = []
        for q in top_queries:
            results.append(
                {
                    "query": q["query"],
                    "landing_page_id": q["content_item_id"],
                    "landing_page_title": q["content_item__title"],
                    "clicks": q["total_clicks"],
                    "impressions": q["total_impressions"],
                    "avg_position": round(q["avg_position"] or 0, 1),
                }
            )

        return Response(results)


class WatchedPageListView(APIView):
    """GET/POST /api/analytics/watched-pages/ — user's watched pages."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import WatchedPage

        pages = WatchedPage.objects.select_related("content_item").all()
        return Response(
            [
                {
                    "id": p.id,
                    "content_item_id": p.content_item_id,
                    "title": p.content_item.title,
                    "url": p.content_item.url,
                    "notes": p.notes,
                    "added_at": p.added_at.isoformat(),
                }
                for p in pages
            ]
        )

    def post(self, request):
        from .models import WatchedPage

        content_item_id = request.data.get("content_item_id")
        notes = request.data.get("notes", "")
        if not content_item_id:
            return Response({"error": "content_item_id is required"}, status=400)

        wp, created = WatchedPage.objects.get_or_create(
            content_item_id=content_item_id,
            defaults={"notes": notes},
        )
        if not created:
            return Response({"error": "Already watching this page"}, status=409)

        return Response(
            {"id": wp.id, "content_item_id": wp.content_item_id}, status=201
        )


class WatchedPageDeleteView(APIView):
    """DELETE /api/analytics/watched-pages/<id>/ — remove a watched page."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        from .models import WatchedPage

        deleted, _ = WatchedPage.objects.filter(pk=pk).delete()
        if not deleted:
            return Response({"error": "Not found"}, status=404)
        return Response(status=204)
