"""
Core views — health check, appearance settings, and dashboard endpoints.

GET  /api/health/             → {"status": "ok", "version": "2.0.0"}
GET  /api/settings/appearance/ → full appearance config JSON
PUT  /api/settings/appearance/ → merge-update appearance config, returns updated config
GET  /api/dashboard/           → aggregated stats for the dashboard
"""

import json

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
    "presets": [],
}


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
            return json.loads(setting.value)
        except AppSetting.DoesNotExist:
            return dict(DEFAULT_APPEARANCE)

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
