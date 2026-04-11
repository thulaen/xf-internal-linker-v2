import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ServiceHealthRecord
from .serializers import ServiceHealthRecordSerializer
from .services import HealthCheckRegistry, perform_health_check
from .tasks import run_all_health_checks

logger = logging.getLogger(__name__)


class HealthStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for viewing and triggering system health checks.
    """

    queryset = ServiceHealthRecord.objects.all().order_by("status", "service_key")
    serializer_class = ServiceHealthRecordSerializer
    pagination_class = None
    lookup_field = "service_key"

    def list(self, request, *args, **kwargs):
        """
        Return all health records, auto-seeding any registered checker that
        has no DB row yet.  This makes the /health page show every service on
        first load without requiring a manual "check all" trigger.

        The seeding step is best-effort: a checker that crashes during seeding
        is logged but never allowed to break the list response.
        """
        registered_keys = set(HealthCheckRegistry.get_checkers().keys())
        existing_keys = set(
            ServiceHealthRecord.objects.filter(
                service_key__in=registered_keys
            ).values_list("service_key", flat=True)
        )
        missing_keys = registered_keys - existing_keys
        for key in missing_keys:
            try:
                perform_health_check(key)
            except Exception:
                logger.exception("Auto-seed failed for health checker: %s", key)
        return super().list(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="check-all")
    def check_all(self, request):
        """Immediately trigger a system-wide health check."""
        results = run_all_health_checks()
        return Response({"message": "Health check triggered", "results": results})

    @action(detail=True, methods=["post"], url_path="check")
    def check_single(self, request, service_key=None):
        """Trigger a health check for a specific service."""
        try:
            record = perform_health_check(service_key)
            serializer = self.get_serializer(record)
            return Response(serializer.data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": f"Failed to check health: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Return a high-level aggregate health status."""
        records = ServiceHealthRecord.objects.all()
        total = records.count()
        degraded = records.filter(
            status__in=[
                ServiceHealthRecord.STATUS_ERROR,
                ServiceHealthRecord.STATUS_DOWN,
                ServiceHealthRecord.STATUS_STALE,
            ]
        ).count()

        system_status = "healthy"
        if degraded > 0:
            system_status = "degraded"
        if records.filter(status=ServiceHealthRecord.STATUS_DOWN).exists():
            system_status = "critical"

        return Response(
            {
                "system_status": system_status,
                "total_services": total,
                "degraded_count": degraded,
                "last_check_at": records.order_by("-last_check_at")
                .first()
                .last_check_at
                if total > 0
                else None,
            }
        )
