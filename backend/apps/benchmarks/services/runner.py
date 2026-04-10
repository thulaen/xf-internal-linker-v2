"""Orchestrates benchmark execution for C++, Python, and C#."""

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


def run_cpp_benchmarks(run: BenchmarkRun) -> list[dict]:
    """Execute all C++ benchmark executables and parse JSON output."""
    from apps.benchmarks.models import BenchmarkResult

    results = []
    build_dir = EXT_BENCH_DIR / "build" / "Release"
    if not build_dir.exists():
        logger.warning("C++ benchmark build directory not found: %s", build_dir)
        return results

    for exe in sorted(build_dir.glob("bench_*.exe")):
        ext_name = exe.stem.replace("bench_", "")
        logger.info("Running C++ benchmark: %s", exe.name)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            subprocess.run(  # nosec B603
                [str(exe), "--benchmark_format=json", f"--benchmark_out={tmp_path}"],
                timeout=300,
                capture_output=True,
                check=False,
            )
            with open(tmp_path) as f:
                data = json.load(f)

            for bench in data.get("benchmarks", []):
                name_parts = bench["name"].split("/")
                func_name = name_parts[0].replace("BM_", "")
                input_size = _classify_size(
                    name_parts[1] if len(name_parts) > 1 else "0"
                )
                mean_ns = int(bench.get("real_time", 0))

                result = BenchmarkResult(
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
                results.append(result)
        except Exception:
            logger.exception("Failed to run C++ benchmark: %s", exe.name)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return results


def run_python_benchmarks(run: BenchmarkRun) -> list[dict]:
    """Execute Python benchmarks via pytest-benchmark and parse JSON."""
    from apps.benchmarks.models import BenchmarkResult

    results = []
    if not PY_BENCH_DIR.exists():
        logger.warning("Python benchmark directory not found: %s", PY_BENCH_DIR)
        return results

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        subprocess.run(  # nosec B603 B607
            [
                "python",
                "-m",
                "pytest",
                str(PY_BENCH_DIR),
                f"--benchmark-json={tmp_path}",
                "--benchmark-disable-gc",
                "-q",
            ],
            timeout=600,
            capture_output=True,
            check=False,
            cwd=str(BASE_DIR),
        )

        with open(tmp_path) as f:
            data = json.load(f)

        for bench in data.get("benchmarks", []):
            name = bench.get("name", "")
            stats = bench.get("stats", {})
            mean_ns = int(stats.get("mean", 0) * 1_000_000_000)
            median_ns = int(stats.get("median", 0) * 1_000_000_000)

            parts = name.split("::")
            func_name = parts[-1] if parts else name
            ext = (
                func_name.split("_")[2] if len(func_name.split("_")) > 2 else "unknown"
            )
            size = _extract_size_from_name(func_name)

            result = BenchmarkResult(
                run=run,
                language="python",
                extension=ext,
                function_name=func_name,
                input_size=size,
                mean_ns=mean_ns,
                median_ns=median_ns,
                items_per_second=1_000_000_000 / max(mean_ns, 1),
                status="ok",
            )
            results.append(result)
    except Exception:
        logger.exception("Failed to run Python benchmarks")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return results


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
    if n <= 500:
        return "small"
    if n <= 15000:
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
