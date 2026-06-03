"""Tests for explicit local quality-tool scope caps."""

from __future__ import annotations

import os
import importlib.util
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent


def _load_scope_cap():
    path = SCRIPTS_DIR / "scope_cap.py"
    spec = importlib.util.spec_from_file_location("scope_cap", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scope_cap = _load_scope_cap()


def test_under_cap_passes() -> None:
    assert scope_cap.enforce_cap(["a.py", "b.py"], 2, "pytest") == [
        "a.py",
        "b.py",
    ]


def test_over_cap_raises_with_tool_and_counts() -> None:
    with pytest.raises(scope_cap.ScopeCapExceeded) as exc_info:
        scope_cap.enforce_cap(["a.py", "b.py", "c.py"], 2, "mutmut")

    message = str(exc_info.value)
    assert "FAIL scope cap: mutmut targets=3 cap=2." in message
    assert "UNBLOCK: narrow the commit" in message


def test_xf_scope_full_tree_in_ci_bypasses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XF_QUALITY_ENV", "ci")
    monkeypatch.setenv("XF_SCOPE_FULL_TREE", "1")

    assert scope_cap.enforce_cap(["a.py", "b.py", "c.py"], 2, "mutmut") == [
        "a.py",
        "b.py",
        "c.py",
    ]


def test_xf_scope_full_tree_local_still_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XF_QUALITY_ENV", "local")
    monkeypatch.setenv("XF_SCOPE_FULL_TREE", "1")

    with pytest.raises(scope_cap.ScopeCapExceeded):
        scope_cap.enforce_cap(["a.py", "b.py", "c.py"], 2, "mutmut")


def test_cli_reports_failure_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    rc = scope_cap.main(["mutmut", "2", "a.py", "b.py", "c.py"])

    captured = capsys.readouterr()
    assert rc == 2
    assert "FAIL scope cap: mutmut targets=3 cap=2." in captured.err


def test_cli_uses_environment_for_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    env = os.environ.copy()
    env["XF_QUALITY_ENV"] = "ci"
    env["XF_SCOPE_FULL_TREE"] = "1"

    assert scope_cap.enforce_cap(["a.py", "b.py", "c.py"], 2, "mutmut", env=env) == [
        "a.py",
        "b.py",
        "c.py",
    ]
