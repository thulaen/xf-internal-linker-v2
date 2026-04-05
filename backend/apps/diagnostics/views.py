import hmac

from django.conf import settings
from rest_framework import status, viewsets, response, views
from rest_framework.permissions import AllowAny
from rest_framework.decorators import action
from .models import ServiceStatusSnapshot, SystemConflict
from .serializers import ServiceStatusSerializer, SystemConflictSerializer, ErrorLogSerializer
from apps.audit.models import ErrorLog
from .health import run_health_checks, detect_conflicts, get_resource_usage, get_feature_readinessMatrix


class DiagnosticsOverviewView(views.APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        snapshots = ServiceStatusSnapshot.objects.all()
        
        healthy_count = snapshots.filter(state='healthy').count()
        degraded_count = snapshots.filter(state='degraded').count()
        failed_count = snapshots.filter(state='failed').count()
        not_configured_count = snapshots.filter(state='not_configured').count()
        planned_only_count = snapshots.filter(state='planned_only').count()
        
        urgent_issues = SystemConflict.objects.filter(severity__in=['high', 'critical'], resolved=False)[:5]
        urgent_serializer = SystemConflictSerializer(urgent_issues, many=True)
        
        return response.Response({
            "summary": {
                "healthy": healthy_count,
                "degraded": degraded_count,
                "failed": failed_count,
                "not_configured": not_configured_count,
                "planned_only": planned_only_count,
            },
            "top_urgent_issues": urgent_serializer.data,
        })


class ServiceStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ServiceStatusSnapshot.objects.all()
    serializer_class = ServiceStatusSerializer

    @action(detail=False, methods=['post'])
    def refresh(self, request):
        results = run_health_checks()
        return response.Response(results)


class ConflictViewSet(viewsets.ModelViewSet):
    queryset = SystemConflict.objects.all()
    serializer_class = SystemConflictSerializer

    @action(detail=False, methods=['post'])
    def detect(self, request):
        conflicts = detect_conflicts()
        return response.Response(conflicts)


class FeatureReadinessView(views.APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        matrix = get_feature_readinessMatrix()
        return response.Response(matrix)


class ResourceUsageView(views.APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        metrics = get_resource_usage()
        return response.Response(metrics)


class SystemErrorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ErrorLog.objects.all().order_by('-created_at')
    serializer_class = ErrorLogSerializer

    @action(detail=True, methods=['post'])
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

        if task_name == "pipeline.monthly_r_auto_tune":
            from apps.pipeline.tasks import monthly_r_auto_tune

            result = monthly_r_auto_tune.run()
            return response.Response(
                {
                    "status": "completed",
                    "task": task_name,
                    "periodic_task_name": periodic_task_name,
                    "result": result,
                },
                status=status.HTTP_200_OK,
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
