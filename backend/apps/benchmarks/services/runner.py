"""Orchestrates benchmark execution for C++ and Python."""

from __future__ import annotations

import json
import logging
import subprocess  # nosec B404 — runs benchmark executables, not user input
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from apps.benchmarks.models import BenchmarkRun

logger = logging.getLogger(__name__)

BASE_DIR = Path(settings.BASE_DIR)
PY_BENCH_DIR = BASE_DIR / "benchmarks"

# Size classification thresholds for benchmark input sizes
_SIZE_SMALL_MAX = 500
_SIZE_MEDIUM_MAX = 15000


def _emit_benchmark_error(exe_name: str, summary: str, detail: str) -> None:
    """Surface a benchmark failure to /error-log. Best-effort; never raises."""
    logger.warning("benchmark failure: %s — %s", exe_name, summary)
    try:
        from apps.audit.error_ingest import ingest_error

        ingest_error(
            job_type="benchmark_run",
            step=exe_name,
            error_message=summary,
            raw_exception=detail,
            why=(
                "A benchmark binary failed during the periodic run. The cert "
                "report will under-count this extension; rebuild the C++ "
                "extension or check the log detail above for the cause."
            ),
        )
    except Exception:  # noqa: BLE001 — error-log itself failing must not propagate
        logger.debug(
            "benchmark_run: ingest_error itself failed for %s; suppressed",
            exe_name,
            exc_info=True,
        )


def run_python_benchmarks(run: BenchmarkRun) -> list[dict]:
    """Execute Python benchmarks via pytest-benchmark and parse JSON.

    Bug fix 2026-05-04: previously caught ``Exception`` and only logged
    via ``logger.exception``, so a missing pytest dep / corrupt JSON /
    timeout silently produced 0 Python benchmarks and the operator
    never knew. Now: surface failures to ``/error-log`` via
    ``ingest_error`` so the cert report has visible breadcrumbs.
    """
    from apps.benchmarks.models import BenchmarkResult

    if not PY_BENCH_DIR.exists():
        logger.warning("Python benchmark directory not found: %s", PY_BENCH_DIR)
        return []

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        if not _invoke_pytest_benchmark(tmp_path):
            return []
        with open(tmp_path) as f:
            data = json.load(f)
        return [
            _parse_python_bench_row(b, run, BenchmarkResult)
            for b in data.get("benchmarks", [])
        ]
    except (json.JSONDecodeError, OSError) as exc:
        _emit_benchmark_error(
            "python_benchmarks", f"Parse failure: {type(exc).__name__}", str(exc)
        )
        return []
    except Exception as exc:  # noqa: BLE001 — defensive last-resort: surface to /error-log
        _emit_benchmark_error("python_benchmarks", "Unexpected error", repr(exc))
        return []
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _invoke_pytest_benchmark(out_path: str) -> bool:
    """Run ``pytest --benchmark-json=<out_path>``. Return True on success.

    Failure routes through ``_emit_benchmark_error`` so the cert report
    has a visible breadcrumb when pytest itself blows up (e.g. missing
    pytest-benchmark plugin, dep import failure, or timeout).
    """
    try:
        # pytest path is repo-internal, not user input — no shell interpolation.
        completed = subprocess.run(  # noqa: S603 S607  # nosec B603 B607
            [
                "python",
                "-m",
                "pytest",
                str(PY_BENCH_DIR),
                f"--benchmark-json={out_path}",
                "--benchmark-disable-gc",
                "-q",
            ],
            timeout=600,
            capture_output=True,
            check=False,
            cwd=str(BASE_DIR),
        )
    except subprocess.TimeoutExpired:
        _emit_benchmark_error("python_benchmarks", "Timeout (>600 s)", "")
        return False
    if completed.returncode != 0:
        _emit_benchmark_error(
            "python_benchmarks",
            f"pytest exit code {completed.returncode}",
            completed.stderr.decode("utf-8", errors="replace")[:1000],
        )
        return False
    return True


def _parse_python_bench_row(bench: dict, run, result_class):
    """Build one BenchmarkResult from a pytest-benchmark JSON entry."""
    name = bench.get("name", "")
    stats = bench.get("stats", {})
    mean_ns = int(stats.get("mean", 0) * 1_000_000_000)
    median_ns = int(stats.get("median", 0) * 1_000_000_000)
    parts = name.split("::")
    func_name = parts[-1] if parts else name
    ext = func_name.split("_")[2] if len(func_name.split("_")) > 2 else "unknown"
    return result_class(
        run=run,
        language="python",
        extension=ext,
        function_name=func_name,
        input_size=_extract_size_from_name(func_name),
        mean_ns=mean_ns,
        median_ns=median_ns,
        items_per_second=1_000_000_000 / max(mean_ns, 1),
        status="ok",
    )


def classify_results(results: list) -> None:
    """Set status to fast/ok/slow based on baseline thresholds."""
    for r in results:
        if r.threshold_ns and r.threshold_ns > 0:
            ratio = r.mean_ns / r.threshold_ns
            if ratio <= 1.0:
                r.status = "fast"
            elif ratio <= 2.0:
                r.status = "ok"
            else:
                r.status = "slow"
        else:
            r.status = "ok"


def _classify_size(value: str) -> str:
    """Map a numeric argument to small/medium/large."""
    try:
        n = int(value)
    except ValueError:
        return "medium"
    if n <= _SIZE_SMALL_MAX:
        return "small"
    if n <= _SIZE_MEDIUM_MAX:
        return "medium"
    return "large"


def _extract_size_from_name(name: str) -> str:
    """Extract size label from Python benchmark function names."""
    lower = name.lower()
    if "small" in lower:
        return "small"
    if "large" in lower:
        return "large"
    return "medium"
