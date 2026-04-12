import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .models import BenchmarkResult, BenchmarkRun
from .serializers import (
    BenchmarkRunListSerializer,
    BenchmarkRunSerializer,
)
from .services.reporter import generate_report

logger = logging.getLogger(__name__)


class BenchmarkViewSet(GenericViewSet):
    """API for benchmark runs, results, trends, and manual triggers."""

    queryset = BenchmarkRun.objects.all()

    def list(self, request):
        """GET /api/benchmarks/ — list all runs."""
        runs = self.get_queryset()[:50]
        serializer = BenchmarkRunListSerializer(runs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """GET /api/benchmarks/{id}/ — single run with all results."""
        run = self.get_object()
        serializer = BenchmarkRunSerializer(run)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def latest(self, request):
        """GET /api/benchmarks/latest/ — most recent completed run."""
        run = (
            BenchmarkRun.objects.filter(status="completed")
            .order_by("-started_at")
            .first()
        )
        if not run:
            return Response(None, status=status.HTTP_200_OK)
        serializer = BenchmarkRunSerializer(run)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def trigger(self, request):
        """POST /api/benchmarks/trigger/ — start a manual benchmark run."""
        from .tasks import run_all_benchmarks

        run = BenchmarkRun.objects.create(trigger="manual")
        run_all_benchmarks.delay(run.pk)
        return Response(
            {"id": run.pk, "status": "running"},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """GET /api/benchmarks/{id}/report/ — AI-readable text report."""
        run = self.get_object()
        if run.status != "completed":
            return Response(
                {"detail": "Run is not yet completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        text = generate_report(run)
        return Response({"report": text}, content_type="application/json")

    @action(detail=False, methods=["get"])
    def trends(self, request):
        """GET /api/benchmarks/trends/ — last 30 days of results (medium size)."""
        cutoff = timezone.now() - timedelta(days=30)
        runs = BenchmarkRun.objects.filter(
            status="completed", started_at__gte=cutoff
        ).values_list("pk", flat=True)

        results = (
            BenchmarkResult.objects.filter(run_id__in=runs, input_size="medium")
            .select_related("run")
            .values(
                "run__started_at",
                "language",
                "extension",
                "function_name",
                "mean_ns",
                "status",
            )
            .order_by("run__started_at")
        )

        trends = [
            {
                "date": r["run__started_at"].date().isoformat(),
                "language": r["language"],
                "function": f"{r['extension']}.{r['function_name']}",
                "mean_ns": r["mean_ns"],
                "status": r["status"],
            }
            for r in results
        ]
        return Response(trends)
