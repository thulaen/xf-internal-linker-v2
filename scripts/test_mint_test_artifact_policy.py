"""Regression tests for test artifacts and failure reporting."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_quality_step


ROOT = Path(__file__).resolve().parents[1]


def test_direct_pytest_runs_do_not_create_windows_cache() -> None:
    pytest_ini = ROOT / "pytest.ini"

    assert pytest_ini.exists()
    assert "-p no:cacheprovider" in pytest_ini.read_text(encoding="utf-8")


def test_python_quality_runner_keeps_test_caches_off_repo_mount() -> None:
    script = (ROOT / "scripts" / "run-python-quality.sh").read_text(encoding="utf-8")

    for marker in (
        "XDG_CACHE_HOME",
        "PYTEST_ADDOPTS",
        "--cache-dir=/tmp/xf-test-cache/pytest",
        "COVERAGE_FILE",
        "MYPY_CACHE_DIR",
        "RUFF_CACHE_DIR",
        "MUTMUT_CACHE_DIR",
    ):
        assert marker in script


def test_failed_test_step_files_autoissue(monkeypatch, tmp_path) -> None:
    calls: list[object] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if isinstance(command, list) and "file_test_failure" in command:
            return SimpleNamespace(returncode=0, stdout="[TEST FAILURE AUTOISSUE: #1 action=created]\n")
        return subprocess.CompletedProcess(command, 1, stdout="FAILED tests/test_demo.py::test_demo\n")

    monkeypatch.setattr(run_quality_step.subprocess, "run", fake_run)
    monkeypatch.setattr(run_quality_step, "_write", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("XF_TEST_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_quality_step.py",
            "--evidence-out",
            str(tmp_path / "evidence.jsonl"),
            "--check-type",
            "normal_test",
            "--tool-name",
            "pytest",
            "--command",
            "python -m pytest tests/test_demo.py",
            "--pass-summary",
            "passed",
            "--fail-summary",
            "failed",
            "--file-path",
            "tests/test_demo.py",
        ],
    )

    assert run_quality_step.main() == 1
    assert any(isinstance(call, list) and "file_test_failure" in call for call in calls)
    assert list(tmp_path.glob("quality-step-pytest*.log"))
