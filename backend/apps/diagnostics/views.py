import hmac

from django.conf import settings

_BYTES_PER_KIB = 1024.0  # bytes per kibibyte
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from rest_framework import status, viewsets, response, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from .models import ServiceStatusSnapshot, SystemConflict
from .serializers import (
    ServiceStatusSerializer,
    SystemConflictSerializer,
    ErrorLogSerializer,
)
from apps.audit.models import ErrorLog
from apps.core.models import AppSetting
from .health import (
    run_health_checks,
    detect_conflicts,
    get_resource_usage,
    get_feature_readinessMatrix,
    check_native_scoring,
)
from .signal_registry import SIGNALS


class DiagnosticsOverviewView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        snapshots = ServiceStatusSnapshot.objects.all()

        healthy_count = snapshots.filter(state="healthy").count()
        degraded_count = snapshots.filter(state="degraded").count()
        failed_count = snapshots.filter(state="failed").count()
        not_configured_count = snapshots.filter(state="not_configured").count()
        planned_only_count = snapshots.filter(state="planned_only").count()

        urgent_issues = SystemConflict.objects.filter(
            severity__in=["high", "critical"], resolved=False
        )[:5]
        urgent_serializer = SystemConflictSerializer(urgent_issues, many=True)

        return response.Response(
            {
                "summary": {
                    "healthy": healthy_count,
                    "degraded": degraded_count,
                    "failed": failed_count,
                    "not_configured": not_configured_count,
                    "planned_only": planned_only_count,
                },
                "top_urgent_issues": urgent_serializer.data,
            }
        )


class ServiceStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ServiceStatusSnapshot.objects.all()
    serializer_class = ServiceStatusSerializer
    pagination_class = None

    @action(detail=False, methods=["post"])
    def refresh(self, request):
        results = run_health_checks()
        return response.Response(results)


class ConflictViewSet(viewsets.ModelViewSet):
    queryset = SystemConflict.objects.all()
    serializer_class = SystemConflictSerializer
    pagination_class = None

    @action(detail=False, methods=["post"])
    def detect(self, request):
        conflicts = detect_conflicts()
        return response.Response(conflicts)


class FeatureReadinessView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        matrix = get_feature_readinessMatrix()
        return response.Response(matrix)


class ResourceUsageView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        metrics = get_resource_usage()
        return response.Response(metrics)


class SystemErrorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ErrorLog.objects.all().order_by("-created_at")
    serializer_class = ErrorLogSerializer
    pagination_class = None

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        error = self.get_object()
        error.acknowledged = True
        error.save()
        return response.Response({"status": "acknowledged"})


class SchedulerDispatchView(views.APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        configured_token = getattr(settings, "SCHEDULER_CONTROL_TOKEN", "")
        request_token = request.headers.get("X-Scheduler-Token", "")

        if not configured_token:
            return response.Response(
                {
                    "detail": "Scheduler control token is missing, so Django cannot trust scheduler-triggered dispatch.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not hmac.compare_digest(configured_token, request_token):
            return response.Response(
                {
                    "detail": "Scheduler control token did not match.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        task_name = str(request.data.get("task") or "").strip()
        kwargs = request.data.get("kwargs") or {}
        periodic_task_name = str(request.data.get("periodic_task_name") or "").strip()

        if not isinstance(kwargs, dict):
            return response.Response(
                {"detail": "Scheduler kwargs must be a JSON object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if task_name == "pipeline.import_content":
            from apps.pipeline.tasks import dispatch_import_content

            result = dispatch_import_content(
                scope_ids=kwargs.get("scope_ids"),
                mode=str(kwargs.get("mode") or "full"),
                source=str(kwargs.get("source") or "api"),
                file_path=kwargs.get("file_path"),
                job_id=kwargs.get("job_id"),
                force_reembed=bool(kwargs.get("force_reembed") or False),
            )
            return response.Response(
                {
                    "status": "queued",
                    "task": task_name,
                    "periodic_task_name": periodic_task_name,
                    **result,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        if task_name == "pipeline.nightly_data_retention":
            from apps.pipeline.tasks import nightly_data_retention

            result = nightly_data_retention.run()
            return response.Response(
                {
                    "status": "completed",
                    "task": task_name,
                    "periodic_task_name": periodic_task_name,
                    "result": result,
                },
                status=status.HTTP_200_OK,
            )

        if task_name == "pipeline.cleanup_stuck_sync_jobs":
            from apps.pipeline.tasks import cleanup_stuck_sync_jobs

            result = cleanup_stuck_sync_jobs.run()
            return response.Response(
                {
                    "status": "completed",
                    "task": task_name,
                    "periodic_task_name": periodic_task_name,
                    "result": result,
                },
                status=status.HTTP_200_OK,
            )

        return response.Response(
            {
                "detail": (
                    f"Scheduler task '{task_name}' is not supported by the Django control plane yet. "
                    "Add an explicit dispatcher before letting the C# scheduler own it."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class WeightDiagnosticsView(views.APIView):
    """
    FR-028: Algorithm Weight Diagnostics.
    Provides a read-only view of all 23 ranking and value model signals,
    their current weights, storage usage, and C++ acceleration status.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Fetch current settings/weights
        settings = {s.key: s.value for s in AppSetting.objects.all()}

        # 2. Get C++ status
        _state, _expl, _step, native_metadata = check_native_scoring()
        cpp_module_map = {
            m["module"]: m for m in native_metadata.get("module_statuses", [])
        }

        # 3. Get recent error counts per area (last 24h)
        yesterday = timezone.now() - timedelta(hours=24)
        error_counts = {}
        # Simple heuristic: map signal keywords to job_type or step
        logs = ErrorLog.objects.filter(created_at__gte=yesterday, acknowledged=False)
        for log in logs:
            key = f"{log.job_type}:{log.step}".lower()
            error_counts[key] = error_counts.get(key, 0) + 1

        # 4. Gather storage stats for referenced tables
        table_stats = self._get_table_stats()

        # 5. Build final payload
        signal_data = []
        for sig in SIGNALS:
            # Resolve weight
            weight_val = (
                settings.get(sig.weight_key, "0.0") if sig.weight_key else "N/A"
            )
            try:
                weight_display = float(weight_val) if weight_val != "N/A" else 0.0
            except ValueError:
                weight_display = weight_val

            # Resolve C++ status
            cpp_active = False
            cpp_status = "Not Supported"
            if sig.cpp_kernel:
                mod_name = sig.cpp_kernel.split(".")[0]
                mod_info = cpp_module_map.get(mod_name)
                if mod_info:
                    cpp_active = mod_info.get("state") == "healthy"
                    cpp_status = (
                        "Active (C++)" if cpp_active else "Degraded (Python Fallback)"
                    )
                else:
                    cpp_status = "Available (Not Loaded)"

            # Resolve storage
            # sig.table_name might contain multiple tables or extra info, take first word as table name
            raw_table = sig.table_name.split(" ")[0].lower()
            stats = table_stats.get(raw_table, {"rows": 0, "size_bytes": 0})

            # Resolve errors
            # Look for signal ID or job_type matches in error_counts
            err_count = 0
            for err_key, count in error_counts.items():
                if sig.id.lower() in err_key or (
                    sig.cpp_kernel and sig.cpp_kernel.split(".")[0].lower() in err_key
                ):
                    err_count += count

            signal_data.append(
                {
                    "id": sig.id,
                    "name": sig.name,
                    "type": sig.type,
                    "description": sig.description,
                    "weight": weight_display,
                    "cpp_acceleration": {
                        "active": cpp_active,
                        "status_label": cpp_status,
                        "kernel": sig.cpp_kernel,
                    },
                    "storage": {
                        "table": raw_table,
                        "row_count": stats["rows"],
                        "size_bytes": stats["size_bytes"],
                        "size_human": self._human_size(stats["size_bytes"]),
                    },
                    "health": {
                        "status": "healthy" if err_count == 0 else "degraded",
                        "recent_errors": err_count,
                    },
                }
            )

        return response.Response(
            {
                "signals": signal_data,
                "summary": {
                    "total_signals": len(SIGNALS),
                    "cpp_accelerated_count": sum(
                        1 for s in signal_data if s["cpp_acceleration"]["active"]
                    ),
                    "healthy_count": sum(
                        1 for s in signal_data if s["health"]["status"] == "healthy"
                    ),
                    "last_refreshed": timezone.now(),
                },
            }
        )

    def _get_table_stats(self):
        """Fetch row counts and disk usage for core algorithm tables."""
        tables = [
            "content_contentitem",
            "content_sentence",
            "graph_existinglink",
            "analytics_searchmetric",
            "analytics_suggestiontelemetrydaily",
            "cooccurrence_sessioncooccurrencepair",
            "graph_clickdistance",
            "audit_errorlog",
        ]
        stats = {}
        with connection.cursor() as cursor:
            for table in tables:
                try:
                    # Get approximate row count and total size including indexes
                    cursor.execute(
                        """
                        SELECT 
                            (reltuples)::bigint AS row_count,
                            pg_total_relation_size(quote_ident(relname)) AS total_bytes
                        FROM pg_class
                        WHERE relname = %s;
                    """,
                        [table],
                    )
                    row = cursor.fetchone()
                    if row:
                        stats[table] = {"rows": row[0], "size_bytes": row[1]}
                    else:
                        stats[table] = {"rows": 0, "size_bytes": 0}
                except Exception:
                    stats[table] = {"rows": 0, "size_bytes": 0}
        return stats

    def _human_size(self, bytes_val):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_val < _BYTES_PER_KIB:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= _BYTES_PER_KIB
        return f"{bytes_val:.1f} PB"
