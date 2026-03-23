"""
Core views — health check endpoint only.

GET /api/health/  →  {"status": "ok", "version": "2.0.0"}
"""

from django.http import JsonResponse
from django.views import View


class HealthCheckView(View):
    """
    Simple health check endpoint.
    Used by Docker Compose and load balancers to verify the backend is alive.
    """

    def get(self, request):
        """Return a simple JSON response confirming the backend is running."""
        return JsonResponse({"status": "ok", "version": "2.0.0"})
