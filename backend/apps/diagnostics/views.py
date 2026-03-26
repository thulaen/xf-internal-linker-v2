from rest_framework import viewsets, response, views
from rest_framework.decorators import action
from .models import ServiceStatusSnapshot, SystemConflict
from .serializers import ServiceStatusSerializer, SystemConflictSerializer, ErrorLogSerializer
from apps.audit.models import ErrorLog
from .health import run_health_checks, detect_conflicts, get_resource_usage, get_feature_readinessMatrix


class DiagnosticsOverviewView(views.APIView):
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
    def get(self, request):
        matrix = get_feature_readinessMatrix()
        return response.Response(matrix)


class ResourceUsageView(views.APIView):
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
