import logging

from django.db import connection
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
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


class HealthDiskView(APIView):
    """GET /api/health/disk/ — database and embedding size estimates."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        db_size_mb = 0
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_database_size(current_database()) / (1024 * 1024)"
                )
                row = cursor.fetchone()
                if row:
                    db_size_mb = row[0]
        except Exception:
            logger.debug("Could not query database size, defaulting to 0")

        # Estimate embedding size from content item count * avg vector size
        embeddings_size_mb = 0
        try:
            from apps.content.models import ContentItem

            count = ContentItem.objects.filter(embedding__isnull=False).count()
            # Each embedding is 1024 floats * 4 bytes = ~4 KB
            embeddings_size_mb = round(count * 4 / 1024, 1)
        except Exception:
            logger.debug(
                "ContentItem model not available, skipping embeddings size estimate"
            )

        return Response(
            {
                "db_size_mb": round(db_size_mb, 1),
                "embeddings_size_mb": embeddings_size_mb,
                "items_count": count if "count" in dir() else 0,
            }
        )


class HealthGpuView(APIView):
    """GET /api/health/gpu/ — GPU temperature, VRAM usage, utilization."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            pynvml.nvmlShutdown()

            return Response(
                {
                    "temp_c": temp,
                    "vram_total_mb": round(mem_info.total / (1024 * 1024)),
                    "vram_used_mb": round(mem_info.used / (1024 * 1024)),
                    "utilization_pct": util.gpu,
                    "available": True,
                }
            )
        except Exception:
            logger.debug(
                "pynvml not available or GPU not detected, returning unavailable status"
            )
            return Response(
                {
                    "temp_c": None,
                    "vram_total_mb": None,
                    "vram_used_mb": None,
                    "utilization_pct": None,
                    "available": False,
                }
            )
