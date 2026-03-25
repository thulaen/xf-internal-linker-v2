"""
Core views — health check, appearance settings, dashboard, and site-asset endpoints.

GET    /api/health/             → {"status": "ok", "version": "2.0.0"}
GET    /api/settings/appearance/ → full appearance config JSON
PUT    /api/settings/appearance/ → merge-update appearance config, returns updated config
POST   /api/settings/logo/      → upload logo image, returns {"logo_url": "..."}
DELETE /api/settings/logo/      → remove logo, clears logoUrl in config
POST   /api/settings/favicon/   → upload favicon image, returns {"favicon_url": "..."}
DELETE /api/settings/favicon/   → remove favicon, clears faviconUrl in config
GET    /api/dashboard/           → aggregated stats for the dashboard
"""

import json
import math
import os
import uuid
from urllib.parse import urlparse

from django.conf import settings as django_settings
from django.http import JsonResponse
from django.views import View
from rest_framework.response import Response
from rest_framework.views import APIView


DEFAULT_APPEARANCE = {
    "primaryColor": "#1a73e8",
    "accentColor": "#f4b400",
    "fontSize": "medium",
    "layoutWidth": "standard",
    "sidebarWidth": "standard",
    "density": "comfortable",
    "headerBg": "#0b57d0",
    "siteName": "XF Internal Linker",
    "showScrollToTop": True,
    "footerText": "XF Internal Linker V2",
    "showFooter": True,
    "footerBg": "#f8f9fa",
    "logoUrl": "",
    "faviconUrl": "",
    "presets": [],
}

DEFAULT_SILO_SETTINGS = {
    "mode": "disabled",
    "same_silo_boost": 0.0,
    "cross_silo_penalty": 0.0,
}

DEFAULT_WORDPRESS_SETTINGS = {
    "base_url": "",
    "username": "",
    "sync_enabled": False,
    "sync_hour": 3,
    "sync_minute": 0,
}

DEFAULT_WEIGHTED_AUTHORITY_SETTINGS = {
    "ranking_weight": 0.2,
    "position_bias": 0.5,
    "empty_anchor_factor": 0.6,
    "bare_url_factor": 0.35,
    "weak_context_factor": 0.75,
    "isolated_context_factor": 0.45,
}

# Allowed MIME types for site asset uploads
_LOGO_ALLOWED = frozenset({"image/png", "image/svg+xml", "image/webp", "image/jpeg"})
_FAVICON_ALLOWED = frozenset({
    "image/png", "image/svg+xml",
    "image/x-icon", "image/vnd.microsoft.icon",
})
_ASSET_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def _get_app_setting_value(key: str, default: str | None = None) -> str | None:
    from apps.core.models import AppSetting

    setting = AppSetting.objects.filter(key=key).first()
    if setting is None:
        return default
    return setting.value


def get_silo_settings() -> dict[str, float | str]:
    """Load persisted silo settings with defensive defaults."""
    mode = _get_app_setting_value("silo.mode", DEFAULT_SILO_SETTINGS["mode"]) or DEFAULT_SILO_SETTINGS["mode"]
    if mode not in {"disabled", "prefer_same_silo", "strict_same_silo"}:
        mode = DEFAULT_SILO_SETTINGS["mode"]

    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            return float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    return {
        "mode": mode,
        "same_silo_boost": _read_float("silo.same_silo_boost", DEFAULT_SILO_SETTINGS["same_silo_boost"]),
        "cross_silo_penalty": _read_float("silo.cross_silo_penalty", DEFAULT_SILO_SETTINGS["cross_silo_penalty"]),
    }


def _validate_silo_settings(payload: dict) -> dict[str, float | str]:
    mode = payload.get("mode", DEFAULT_SILO_SETTINGS["mode"])
    if mode not in {"disabled", "prefer_same_silo", "strict_same_silo"}:
        raise ValueError("mode must be one of disabled, prefer_same_silo, strict_same_silo.")

    def _coerce_float(key: str) -> float:
        value = payload.get(key, DEFAULT_SILO_SETTINGS[key])
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc

    same_silo_boost = _coerce_float("same_silo_boost")
    cross_silo_penalty = _coerce_float("cross_silo_penalty")
    if same_silo_boost < 0:
        raise ValueError("same_silo_boost must be >= 0.")
    if cross_silo_penalty < 0:
        raise ValueError("cross_silo_penalty must be >= 0.")

    return {
        "mode": mode,
        "same_silo_boost": same_silo_boost,
        "cross_silo_penalty": cross_silo_penalty,
    }


def get_wordpress_settings() -> dict[str, object]:
    """Load persisted WordPress sync settings with environment fallbacks."""
    base_url = (_get_app_setting_value("wordpress.base_url", django_settings.WORDPRESS_BASE_URL) or "").strip().rstrip("/")
    username = (_get_app_setting_value("wordpress.username", django_settings.WORDPRESS_USERNAME) or "").strip()
    app_password = _get_app_setting_value("wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD) or ""

    def _read_int(key: str, default: int) -> int:
        raw = _get_app_setting_value(key)
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    sync_enabled = (_get_app_setting_value("wordpress.sync_enabled") or "").strip().lower() in {"1", "true", "yes", "on"}

    return {
        "base_url": base_url,
        "username": username,
        "app_password_configured": bool(app_password.strip()),
        "sync_enabled": sync_enabled,
        "sync_hour": _read_int("wordpress.sync_hour", DEFAULT_WORDPRESS_SETTINGS["sync_hour"]),
        "sync_minute": _read_int("wordpress.sync_minute", DEFAULT_WORDPRESS_SETTINGS["sync_minute"]),
    }


def get_wordpress_runtime_config() -> dict[str, str]:
    """Return WordPress connection settings including the stored secret."""
    return {
        "base_url": (_get_app_setting_value("wordpress.base_url", django_settings.WORDPRESS_BASE_URL) or "").strip().rstrip("/"),
        "username": (_get_app_setting_value("wordpress.username", django_settings.WORDPRESS_USERNAME) or "").strip(),
        "app_password": (_get_app_setting_value("wordpress.app_password", django_settings.WORDPRESS_APP_PASSWORD) or "").strip(),
    }


def get_weighted_authority_settings() -> dict[str, float]:
    """Load persisted weighted-authority settings with defensive defaults."""
    settings = _read_weighted_authority_settings()
    try:
        return _validate_weighted_authority_settings(
            settings,
            current=dict(DEFAULT_WEIGHTED_AUTHORITY_SETTINGS),
        )
    except ValueError:
        return dict(DEFAULT_WEIGHTED_AUTHORITY_SETTINGS)


def _read_weighted_authority_settings() -> dict[str, float]:
    """Read weighted-authority settings from AppSetting without applying bounds."""
    def _read_float(key: str, default: float) -> float:
        raw = _get_app_setting_value(key)
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value):
            return default
        return value

    return {
        "ranking_weight": _read_float("weighted_authority.ranking_weight", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["ranking_weight"]),
        "position_bias": _read_float("weighted_authority.position_bias", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["position_bias"]),
        "empty_anchor_factor": _read_float("weighted_authority.empty_anchor_factor", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["empty_anchor_factor"]),
        "bare_url_factor": _read_float("weighted_authority.bare_url_factor", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["bare_url_factor"]),
        "weak_context_factor": _read_float("weighted_authority.weak_context_factor", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["weak_context_factor"]),
        "isolated_context_factor": _read_float("weighted_authority.isolated_context_factor", DEFAULT_WEIGHTED_AUTHORITY_SETTINGS["isolated_context_factor"]),
    }


def _validate_wordpress_settings(payload: dict) -> dict[str, object]:
    current = get_wordpress_settings()

    base_url = str(payload.get("base_url", current["base_url"])).strip().rstrip("/")
    username = str(payload.get("username", current["username"])).strip()

    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be a valid http(s) URL.")

    app_password_provided = "app_password" in payload
    app_password = None
    if app_password_provided:
        app_password = str(payload.get("app_password", "")).strip()

    effective_has_password = bool(current["app_password_configured"])
    if app_password_provided:
        effective_has_password = bool(app_password)

    def _coerce_bool(value: object, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _coerce_int(key: str, minimum: int, maximum: int) -> int:
        raw = payload.get(key, current[key])
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer.") from exc
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")
        return value

    sync_enabled = _coerce_bool(payload.get("sync_enabled"), bool(current["sync_enabled"]))
    sync_hour = _coerce_int("sync_hour", 0, 23)
    sync_minute = _coerce_int("sync_minute", 0, 59)

    if username and not effective_has_password:
        raise ValueError("Application Password is required when a WordPress username is configured.")
    if effective_has_password and not username:
        raise ValueError("username is required when an Application Password is configured.")
    if sync_enabled and not base_url:
        raise ValueError("base_url is required when scheduled WordPress sync is enabled.")

    return {
        "base_url": base_url,
        "username": username,
        "app_password": app_password,
        "app_password_provided": app_password_provided,
        "app_password_configured": effective_has_password,
        "sync_enabled": sync_enabled,
        "sync_hour": sync_hour,
        "sync_minute": sync_minute,
    }


def _validate_weighted_authority_settings(
    payload: dict,
    *,
    current: dict[str, float] | None = None,
) -> dict[str, float]:
    current = current or _read_weighted_authority_settings()

    def _coerce_float(key: str) -> float:
        value = payload.get(key, current[key])
        try:
            coerced = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(coerced):
            raise ValueError(f"{key} must be finite.")
        return coerced

    validated = {
        "ranking_weight": _coerce_float("ranking_weight"),
        "position_bias": _coerce_float("position_bias"),
        "empty_anchor_factor": _coerce_float("empty_anchor_factor"),
        "bare_url_factor": _coerce_float("bare_url_factor"),
        "weak_context_factor": _coerce_float("weak_context_factor"),
        "isolated_context_factor": _coerce_float("isolated_context_factor"),
    }

    bounds = {
        "ranking_weight": (0.0, 0.25),
        "position_bias": (0.0, 1.0),
        "empty_anchor_factor": (0.1, 1.0),
        "bare_url_factor": (0.1, 1.0),
        "weak_context_factor": (0.1, 1.0),
        "isolated_context_factor": (0.1, 1.0),
    }
    for key, (minimum, maximum) in bounds.items():
        value = validated[key]
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")

    if validated["isolated_context_factor"] > validated["weak_context_factor"]:
        raise ValueError("isolated_context_factor must be <= weak_context_factor.")
    if validated["weak_context_factor"] > 1.0:
        raise ValueError("weak_context_factor must be <= 1.0.")
    if validated["bare_url_factor"] > 1.0:
        raise ValueError("bare_url_factor must be <= 1.0.")

    return validated


def _sync_wordpress_periodic_task(config: dict[str, object]) -> None:
    """Keep the Celery Beat schedule aligned with the saved WordPress sync settings."""
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute=str(config["sync_minute"]),
        hour=str(config["sync_hour"]),
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    PeriodicTask.objects.update_or_create(
        name="wordpress-content-sync",
        defaults={
            "task": "pipeline.import_content",
            "crontab": schedule,
            "kwargs": json.dumps({"source": "wp", "mode": "full"}),
            "queue": "pipeline",
            "enabled": bool(config["sync_enabled"]) and bool(config["base_url"]),
            "description": "Scheduled WordPress content sync for cross-link indexing.",
        },
    )


class HealthCheckView(View):
    """
    Simple health check endpoint.
    Used by Docker Compose and load balancers to verify the backend is alive.
    """

    def get(self, request):
        """Return a simple JSON response confirming the backend is running."""
        return JsonResponse({"status": "ok", "version": "2.0.0"})


class AppearanceSettingsView(APIView):
    """
    GET  /api/settings/appearance/ — returns current appearance config (or defaults)
    PUT  /api/settings/appearance/ — merge-updates the config, returns updated config
    """

    def _get_config(self) -> dict:
        from apps.core.models import AppSetting
        try:
            setting = AppSetting.objects.get(key="appearance.config")
            stored = json.loads(setting.value)
        except AppSetting.DoesNotExist:
            stored = {}
        # Merge stored values over defaults.  Keys that are not in
        # DEFAULT_APPEARANCE are silently dropped — this cleans up legacy
        # keys such as "theme" that were removed from the schema.
        result = dict(DEFAULT_APPEARANCE)
        for k in DEFAULT_APPEARANCE:
            if k in stored:
                result[k] = stored[k]
        return result

    def get(self, request):
        return Response(self._get_config())

    def put(self, request):
        from apps.core.models import AppSetting
        current = self._get_config()
        # Shallow merge — client sends only the keys it wants to change
        for k, v in request.data.items():
            if k in DEFAULT_APPEARANCE:
                current[k] = v
        AppSetting.objects.update_or_create(
            key="appearance.config",
            defaults={
                "value": json.dumps(current),
                "value_type": "json",
                "category": "appearance",
                "description": "Theme customizer appearance configuration (managed by UI).",
                "is_secret": False,
            },
        )
        return Response(current)


class SiloSettingsView(APIView):
    """
    GET  /api/settings/silos/ - returns persisted silo-ranking configuration
    PUT  /api/settings/silos/ - validates and persists silo-ranking configuration
    """

    def get(self, request):
        return Response(get_silo_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_silo_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "silo.mode": {
                "value": validated["mode"],
                "value_type": "str",
                "description": "Topical silo enforcement mode for the suggestion pipeline.",
            },
            "silo.same_silo_boost": {
                "value": str(validated["same_silo_boost"]),
                "value_type": "float",
                "description": "Score bonus applied to same-silo candidates in prefer_same_silo mode.",
            },
            "silo.cross_silo_penalty": {
                "value": str(validated["cross_silo_penalty"]),
                "value_type": "float",
                "description": "Score penalty applied to cross-silo candidates in prefer_same_silo mode.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class WeightedAuthoritySettingsView(APIView):
    """
    GET  /api/settings/weighted-authority/ - returns March 2026 PageRank settings
    PUT  /api/settings/weighted-authority/ - validates and persists those settings
    """

    def get(self, request):
        return Response(get_weighted_authority_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_weighted_authority_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "weighted_authority.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "description": "Ranking weight applied to the normalized March 2026 PageRank signal.",
            },
            "weighted_authority.position_bias": {
                "value": str(validated["position_bias"]),
                "description": "How much later links are down-weighted within a source page.",
            },
            "weighted_authority.empty_anchor_factor": {
                "value": str(validated["empty_anchor_factor"]),
                "description": "Multiplier applied when a non-bare link has blank anchor text.",
            },
            "weighted_authority.bare_url_factor": {
                "value": str(validated["bare_url_factor"]),
                "description": "Multiplier applied to naked URL links.",
            },
            "weighted_authority.weak_context_factor": {
                "value": str(validated["weak_context_factor"]),
                "description": "Multiplier applied to links with prose on only one side.",
            },
            "weighted_authority.isolated_context_factor": {
                "value": str(validated["isolated_context_factor"]),
                "description": "Multiplier applied to isolated or list-like links.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": "float",
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class WeightedAuthorityRecalculateView(APIView):
    """POST /api/settings/weighted-authority/recalculate/ - recalculate March 2026 PageRank."""

    def post(self, request):
        from apps.pipeline.tasks import recalculate_weighted_authority

        job_id = str(uuid.uuid4())
        recalculate_weighted_authority.delay(job_id=job_id)
        return Response({"job_id": job_id}, status=202)


class WordPressSettingsView(APIView):
    """
    GET  /api/settings/wordpress/ - returns saved WordPress sync settings
    PUT  /api/settings/wordpress/ - validates and persists WordPress sync settings
    """

    def get(self, request):
        return Response(get_wordpress_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        try:
            validated = _validate_wordpress_settings(request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "wordpress.base_url": {
                "value": str(validated["base_url"]),
                "value_type": "str",
                "description": "Base URL for the read-only WordPress REST API.",
                "category": "sync",
                "is_secret": False,
            },
            "wordpress.username": {
                "value": str(validated["username"]),
                "value_type": "str",
                "description": "WordPress username used for Application Password authentication.",
                "category": "api",
                "is_secret": False,
            },
            "wordpress.sync_enabled": {
                "value": "true" if validated["sync_enabled"] else "false",
                "value_type": "bool",
                "description": "Whether scheduled WordPress sync is enabled via Celery Beat.",
                "category": "sync",
                "is_secret": False,
            },
            "wordpress.sync_hour": {
                "value": str(validated["sync_hour"]),
                "value_type": "int",
                "description": "UTC hour for the scheduled WordPress sync.",
                "category": "sync",
                "is_secret": False,
            },
            "wordpress.sync_minute": {
                "value": str(validated["sync_minute"]),
                "value_type": "int",
                "description": "UTC minute for the scheduled WordPress sync.",
                "category": "sync",
                "is_secret": False,
            },
        }
        if validated["app_password_provided"]:
            rows["wordpress.app_password"] = {
                "value": str(validated["app_password"] or ""),
                "value_type": "str",
                "description": "WordPress Application Password for private-content reads.",
                "category": "api",
                "is_secret": True,
            }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": row["category"],
                    "description": row["description"],
                    "is_secret": row["is_secret"],
                },
            )

        _sync_wordpress_periodic_task(validated)
        return Response(get_wordpress_settings())


class WordPressSyncRunView(APIView):
    """POST /api/sync/wordpress/run/ - enqueue a manual WordPress sync job."""

    def post(self, request):
        from django.utils import timezone

        from apps.pipeline.tasks import import_content
        from apps.sync.models import SyncJob

        config = get_wordpress_settings()
        if not config["base_url"]:
            return Response(
                {"detail": "Configure a WordPress base URL before starting a sync."},
                status=400,
            )

        job = SyncJob.objects.create(
            source="wp",
            mode="full",
            status="pending",
            message="Queued WordPress sync.",
            started_at=timezone.now(),
        )

        import_content.delay(
            mode="full",
            source="wp",
            job_id=str(job.job_id),
        )

        return Response(
            {
                "job_id": str(job.job_id),
                "source": "wp",
                "mode": "full",
            },
            status=202,
        )


def _save_appearance_key(key: str, value) -> None:
    """Persist a single key into the appearance config AppSetting blob."""
    from apps.core.models import AppSetting
    try:
        setting = AppSetting.objects.get(key="appearance.config")
        stored = json.loads(setting.value)
    except AppSetting.DoesNotExist:
        stored = {}
    stored[key] = value
    AppSetting.objects.update_or_create(
        key="appearance.config",
        defaults={
            "value": json.dumps(stored),
            "value_type": "json",
            "category": "appearance",
            "description": "Theme customizer appearance configuration (managed by UI).",
            "is_secret": False,
        },
    )


class _SiteAssetUploadView(APIView):
    """
    Base class for logo and favicon upload views.

    Subclasses set:
        asset_key      — the key in DEFAULT_APPEARANCE (e.g. 'logoUrl')
        allowed_types  — frozenset of permitted MIME types
        url_field      — the key returned in the JSON response (e.g. 'logo_url')
        subfolder      — directory inside MEDIA_ROOT/site-assets/ (e.g. 'logos')
    """

    asset_key: str = ""
    allowed_types: frozenset = frozenset()
    url_field: str = ""
    subfolder: str = ""

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"error": "No file uploaded. Use field name 'file'."}, status=400)

        # Size check
        if upload.size > _ASSET_MAX_BYTES:
            return Response({"error": "File exceeds 2 MB limit."}, status=400)

        # MIME-type check (uses the browser-reported content type)
        if upload.content_type not in self.allowed_types:
            return Response(
                {
                    "error": (
                        f"Unsupported file type '{upload.content_type}'. "
                        f"Allowed: {', '.join(sorted(self.allowed_types))}"
                    )
                },
                status=400,
            )

        # Derive safe extension from MIME type
        ext_map = {
            "image/png": ".png",
            "image/svg+xml": ".svg",
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
            "image/x-icon": ".ico",
            "image/vnd.microsoft.icon": ".ico",
        }
        ext = ext_map.get(upload.content_type, ".bin")

        # Build destination path using UUID filename — never use the original name
        dest_dir = django_settings.MEDIA_ROOT / "site-assets" / self.subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4()}{ext}"
        dest_path = dest_dir / filename

        with open(dest_path, "wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)

        asset_url = f"{django_settings.MEDIA_URL}site-assets/{self.subfolder}/{filename}"
        _save_appearance_key(self.asset_key, asset_url)

        return Response({self.url_field: asset_url}, status=201)

    def delete(self, request):
        _save_appearance_key(self.asset_key, "")
        return Response(status=204)


class LogoUploadView(_SiteAssetUploadView):
    """POST /api/settings/logo/ — upload site logo (PNG, SVG, WEBP, JPEG ≤ 2 MB)."""

    asset_key = "logoUrl"
    allowed_types = _LOGO_ALLOWED
    url_field = "logo_url"
    subfolder = "logos"


class FaviconUploadView(_SiteAssetUploadView):
    """POST /api/settings/favicon/ — upload site favicon (PNG, SVG, ICO ≤ 2 MB)."""

    asset_key = "faviconUrl"
    allowed_types = _FAVICON_ALLOWED
    url_field = "favicon_url"
    subfolder = "favicons"


class DashboardView(APIView):
    """
    GET /api/dashboard/

    Returns aggregated stats for the dashboard:
    - suggestion counts by status
    - total content items
    - last completed sync job
    - recent pipeline runs (last 5)
    - recent import jobs (last 5)
    """

    def get(self, request):
        from apps.suggestions.models import Suggestion, PipelineRun
        from apps.content.models import ContentItem
        from apps.sync.models import SyncJob
        from apps.graph.models import BrokenLink
        from django.db.models import Count

        # Suggestion counts by status
        status_rows = (
            Suggestion.objects.values("status")
            .annotate(count=Count("pk"))
        )
        suggestion_counts = {row["status"]: row["count"] for row in status_rows}

        # Total content items
        content_count = ContentItem.objects.count()

        open_broken_links = BrokenLink.objects.filter(status="open").count()

        # Last completed sync
        last_sync = (
            SyncJob.objects.filter(status="completed")
            .values("completed_at", "source", "mode", "items_synced")
            .order_by("-completed_at")
            .first()
        )

        # Recent pipeline runs (last 5)
        pipeline_runs = list(
            PipelineRun.objects.values(
                "run_id", "run_state", "rerun_mode",
                "suggestions_created", "destinations_processed",
                "duration_seconds", "created_at",
            ).order_by("-created_at")[:5]
        )
        for run in pipeline_runs:
            run["run_id"] = str(run["run_id"])
            if run["created_at"]:
                run["created_at"] = run["created_at"].isoformat()
            ds = run.pop("duration_seconds")
            if ds is not None:
                minutes, seconds = divmod(int(ds), 60)
                run["duration_display"] = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            else:
                run["duration_display"] = None

        # Recent import jobs (last 5)
        recent_imports = list(
            SyncJob.objects.values(
                "job_id", "status", "source", "mode",
                "items_synced", "created_at", "completed_at",
            ).order_by("-created_at")[:5]
        )
        for job in recent_imports:
            job["job_id"] = str(job["job_id"])
            if job["created_at"]:
                job["created_at"] = job["created_at"].isoformat()
            if job["completed_at"]:
                job["completed_at"] = job["completed_at"].isoformat()

        return Response({
            "suggestion_counts": {
                "pending":  suggestion_counts.get("pending", 0),
                "approved": suggestion_counts.get("approved", 0),
                "rejected": suggestion_counts.get("rejected", 0),
                "applied":  suggestion_counts.get("applied", 0),
                "total":    sum(suggestion_counts.values()),
            },
            "content_count": content_count,
            "open_broken_links": open_broken_links,
            "last_sync": last_sync,
            "pipeline_runs": pipeline_runs,
            "recent_imports": recent_imports,
        })
