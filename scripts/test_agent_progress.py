#!/usr/bin/env python3
"""Unit tests for scripts/agent_progress.py — the cross-agent progress reporter.

All logic lives in pure functions (progress_bar, percent_done, detect_stuck,
should_emit, render), so these run with no Docker, no git, and no network.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parent / "agent_progress.py"
_spec = importlib.util.spec_from_file_location("agent_progress", _MOD_PATH)
agent_progress = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent_progress)

CADENCE = agent_progress.CADENCE_SECONDS


class ProgressBarTests(unittest.TestCase):
    def test_empty_when_no_total(self) -> None:
        self.assertEqual(agent_progress.progress_bar(0, 0), "░" * 20)

    def test_half_done_fills_half(self) -> None:
        bar = agent_progress.progress_bar(50, 100)
        self.assertEqual(bar.count("█"), 10)
        self.assertEqual(bar.count("░"), 10)

    def test_full_when_complete(self) -> None:
        self.assertEqual(agent_progress.progress_bar(100, 100), "█" * 20)


class PercentDoneTests(unittest.TestCase):
    def test_zero_baseline_is_zero(self) -> None:
        self.assertEqual(agent_progress.percent_done(5, 0), 0)

    def test_quarter_committed(self) -> None:
        self.assertEqual(agent_progress.percent_done(75, 100), 25)

    def test_never_negative_when_dirty_grew(self) -> None:
        self.assertEqual(agent_progress.percent_done(120, 100), 0)


class DetectStuckTests(unittest.TestCase):
    def test_low_cpu_long_uptime_is_stuck(self) -> None:
        rows = [{"name": "xf-mutation-1", "up_minutes": 11, "cpu_percent": 0.0}]
        stuck = agent_progress.detect_stuck(rows, None)
        self.assertEqual(len(stuck), 1)
        self.assertIn("stalled", stuck[0])

    def test_busy_container_is_not_stuck(self) -> None:
        rows = [{"name": "xf-mutation-1", "up_minutes": 11, "cpu_percent": 70.0}]
        self.assertEqual(agent_progress.detect_stuck(rows, None), [])

    def test_recent_container_is_not_stuck(self) -> None:
        rows = [{"name": "xf-mutation-1", "up_minutes": 2, "cpu_percent": 0.0}]
        self.assertEqual(agent_progress.detect_stuck(rows, None), [])

    def test_old_held_lock_is_stuck(self) -> None:
        stuck = agent_progress.detect_stuck([], 9 * 60)
        self.assertEqual(len(stuck), 1)
        self.assertIn("lock", stuck[0])

    def test_fresh_lock_is_not_stuck(self) -> None:
        self.assertEqual(agent_progress.detect_stuck([], 60), [])


class ShouldEmitTests(unittest.TestCase):
    def test_first_run_emits(self) -> None:
        self.assertTrue(agent_progress.should_emit(None, 1000.0, stuck=False, force=False))

    def test_inside_window_stays_quiet(self) -> None:
        self.assertFalse(
            agent_progress.should_emit(1000.0, 1000.0 + CADENCE - 1, stuck=False, force=False)
        )

    def test_after_window_emits(self) -> None:
        self.assertTrue(
            agent_progress.should_emit(1000.0, 1000.0 + CADENCE, stuck=False, force=False)
        )

    def test_stuck_overrides_window(self) -> None:
        self.assertTrue(agent_progress.should_emit(1000.0, 1000.5, stuck=True, force=False))

    def test_force_overrides_window(self) -> None:
        self.assertTrue(agent_progress.should_emit(1000.0, 1000.5, stuck=False, force=True))


class RenderTests(unittest.TestCase):
    def test_shows_bar_and_counts_with_baseline(self) -> None:
        out = agent_progress.render("12:00:00", "clean the tree", dirty=300, baseline=600, stuck=[])
        self.assertIn("[PROGRESS · 12:00:00 · clean the tree]", out)
        self.assertIn("50%", out)
        self.assertIn("300 files left", out)
        self.assertIn("Stuck? no", out)

    def test_reports_stuck_text(self) -> None:
        out = agent_progress.render("12:00:00", "x", dirty=10, baseline=20, stuck=["it stalled"])
        self.assertIn("Stuck? YES — it stalled", out)

    def test_no_baseline_shows_plain_count(self) -> None:
        out = agent_progress.render("12:00:00", "answering", dirty=7, baseline=0, stuck=[])
        self.assertIn("7 uncommitted files", out)


class WriteStatusFileTests(unittest.TestCase):
    def test_writes_block_to_status_path(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "latest.txt"
            original = agent_progress.STATUS_PATH
            agent_progress.STATUS_PATH = target
            try:
                agent_progress._write_status_file("[PROGRESS] hello")
            finally:
                agent_progress.STATUS_PATH = original
            self.assertEqual(target.read_text(encoding="utf-8").strip(), "[PROGRESS] hello")

    def test_unwritable_path_does_not_raise(self) -> None:
        original = agent_progress.STATUS_PATH
        # A path whose parent is a file, not a directory, cannot be created;
        # the writer must swallow the OSError so a status write never breaks a reply.
        agent_progress.STATUS_PATH = Path(__file__) / "nope" / "latest.txt"
        try:
            agent_progress._write_status_file("x")  # must not raise
        finally:
            agent_progress.STATUS_PATH = original


if __name__ == "__main__":
    unittest.main()
