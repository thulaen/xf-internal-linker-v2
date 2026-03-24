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
import os
import uuid

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

# Allowed MIME types for site asset uploads
_LOGO_ALLOWED = frozenset({"image/png", "image/svg+xml", "image/webp", "image/jpeg"})
_FAVICON_ALLOWED = frozenset({
    "image/png", "image/svg+xml",
    "image/x-icon", "image/vnd.microsoft.icon",
})
_ASSET_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


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
        from django.db.models import Count

        # Suggestion counts by status
        status_rows = (
            Suggestion.objects.values("status")
            .annotate(count=Count("pk"))
        )
        suggestion_counts = {row["status"]: row["count"] for row in status_rows}

        # Total content items
        content_count = ContentItem.objects.count()

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
            "last_sync": last_sync,
            "pipeline_runs": pipeline_runs,
            "recent_imports": recent_imports,
        })
