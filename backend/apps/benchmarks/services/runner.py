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
EXT_BENCH_DIR = BASE_DIR / "extensions" / "benchmarks"
PY_BENCH_DIR = BASE_DIR / "benchmarks"

# Size classification thresholds for benchmark input sizes
_SIZE_SMALL_MAX = 500
_SIZE_MEDIUM_MAX = 15000


def run_cpp_benchmarks(run: BenchmarkRun) -> list[dict]:
    """Execute all C++ benchmark executables and parse JSON output.

    Bug fix 2026-05-04: previously globbed only ``bench_*.exe``, which
    matches Windows binaries but the backend container is Linux —
    production runs found ZERO benchmarks and the operator had no
    signal. Now globs both Linux (no extension, with ``stat.S_IXUSR``
    executable bit) AND Windows (``.exe``) so the runner works on
    every supported host.
    """
    from apps.benchmarks.models import BenchmarkResult

    results: list = []
    build_dir = EXT_BENCH_DIR / "build" / "Release"
    if not build_dir.exists():
        logger.warning("C++ benchmark build directory not found: %s", build_dir)
        return results

    executables = _discover_cpp_benchmark_executables(build_dir)
    if not executables:
        logger.warning(
            "No C++ benchmark executables found in %s — did the build step run?",
            build_dir,
        )
        return results

    for exe in executables:
        ext_name = exe.stem.replace("bench_", "")
        logger.info("Running C++ benchmark: %s", exe.name)
        results.extend(_run_one_cpp_benchmark(exe, ext_name, run, BenchmarkResult))

    return results


def _discover_cpp_benchmark_executables(build_dir: Path) -> list[Path]:
    """Return every executable bench_* file in *build_dir*.

    Cross-OS: ``.exe`` on Windows, no extension on Linux/macOS. We
    treat anything starting with ``bench_`` AND marked executable
    (Linux executable bit OR ``.exe`` suffix) as a benchmark binary.
    """
    import stat

    found: list[Path] = []
    for path in sorted(build_dir.glob("bench_*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".exe":
            found.append(path)
            continue
        # Linux/macOS: no extension, must have the executable bit.
        try:
            mode = path.stat().st_mode
            if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                found.append(path)
        except OSError:
            # Permission error reading stat — skip silently; the
            # warning above already noted "no benchmarks found" if all
            # files end up filtered out.
            continue
    return found


def _run_one_cpp_benchmark(
    exe: Path,
    ext_name: str,
    run: BenchmarkRun,
    result_class,
) -> list:
    """Run one C++ benchmark binary; parse JSON; return BenchmarkResult rows.

    Returns empty list on any failure (timeout, non-zero exit, malformed
    JSON). Errors surface to /error-log via ``ingest_error`` so the
    operator sees the failure instead of a silently-empty cert report.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        completed = subprocess.run(  # noqa: S603 — args are repo-internal benchmark binaries, not user input
            [str(exe), "--benchmark_format=json", f"--benchmark_out={tmp_path}"],
            timeout=300,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            _emit_benchmark_error(
                exe.name,
                f"Exit code {completed.returncode}",
                completed.stderr.decode("utf-8", errors="replace")[:1000],
            )
            return []
        with open(tmp_path) as f:
            data = json.load(f)
        return [
            _parse_cpp_bench_row(b, run, ext_name, result_class)
            for b in data.get("benchmarks", [])
        ]
    except subprocess.TimeoutExpired:
        _emit_benchmark_error(exe.name, "Timeout (>300 s)", "")
        return []
    except (json.JSONDecodeError, OSError) as exc:
        _emit_benchmark_error(
            exe.name, f"Parse failure: {type(exc).__name__}", str(exc)
        )
        return []
    except Exception as exc:  # noqa: BLE001 — defensive last-resort: surface to /error-log
        _emit_benchmark_error(exe.name, "Unexpected error", repr(exc))
        return []
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _parse_cpp_bench_row(bench: dict, run, ext_name: str, result_class):
    """Build one BenchmarkResult from a Google-Benchmark JSON entry."""
    name_parts = bench.get("name", "").split("/")
    func_name = name_parts[0].replace("BM_", "")
    input_size = _classify_size(name_parts[1] if len(name_parts) > 1 else "0")
    mean_ns = int(bench.get("real_time", 0))
    return result_class(
        run=run,
        language="cpp",
        extension=ext_name,
        function_name=func_name,
        input_size=input_size,
        mean_ns=mean_ns,
        median_ns=mean_ns,
        items_per_second=bench.get("items_per_second", 0),
        status="ok",
    )


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
