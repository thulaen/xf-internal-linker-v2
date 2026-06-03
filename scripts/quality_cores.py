"""Adaptive worker-count policy for local quality tools.

The default is every visible logical processor, with no local cap. Set
``XF_QUALITY_CORES`` to a positive integer to request a specific worker count;
values above the visible processor count are clamped and invalid values are
ignored with a warning. Parallel test failures should be fixed by making the
tests isolated, not by lowering this shared default.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import platform as platform_module
import sys


@dataclass(frozen=True)
class QualityCoreResult:
    workers: int
    source: str
    visible_cpus: int
    platform: str


def _platform_name() -> str:
    name = platform_module.system().lower()
    if name.startswith("darwin"):
        return "darwin"
    if name.startswith("windows"):
        return "windows"
    return "linux"


def _cpu_count_fallback() -> int:
    count = os.cpu_count()
    if count is None or count < 1:
        print(
            "[quality_cores] warning: cpu count unavailable; using 1",
            file=sys.stderr,
        )
        return 1
    return count


def _linux_affinity_count() -> int:
    try:
        return len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return _cpu_count_fallback()


def _linux_cgroup_quota_count() -> int | None:
    path = Path("/sys/fs/cgroup/cpu.max")
    try:
        raw = path.read_text(encoding="utf-8").strip().split()
    except OSError:
        return None
    if len(raw) < 2 or raw[0] == "max":
        return None
    try:
        quota = int(raw[0])
        period = int(raw[1])
    except ValueError:
        return None
    if quota <= 0 or period <= 0:
        return None
    return max(1, math.floor(quota / period))


def visible_cpus() -> int:
    platform = _platform_name()
    if platform == "linux":
        affinity = _linux_affinity_count()
        quota = _linux_cgroup_quota_count()
        if quota is not None and quota < affinity:
            return max(1, quota)
        return max(1, affinity)
    return max(1, _cpu_count_fallback())


def _override_value(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        parsed = int(raw)
    except ValueError:
        print(
            f"[quality_cores] warning: invalid XF_QUALITY_CORES='{raw}' ignored",
            file=sys.stderr,
        )
        return None
    if parsed <= 0:
        print(
            f"[quality_cores] warning: invalid XF_QUALITY_CORES='{raw}' ignored",
            file=sys.stderr,
        )
        return None
    return parsed


def quality_cores(tool: str) -> QualityCoreResult:
    visible = visible_cpus()
    requested = _override_value(os.environ.get("XF_QUALITY_CORES"))
    source = "default"
    workers = visible
    if requested is not None:
        if requested > visible:
            workers = visible
            source = "override-clamped"
            print(
                "[quality_cores] warning: XF_QUALITY_CORES="
                f"{requested} clamped to visible_cpus={visible}",
                file=sys.stderr,
            )
        else:
            workers = requested
            source = "override"
    workers = max(1, workers)
    result = QualityCoreResult(
        workers=workers,
        source=source,
        visible_cpus=visible,
        platform=_platform_name(),
    )
    print(
        "[quality_cores] "
        f"tool={tool} workers={result.workers} source={result.source} "
        f"visible_cpus={result.visible_cpus} platform={result.platform}",
        file=sys.stderr,
    )
    return result


if __name__ == "__main__":
    tool_name = sys.argv[1] if len(sys.argv) > 1 else "quality"
    print(quality_cores(tool_name).workers)
