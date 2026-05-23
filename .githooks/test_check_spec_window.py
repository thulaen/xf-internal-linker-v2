#!/usr/bin/env python3
"""Tests for ``.githooks/check-spec-window.py`` (Phase K.3)."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


_HOOK_PATH = Path(__file__).resolve().parent / "check-spec-window.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location(
        "check_spec_window_under_test", _HOOK_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-spec-window.py")
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
    spec_files: list[str],
    opened_at: datetime | None = None,
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
        hook, "_staged_spec_files", return_value=spec_files
    ), patch.object(
        hook, "_opened_at_for", return_value=opened_at
    ), patch.object(
        hook, "_staged_handoff_diff", return_value=handoff_diff
    ), patch.object(hook, "datetime", _FrozenDatetime), patch.object(
        hook.sys, "stderr", new=_StderrCollector(captured)
    ):
        rc = hook.main()
    return rc, "".join(captured)


class NoSpecFilesExempt(unittest.TestCase):
    def test_pure_code_commit_passes(self) -> None:
        rc, _ = _run_with(spec_files=[])
        self.assertEqual(rc, 0)


class NoFreshnessMarkerExempt(unittest.TestCase):
    def test_spec_without_marker_passes(self) -> None:
        rc, _ = _run_with(
            spec_files=["docs/specs/fr-new.md"],
            opened_at=None,
        )
        self.assertEqual(rc, 0)


class OpenWindowPasses(unittest.TestCase):
    def test_recently_landed_spec_passes(self) -> None:
        now = datetime(2026, 5, 23, tzinfo=timezone.utc)
        opened = now - timedelta(days=3)
        rc, _ = _run_with(
            spec_files=["docs/specs/fr-young.md"],
            opened_at=opened,
            now=now,
        )
        self.assertEqual(rc, 0)


class SettledWindowBlocks(unittest.TestCase):
    def test_old_spec_with_no_reopen_blocks(self) -> None:
        now = datetime(2026, 5, 23, tzinfo=timezone.utc)
        opened = now - timedelta(days=30)
        rc, out = _run_with(
            spec_files=["docs/specs/fr-old.md"],
            opened_at=opened,
            now=now,
        )
        self.assertEqual(rc, 2)
        self.assertIn("docs/specs/fr-old.md", out)
        self.assertIn("closed", out)


class ReopenMarkersAllowEdit(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 5, 23, tzinfo=timezone.utc)
        self.opened = self.now - timedelta(days=30)
        self.spec = "docs/specs/fr-old.md"

    def test_user_reopen_passes(self) -> None:
        diff = (
            '[USER REQUEST SPEC EDIT: spec=docs/specs/fr-old.md '
            'reason="operator requested correction of stale citation block"]'
        )
        rc, _ = _run_with(
            spec_files=[self.spec],
            opened_at=self.opened,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 0)

    def test_user_reopen_with_short_reason_blocks(self) -> None:
        diff = (
            '[USER REQUEST SPEC EDIT: spec=docs/specs/fr-old.md reason="too short"]'
        )
        rc, _ = _run_with(
            spec_files=[self.spec],
            opened_at=self.opened,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 2)

    def test_citation_drift_passes(self) -> None:
        diff = (
            "[SPEC CITATION DRIFT: spec=docs/specs/fr-old.md "
            "previous_id=doi:10.1145/old new_id=doi:10.1145/new "
            "evidence_url=https://example.org/paper]"
        )
        rc, _ = _run_with(
            spec_files=[self.spec],
            opened_at=self.opened,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 0)

    def test_citation_drift_with_same_id_blocks(self) -> None:
        diff = (
            "[SPEC CITATION DRIFT: spec=docs/specs/fr-old.md "
            "previous_id=doi:10.1145/same new_id=doi:10.1145/same "
            "evidence_url=https://example.org/paper]"
        )
        rc, _ = _run_with(
            spec_files=[self.spec],
            opened_at=self.opened,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 2)

    def test_kpi_drift_above_threshold_passes(self) -> None:
        diff = (
            "[SPEC KPI DRIFT: spec=docs/specs/fr-old.md metric=p95_latency_ms "
            "baseline=100.0 observed=140.0 threshold_pct=20.0]"
        )
        rc, _ = _run_with(
            spec_files=[self.spec],
            opened_at=self.opened,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 0)

    def test_kpi_drift_below_threshold_blocks(self) -> None:
        diff = (
            "[SPEC KPI DRIFT: spec=docs/specs/fr-old.md metric=p95_latency_ms "
            "baseline=100.0 observed=105.0 threshold_pct=20.0]"
        )
        rc, _ = _run_with(
            spec_files=[self.spec],
            opened_at=self.opened,
            handoff_diff=diff,
            now=self.now,
        )
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
