"""Celery tasks for benchmark execution."""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(time_limit=1800, soft_time_limit=1700)
def run_all_benchmarks(run_id: int | None = None, trigger: str = "scheduled"):
    """Execute all benchmarks (C++, Python, C#) and store results."""
    from .models import BenchmarkResult, BenchmarkRun
    from .services.runner import (
        classify_results,
        run_cpp_benchmarks,
        run_python_benchmarks,
    )

    if run_id:
        run = BenchmarkRun.objects.get(pk=run_id)
    else:
        run = BenchmarkRun.objects.create(trigger=trigger)

    logger.info("Starting benchmark run #%d (trigger=%s)", run.pk, run.trigger)

    all_results = []
    try:
        cpp_results = run_cpp_benchmarks(run)
        all_results.extend(cpp_results)
        logger.info("C++ benchmarks: %d results", len(cpp_results))

        py_results = run_python_benchmarks(run)
        all_results.extend(py_results)
        logger.info("Python benchmarks: %d results", len(py_results))

        classify_results(all_results)
        BenchmarkResult.objects.bulk_create(all_results)

        fast_count = sum(1 for r in all_results if r.status == "fast")
        ok_count = sum(1 for r in all_results if r.status == "ok")
        slow_count = sum(1 for r in all_results if r.status == "slow")

        run.summary_json = {
            "total": len(all_results),
            "fast": fast_count,
            "ok": ok_count,
            "slow": slow_count,
            "languages": {
                "cpp": sum(1 for r in all_results if r.language == "cpp"),
                "python": sum(1 for r in all_results if r.language == "python"),
                "csharp": sum(1 for r in all_results if r.language == "csharp"),
            },
        }
        run.status = "completed"
        run.finished_at = timezone.now()
        run.save()
        logger.info(
            "Benchmark run #%d completed: %d fast, %d ok, %d slow",
            run.pk, fast_count, ok_count, slow_count,
        )
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = timezone.now()
        run.save()
        logger.exception("Benchmark run #%d failed", run.pk)
        raise
