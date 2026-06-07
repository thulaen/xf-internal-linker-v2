#!/usr/bin/env python3
"""Tests for ``.githooks/check-native-inspection-window.py`` (Phase K.3)."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


_HOOK_PATH = Path(__file__).resolve().parent / "check-native-inspection-window.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location(
        "check_native_inspection_window_under_test", _HOOK_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-native-inspection-window.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


class _StderrCollector:
    def __init__(self, bucket: list[str]) -> None:
        self._bucket = bucket

    def write(self, msg: str) -> int:
        self._bucket.append(msg)
        return len(msg)

    def flush(self) -> None:  # pragma: no cover
        return None


def _run_with(
    *,
    rust_files: list[str],
    handoff_text: str = "",
    handoff_diff: str = "",
    now: datetime | None = None,
) -> tuple[int, str]:
    captured: list[str] = []
    fixed_now = now or datetime.now(timezone.utc)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fixed_now if tz is None else fixed_now.astimezone(tz)

    with patch.object(
        hook, "_staged_rust_files", return_value=rust_files
    ), patch.object(
        hook, "_handoff_text", return_value=handoff_text
    ), patch.object(
        hook, "_staged_handoff_diff", return_value=handoff_diff
    ), patch.object(hook, "datetime", _FrozenDatetime), patch.object(
        hook.sys, "stderr", new=_StderrCollector(captured)
    ):
        rc = hook.main()
    return rc, "".join(captured)


def _window_marker(path: str, opened_at: datetime) -> str:
    closes = opened_at + timedelta(days=7)
    return (
        f"[NATIVE INSPECTION WINDOW: file={path} "
        f"opened_at={opened_at.isoformat()} closes_at={closes.isoformat()}]"
    )


class NoNativeFilesExempt(unittest.TestCase):
    def test_pure_docs_commit_passes(self) -> None:
        rc, _ = _run_with(rust_files=[])
        self.assertEqual(rc, 0)

    def test_retired_language_files_are_not_rust_paths(self) -> None:
        self.assertFalse(hook._is_rust_path("services/sentinel/src/Main.hs"))
        self.assertFalse(hook._is_rust_path("services/streamd/cmd/main.go"))
        self.assertFalse(hook._is_rust_path("backend/extensions/scoring.cpp"))
        self.assertFalse(hook._is_rust_path("backend/lua/rules.lua"))


class FirstMergeExempt(unittest.TestCase):
    def test_rust_file_with_no_prior_window_passes(self) -> None:
        rc, _ = _run_with(
            rust_files=["backend/extensions/scoring/src/lib.rs"],
            handoff_text="some prior content without any window markers",
        )
        self.assertEqual(rc, 0)


class OpenWindowPasses(unittest.TestCase):
    def test_open_window_lets_edit_through(self) -> None:
        now = datetime(2026, 5, 23, tzinfo=timezone.utc)
        opened = now - timedelta(days=3)
        handoff = _window_marker("backend/extensions/scoring/src/lib.rs", opened)
        rc, _ = _run_with(
            rust_files=["backend/extensions/scoring/src/lib.rs"],
            handoff_text=handoff,
            now=now,
        )
        self.assertEqual(rc, 0)


class SettledWindowBlocks(unittest.TestCase):
    def test_closed_window_with_no_reopen_blocks(self) -> None:
        now = datetime(2026, 5, 23, tzinfo=timezone.utc)
        opened = now - timedelta(days=30)
        handoff = _window_marker("backend/extensions/scoring/src/lib.rs", opened)
        rc, out = _run_with(
            rust_files=["backend/extensions/scoring/src/lib.rs"],
            handoff_text=handoff,
            now=now,
        )
        self.assertEqual(rc, 2)
        self.assertIn("backend/extensions/scoring/src/lib.rs", out)
        self.assertIn("closed", out)


class ReopenMarkersAllowEdit(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 5, 23, tzinfo=timezone.utc)
        opened = self.now - timedelta(days=30)
        self.path = "backend/extensions/scoring/src/lib.rs"
        self.handoff = _window_marker(self.path, opened)

    def test_user_reopen_passes(self) -> None:
        diff = (
            f'[USER REQUEST INSPECTION: file={self.path} '
            'reason="user-requested second pass for correctness review"]'
        )
        rc, _ = _run_with(
            rust_files=[self.path],
            handoff_text=self.handoff,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 0)

    def test_user_reopen_with_short_reason_blocks(self) -> None:
        diff = (
            f'[USER REQUEST INSPECTION: file={self.path} '
            'reason="too short"]'
        )
        rc, out = _run_with(
            rust_files=[self.path],
            handoff_text=self.handoff,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 2)
        self.assertIn("closed", out)

    def test_pyroscope_regression_meets_threshold(self) -> None:
        diff = (
            f"[PYROSCOPE REGRESSION: file={self.path} baseline_p95_ms=100.0 "
            "observed_p95_ms=200.0 sustained_minutes=15]"
        )
        rc, _ = _run_with(
            rust_files=[self.path],
            handoff_text=self.handoff,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 0)

    def test_pyroscope_regression_below_multiplier_blocks(self) -> None:
        diff = (
            f"[PYROSCOPE REGRESSION: file={self.path} baseline_p95_ms=100.0 "
            "observed_p95_ms=120.0 sustained_minutes=15]"
        )
        rc, _ = _run_with(
            rust_files=[self.path],
            handoff_text=self.handoff,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 2)

    def test_otel_regression_with_short_window_blocks(self) -> None:
        diff = (
            f"[OTEL_PROFILE REGRESSION: file={self.path} baseline_p95_ms=100.0 "
            "observed_p95_ms=200.0 sustained_minutes=5]"
        )
        rc, _ = _run_with(
            rust_files=[self.path],
            handoff_text=self.handoff,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
