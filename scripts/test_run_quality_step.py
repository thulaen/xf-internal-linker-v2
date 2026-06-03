"""Tests for bounded quality-step command execution."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_quality_step


def _argv(tmp_path: Path, command: str = "tool --flag") -> list[str]:
    return [
        "run_quality_step.py",
        "--evidence-out",
        str(tmp_path / "evidence.jsonl"),
        "--check-type",
        "static_analysis",
        "--tool-name",
        "demo-tool",
        "--command",
        command,
        "--pass-summary",
        "passed",
        "--fail-summary",
        "failed",
        "--timeout-seconds",
        "7",
    ]


def test_quality_step_passes_timeout_to_subprocess(monkeypatch, tmp_path) -> None:
    """Each wrapped command receives the requested wall-clock timeout."""

    seen: dict[str, object] = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="ok\n")

    monkeypatch.setattr(run_quality_step.subprocess, "run", fake_run)
    monkeypatch.setattr(run_quality_step, "_write", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sys, "argv", _argv(tmp_path))

    assert run_quality_step.main() == 0
    assert seen["command"] == "tool --flag"
    assert seen["timeout"] == 7


def test_quality_step_timeout_writes_report_and_returns_124(monkeypatch, tmp_path) -> None:
    """A timed-out command records a useful report and returns GNU timeout's code."""

    def fake_run(_command, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd="slow-tool",
            timeout=7,
            output="partial output\n",
        )

    written: dict[str, object] = {}

    def fake_write(_args, returncode, report):
        written["returncode"] = returncode
        written["report"] = Path(report).read_text(encoding="utf-8")

    monkeypatch.setattr(run_quality_step.subprocess, "run", fake_run)
    monkeypatch.setattr(run_quality_step, "_write", fake_write)
    monkeypatch.setattr(sys, "argv", _argv(tmp_path, "slow-tool"))

    assert run_quality_step.main() == 124
    assert written["returncode"] == 124
    assert "Timed out after 7 seconds" in str(written["report"])
    assert "partial output" in str(written["report"])
