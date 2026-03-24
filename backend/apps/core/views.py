"""
Core views — health check and appearance settings endpoints.

GET  /api/health/             → {"status": "ok", "version": "2.0.0"}
GET  /api/settings/appearance/ → full appearance config JSON
PUT  /api/settings/appearance/ → merge-update appearance config, returns updated config
"""

import json

from django.http import JsonResponse
from django.views import View
from rest_framework.response import Response
from rest_framework.views import APIView


DEFAULT_APPEARANCE = {
    "theme": "light",
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
