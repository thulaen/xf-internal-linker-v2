"""Tests for session-start lookup fast paths."""

from __future__ import annotations

import importlib
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def test_current_task_id_reads_handoff_head_and_uses_newest_marker(tmp_path, monkeypatch):
    module = importlib.import_module("apps.auto_issues.services.resolved_issue_index")
    handoff = tmp_path / "AGENT-HANDOFF.md"
    new_marker = "[TDD PREFLIGHT: session_id=22222222-2222-2222-2222-222222222222]"
    old_marker = "[TDD PREFLIGHT: session_id=11111111-1111-1111-1111-111111111111]"
    handoff.write_text(new_marker + "\n" + ("x" * 2_000_000) + "\n" + old_marker)

    monkeypatch.setattr(module, "HANDOFF_PATH", handoff)
    module._task_id_cache = None

    assert module.current_task_id() == "22222222-2222-2222-2222-222222222222"


def test_current_task_id_reads_handoff_head_for_prepended_entries(tmp_path, monkeypatch):
    module = importlib.import_module("apps.auto_issues.services.resolved_issue_index")
    handoff = tmp_path / "AGENT-HANDOFF.md"
    newest = "[TDD PREFLIGHT: session_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa]"
    older = "[TDD PREFLIGHT: session_id=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb]"
    handoff.write_text(newest + "\n" + ("x" * 2_000_000) + "\n" + older)

    monkeypatch.setattr(module, "HANDOFF_PATH", handoff)
    module._task_id_cache = None

    assert module.current_task_id() == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_current_task_id_reuses_cached_handoff_marker(tmp_path, monkeypatch):
    module = importlib.import_module("apps.auto_issues.services.resolved_issue_index")
    handoff = tmp_path / "AGENT-HANDOFF.md"
    marker = "[TDD PREFLIGHT: session_id=33333333-3333-3333-3333-333333333333]"
    handoff.write_text(marker)
    calls = 0
    original = module._read_handoff_head

    def counted_tail():
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(module, "HANDOFF_PATH", handoff)
    monkeypatch.setattr(module, "_read_handoff_head", counted_tail)
    module._task_id_cache = None

    assert module.current_task_id() == "33333333-3333-3333-3333-333333333333"
    assert module.current_task_id() == "33333333-3333-3333-3333-333333333333"
    assert calls == 1


def test_current_task_id_caches_git_fallback_when_no_marker(tmp_path, monkeypatch):
    module = importlib.import_module("apps.auto_issues.services.resolved_issue_index")
    handoff = tmp_path / "AGENT-HANDOFF.md"
    handoff.write_text("no preflight marker")
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args[0], 0, "abcdef1234567890\n", "")

    monkeypatch.setattr(module, "HANDOFF_PATH", handoff)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    module._task_id_cache = None

    first = module.current_task_id()
    second = module.current_task_id()

    assert first == second
    assert calls == 1


def test_current_task_id_cold_path_is_5x_faster_than_full_file_scan(tmp_path, monkeypatch):
    module = importlib.import_module("apps.auto_issues.services.resolved_issue_index")
    handoff = tmp_path / "AGENT-HANDOFF.md"
    marker = "[TDD PREFLIGHT: session_id=dddddddd-dddd-dddd-dddd-dddddddddddd]"
    handoff.write_text(marker + "\n" + ("x" * 16_000_000), encoding="utf-8")

    monkeypatch.setattr(module, "HANDOFF_PATH", handoff)

    def legacy_full_scan() -> str:
      text = handoff.read_text(encoding="utf-8", errors="replace")
      return module._latest_prefight_session_id(text)

    def timed(fn, repeat: int = 7) -> float:
      timings = []
      for _ in range(repeat):
        module._task_id_cache = None
        start = time.perf_counter()
        assert fn() == "dddddddd-dddd-dddd-dddd-dddddddddddd"
        timings.append(time.perf_counter() - start)
      return sorted(timings)[len(timings) // 2]

    legacy_seconds = timed(legacy_full_scan, repeat=5)
    optimized_seconds = timed(module.current_task_id, repeat=7)

    assert legacy_seconds / optimized_seconds >= 5
