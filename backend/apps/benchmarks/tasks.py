"""Celery tasks for benchmark execution."""

import logging

from celery import shared_task
from django.utils import timezone

from apps.core.helpers import HelperConstraint

logger = logging.getLogger(__name__)


def _log_caller_diagnostics(self, run_id, trigger):
    """ISS-102 telemetry — logs the caller's pid/hostname/task_id/origin."""
    import os as _os

    request = getattr(self, "request", None)
    logger.info(
        "[run_all_benchmarks-trace] pid=%d hostname=%s task_id=%s parent_id=%s "
        "origin=%s trigger=%s run_id=%s",
        _os.getpid(),
        _os.environ.get("HOSTNAME", "?"),
        getattr(request, "id", "?") if request else "?",
        getattr(request, "parent_id", None) if request else None,
        getattr(request, "origin", "?") if request else "?",
        trigger,
        run_id,
    )


_RECENT_RUN_WINDOW_S = 60


def _detect_storm_skip(self, trigger):
    """ISS-102 idempotency guard. Returns True if another run started in the
    last 60 s — caller should skip + log + return early.

    The 2026-05-08 storm fired 5 runs in 67 s from an unknown source. Even
    with the caller-trace telemetry already in place to identify the source
    on next recurrence, we want to STOP the storm from happening at all.
    A 60-second window is well under the typical run time (~1-3 min) so
    legitimate manual triggers from the UI won't double-fire."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import BenchmarkRun

    cutoff = timezone.now() - timedelta(seconds=_RECENT_RUN_WINDOW_S)
    recent = BenchmarkRun.objects.filter(started_at__gte=cutoff).order_by(
        "-started_at"
    ).first()
    if recent is None:
        return False
    request = getattr(self, "request", None)
    logger.warning(
        "[run_all_benchmarks-skip] storm guard: another run #%d started "
        "%.1f s ago — refusing to dispatch. trigger=%s task_id=%s origin=%s",
        recent.pk,
        (timezone.now() - recent.started_at).total_seconds(),
        trigger,
        getattr(request, "id", "?") if request else "?",
        getattr(request, "origin", "?") if request else "?",
    )
    return True


def _summarise_results(all_results):
    """Reduce a list of BenchmarkResult rows to the summary_json shape."""
    return {
        "total": len(all_results),
        "fast": sum(1 for r in all_results if r.status == "fast"),
        "ok": sum(1 for r in all_results if r.status == "ok"),
        "slow": sum(1 for r in all_results if r.status == "slow"),
        "languages": {
            "cpp": sum(1 for r in all_results if r.language == "cpp"),
            "python": sum(1 for r in all_results if r.language == "python"),
        },
    }


@shared_task(time_limit=1800, soft_time_limit=1700, bind=True)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=600,
)
def run_all_benchmarks(self, run_id: int | None = None, trigger: str = "scheduled"):
    """Execute all benchmarks (C++ and Python) and store results."""
    from .models import BenchmarkResult, BenchmarkRun
    from .services.runner import (
        classify_results,
        run_cpp_benchmarks,
        run_python_benchmarks,
    )

    _log_caller_diagnostics(self, run_id, trigger)

    # ISS-102 storm guard. When `run_id` is provided (UI button passes one)
    # we skip the guard — the operator explicitly clicked "run". When the
    # task arrives without a run_id (cron beat / unknown caller) AND another
    # run started in the last 60 s, we refuse to dispatch.
    if run_id is None and _detect_storm_skip(self, trigger):
        return {"status": "skipped_storm_guard", "trigger": trigger}

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

        run.summary_json = _summarise_results(all_results)
        run.status = "completed"
        run.finished_at = timezone.now()
        run.save()
        logger.info(
            "Benchmark run #%d completed: %d fast, %d ok, %d slow",
            run.pk,
            run.summary_json["fast"],
            run.summary_json["ok"],
            run.summary_json["slow"],
        )
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.finished_at = timezone.now()
        run.save()
        logger.exception("Benchmark run #%d failed", run.pk)
        raise
