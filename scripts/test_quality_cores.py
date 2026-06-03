"""Tests for adaptive quality worker-count helpers."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_python_quality_cores_defaults_to_visible_cpus() -> None:
    code = (
        "from scripts.quality_cores import quality_cores; "
        "result = quality_cores('pytest'); "
        "print(result.workers, result.source, result.visible_cpus, result.platform)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    workers, source, visible, platform = completed.stdout.strip().split()
    assert int(workers) == os.cpu_count()
    assert source == "default"
    assert int(visible) == os.cpu_count()
    assert platform in {"linux", "darwin", "windows"}
    assert "[quality_cores] tool=pytest" in completed.stderr
    assert f"workers={workers}" in completed.stderr


def test_python_quality_cores_clamps_large_override() -> None:
    code = (
        "from scripts.quality_cores import quality_cores; "
        "result = quality_cores('mutmut'); "
        "print(result.workers, result.source, result.visible_cpus)"
    )
    env = os.environ.copy()
    env["XF_QUALITY_CORES"] = "99999"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    workers, source, visible = completed.stdout.strip().split()
    assert int(workers) == os.cpu_count()
    assert source == "override-clamped"
    assert int(visible) == os.cpu_count()
    assert "clamped" in completed.stderr


def test_python_quality_cores_warns_on_invalid_override() -> None:
    code = (
        "from scripts.quality_cores import quality_cores; "
        "result = quality_cores('ruff'); "
        "print(result.workers, result.source)"
    )
    env = os.environ.copy()
    env["XF_QUALITY_CORES"] = "garbage"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    workers, source = completed.stdout.strip().split()
    assert int(workers) == os.cpu_count()
    assert source == "default"
    assert "invalid XF_QUALITY_CORES='garbage'" in completed.stderr


def test_shell_quality_cores_matches_python_default() -> None:
    bash = shutil.which("bash")
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        bash = str(git_bash)
    assert bash is not None
    shell = (
        ". scripts/quality_cores.sh; "
        "quality_cores pytest >/dev/null; "
        "printf '%s %s %s %s\\n' "
        "\"$QUALITY_CORES\" \"$QUALITY_CORES_SOURCE\" "
        "\"$QUALITY_CORES_VISIBLE_CPUS\" \"$QUALITY_CORES_PLATFORM\""
    )
    completed = subprocess.run(
        [bash, "-lc", shell],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    workers, source, visible, platform = completed.stdout.strip().split()
    assert int(workers) == os.cpu_count()
    assert source == "default"
    assert int(visible) == os.cpu_count()
    assert platform in {"linux", "darwin", "windows"}
    assert "[quality_cores] tool=pytest" in completed.stderr


def test_shell_quality_cores_stays_local_when_codebuild_env_is_present() -> None:
    bash = shutil.which("bash")
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    if git_bash.exists():
        bash = str(git_bash)
    assert bash is not None
    shell = (
        ". scripts/quality_cores.sh; "
        "quality_cores pytest >/dev/null; "
        "printf '%s|%s\\n' "
        "\"${COMPUTE_CLASS:-}\" \"${QUALITY_CORES_COMPUTE_CLASS:-}\""
    )
    env = os.environ.copy()
    env["CODEBUILD_PROJECT_NAME"] = "xf-mutation-master"
    completed = subprocess.run(
        [bash, "-lc", shell],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert completed.stdout.strip() == "|"
    assert "codebuild_project=" not in completed.stderr
    assert "compute_class=" not in completed.stderr
    assert "platform=" in completed.stderr
