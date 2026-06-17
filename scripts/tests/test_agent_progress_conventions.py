"""Convention tests for scripts/agent_progress.py pure helpers.

BDD:
  Given the cross-agent progress reporter's pure helpers
  When fed known inputs
  Then bar width, percent rounding, stuck detection, the emit cadence, and the
       rendered [PROGRESS ...] block match exact expected strings/numbers so
       mutation survivors on the changed lines are killed.

All Docker/git/subprocess side effects are avoided: only the pure helpers are
exercised. No network, no filesystem writes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ap = _load("agent_progress", "agent_progress.py")


class TestProgressBar(TestCase):
    def test_empty_when_total_zero(self):
        self.assertEqual(ap.progress_bar(0, 0), "░" * 20)

    def test_full_bar_when_done_equals_total(self):
        self.assertEqual(ap.progress_bar(10, 10), "█" * 20)

    def test_half_done_fills_ten_cells(self):
        self.assertEqual(ap.progress_bar(5, 10), "█" * 10 + "░" * 10)

    def test_negative_total_is_empty(self):
        self.assertEqual(ap.progress_bar(3, -1), "░" * 20)


class TestPercentDone(TestCase):
    def test_zero_baseline_returns_zero(self):
        self.assertEqual(ap.percent_done(5, 0), 0)

    def test_full_progress_is_hundred(self):
        self.assertEqual(ap.percent_done(0, 10), 100)

    def test_half_progress_rounds(self):
        self.assertEqual(ap.percent_done(5, 10), 50)

    def test_dirty_above_baseline_clamps_to_zero(self):
        self.assertEqual(ap.percent_done(12, 10), 0)


class TestDetectStuck(TestCase):
    def _container(self, up_minutes, cpu_percent, name="mutation-runner"):
        return {"name": name, "up_minutes": up_minutes, "cpu_percent": cpu_percent}

    def test_low_cpu_long_up_is_stuck(self):
        stuck = ap.detect_stuck([self._container(8, 1.0)], None)
        self.assertEqual(len(stuck), 1)
        self.assertIn("mutation-runner", stuck[0])
        self.assertIn("looks stalled, not working", stuck[0])

    def test_below_minute_threshold_not_stuck(self):
        self.assertEqual(ap.detect_stuck([self._container(7, 1.0)], None), [])

    def test_busy_container_not_stuck(self):
        self.assertEqual(ap.detect_stuck([self._container(20, 5.0)], None), [])

    def test_lock_at_threshold_is_stuck(self):
        stuck = ap.detect_stuck([], 8 * 60)
        self.assertEqual(
            stuck,
            ["the mutation-test lock has been held 8 min — a run may be wedged"],
        )

    def test_lock_below_threshold_not_stuck(self):
        self.assertEqual(ap.detect_stuck([], 8 * 60 - 1), [])

    def test_none_lock_not_stuck(self):
        self.assertEqual(ap.detect_stuck([], None), [])

    def test_keepalive_container_is_skipped(self):
        c = self._container(780, 0.0, name="frontend_mutation_tools")
        c["keepalive"] = True
        self.assertEqual(ap.detect_stuck([c], None), [])

    def test_non_keepalive_low_cpu_is_stuck(self):
        c = self._container(8, 1.0)
        c["keepalive"] = False
        self.assertEqual(len(ap.detect_stuck([c], None)), 1)


class TestIsKeepalive(TestCase):
    def test_tail_f_dev_null_true(self):
        self.assertTrue(ap.is_keepalive_command("sh -lc 'tail -f /dev/null'"))

    def test_sleep_infinity_true(self):
        self.assertTrue(ap.is_keepalive_command("sleep infinity"))

    def test_normal_command_false(self):
        self.assertFalse(ap.is_keepalive_command("python -m pytest"))


class TestShouldEmit(TestCase):
    def test_force_always_emits(self):
        self.assertTrue(ap.should_emit(100.0, 100.0, False, True))

    def test_stuck_always_emits(self):
        self.assertTrue(ap.should_emit(100.0, 100.0, True, False))

    def test_first_run_emits(self):
        self.assertTrue(ap.should_emit(None, 100.0, False, False))

    def test_within_cadence_stays_quiet(self):
        self.assertFalse(ap.should_emit(100.0, 100.0 + 599, False, False))

    def test_at_cadence_emits(self):
        self.assertTrue(ap.should_emit(100.0, 100.0 + 600, False, False))


class TestRender(TestCase):
    def test_chat_task_render_uses_steps_before_repo_count(self):
        task = ap.start_task_state("chat task", ["Inspect", "Fix", "Test", "Report"], now=100.0)
        block = ap.render("12:00:00", "fallback", dirty=55, baseline=660, stuck=[], task=task)
        self.assertIn("[PROGRESS · 12:00:00 · chat task]", block)
        self.assertIn("Task   [░░░░░░░░░░░░░░░░░░░░] 0%   0/4 steps done", block)
        self.assertIn("current: Inspect", block)
        self.assertIn("Repo   55 uncommitted files total", block)
        self.assertNotIn("files left to commit", block)

    def test_chat_task_done_steps_move_bar(self):
        task = ap.start_task_state("chat task", ["Inspect", "Fix"], now=100.0)
        task = ap.update_task_step_state(task, "Inspect", "done", now=101.0)
        task = ap.update_task_step_state(task, "Fix", "in_progress", now=102.0)
        block = ap.render("12:00:00", "fallback", dirty=55, baseline=660, stuck=[], task=task)
        self.assertIn("Task   [██████████░░░░░░░░░░] 50%   1/2 steps done", block)
        self.assertIn("current: Fix", block)

    def test_chat_task_blocked_adds_plain_stuck_reason(self):
        task = ap.start_task_state("chat task", ["Inspect", "Fix"], now=100.0)
        task = ap.update_task_step_state(task, "Fix", "blocked", now=101.0)
        self.assertEqual(ap.chat_task_stuck_reasons(task), ["current chat task is blocked at Fix"])

    def test_stale_chat_task_expires(self):
        task = ap.start_task_state("chat task", ["Inspect"], now=100.0)
        self.assertIsNone(ap.active_task_or_none(task, now=100.0 + 46 * 60))

    def test_header_and_no_stall_line(self):
        block = ap.render("12:00:00", "working", dirty=5, baseline=10, stuck=[])
        self.assertIn("[PROGRESS · 12:00:00 · working]", block)
        self.assertIn("Stuck? no — nothing stalled", block)
        self.assertIn("5 files left to commit (started at 10)", block)
        self.assertIn("50%", block)

    def test_no_baseline_uses_uncommitted_line(self):
        block = ap.render("01:02:03", "lbl", dirty=4, baseline=0, stuck=[])
        self.assertIn("Task   no active chat task", block)
        self.assertIn("Repo   4 uncommitted files total", block)

    def test_stall_line_joins_reasons(self):
        block = ap.render("00:00:00", "lbl", dirty=1, baseline=2, stuck=["a", "b"])
        self.assertIn("Stuck? YES — a; b", block)
