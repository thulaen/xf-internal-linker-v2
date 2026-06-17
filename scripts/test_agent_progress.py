#!/usr/bin/env python3
"""Unit tests for scripts/agent_progress.py — the cross-agent progress reporter.

All logic lives in pure functions (progress_bar, percent_done, detect_stuck,
should_emit, render), so these run with no Docker, no git, and no network.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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


class ChatTaskStateTests(unittest.TestCase):
    def test_split_steps_trims_and_drops_blanks(self) -> None:
        self.assertEqual(agent_progress.split_steps(" Inspect | | Test "), ["Inspect", "Test"])

    def test_start_task_uses_safe_defaults(self) -> None:
        task = agent_progress.start_task_state("  ", [" ", ""], now=10.0)
        self.assertEqual(task["title"], "working")
        self.assertEqual(task["steps"], [{"name": "Work", "status": "in_progress"}])
        self.assertFalse(task["finished"])

    def test_finished_and_missing_tasks_are_inactive(self) -> None:
        task = agent_progress.start_task_state("done", ["Finish"], now=10.0)
        task["finished"] = True
        self.assertIsNone(agent_progress.active_task_or_none(task, now=11.0))
        self.assertIsNone(agent_progress.active_task_or_none({}, now=11.0))

    def test_task_with_bad_updated_time_is_inactive(self) -> None:
        task = agent_progress.start_task_state("bad", ["Inspect"], now=10.0)
        task["updated_at"] = 0
        self.assertIsNone(agent_progress.active_task_or_none(task, now=11.0))

    def test_update_task_adds_new_step_and_resets_old_active_step(self) -> None:
        task = agent_progress.start_task_state("meter", ["Inspect"], now=10.0)
        task = agent_progress.update_task_step_state(task, "Report", "in_progress", now=11.0)
        self.assertEqual(task["steps"][0]["status"], "pending")
        self.assertEqual(task["steps"][1], {"name": "Report", "status": "in_progress"})

    def test_update_task_rejects_bad_status_and_empty_step(self) -> None:
        task = agent_progress.start_task_state("meter", ["Inspect"], now=10.0)
        with self.assertRaises(ValueError):
            agent_progress.update_task_step_state(task, "Inspect", "bad", now=11.0)
        with self.assertRaises(ValueError):
            agent_progress.update_task_step_state(task, " ", "done", now=11.0)

    def test_finish_task_marks_all_steps_done(self) -> None:
        task = agent_progress.start_task_state("meter", ["Inspect", "Report"], now=10.0)
        task = agent_progress.finish_task_state(task, now=12.0)
        self.assertTrue(task["finished"])
        self.assertEqual(agent_progress.chat_task_counts(task), (2, 2))
        self.assertEqual(agent_progress.chat_task_current_step(task), "complete")

    def test_empty_task_counts_and_current_step_are_safe(self) -> None:
        self.assertEqual(agent_progress.chat_task_counts({"steps": []}), (0, 0))
        self.assertEqual(agent_progress.chat_task_current_step({"steps": []}), "complete")
        self.assertEqual(agent_progress.chat_task_stuck_reasons(None), [])


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

    def test_keepalive_idle_helper_is_not_stuck(self) -> None:
        # A warm helper whose command just idles (e.g. `tail -f /dev/null`) sits
        # at ~0% CPU by design; it must never be reported as a stalled job.
        rows = [{
            "name": "xf_linker_frontend_mutation_tools",
            "up_minutes": 780, "cpu_percent": 0.0, "keepalive": True,
        }]
        self.assertEqual(agent_progress.detect_stuck(rows, None), [])

    def test_keepalive_helper_still_reports_held_lock(self) -> None:
        # The idle helper itself isn't flagged, but a genuinely wedged run
        # (an old held mutation lock) is still surfaced.
        rows = [{
            "name": "xf_linker_frontend_mutation_tools",
            "up_minutes": 780, "cpu_percent": 0.0, "keepalive": True,
        }]
        stuck = agent_progress.detect_stuck(rows, 9 * 60)
        self.assertEqual(len(stuck), 1)
        self.assertIn("lock", stuck[0])

    def test_non_keepalive_low_cpu_long_uptime_still_stuck(self) -> None:
        # A real job-runner (not a keepalive) idling at 0% CPU is still a stall.
        rows = [{
            "name": "xf-mutation-run",
            "up_minutes": 11, "cpu_percent": 0.0, "keepalive": False,
        }]
        self.assertEqual(len(agent_progress.detect_stuck(rows, None)), 1)


class IsKeepaliveCommandTests(unittest.TestCase):
    def test_tail_dev_null_is_keepalive(self) -> None:
        self.assertTrue(agent_progress.is_keepalive_command("sh -lc 'tail -f /dev/null'"))

    def test_sleep_infinity_is_keepalive(self) -> None:
        self.assertTrue(agent_progress.is_keepalive_command("sleep infinity"))

    def test_real_command_is_not_keepalive(self) -> None:
        self.assertFalse(agent_progress.is_keepalive_command("npx stryker run"))

    def test_empty_command_is_not_keepalive(self) -> None:
        self.assertFalse(agent_progress.is_keepalive_command(""))


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
    def test_shows_chat_task_before_repo_count(self) -> None:
        task = agent_progress.start_task_state(
            "Google setup proof",
            ["Inspect", "Fix", "Test", "Report", "Finish"],
            now=1000.0,
        )
        out = agent_progress.render(
            "12:00:00", "working", dirty=55, baseline=660, stuck=[], task=task
        )
        self.assertIn("[PROGRESS · 12:00:00 · Google setup proof]", out)
        self.assertIn("Task   [░░░░░░░░░░░░░░░░░░░░] 0%   0/5 steps done", out)
        self.assertIn("current: Inspect", out)
        self.assertIn("Repo   55 uncommitted files total", out)
        self.assertNotIn("files left to commit", out)

    def test_completed_chat_task_steps_move_percent(self) -> None:
        task = agent_progress.start_task_state("meter", ["Inspect", "Fix", "Test"], now=1000.0)
        task = agent_progress.update_task_step_state(task, "Inspect", "done", now=1001.0)
        task = agent_progress.update_task_step_state(task, "Fix", "done", now=1002.0)
        task = agent_progress.update_task_step_state(task, "Test", "in_progress", now=1003.0)
        out = agent_progress.render(
            "12:00:00", "working", dirty=55, baseline=660, stuck=[], task=task
        )
        self.assertIn("67%   2/3 steps done", out)
        self.assertIn("current: Test", out)

    def test_blocked_chat_task_reports_stuck(self) -> None:
        task = agent_progress.start_task_state("meter", ["Inspect", "Fix"], now=1000.0)
        task = agent_progress.update_task_step_state(task, "Fix", "blocked", now=1001.0)
        stuck = agent_progress.chat_task_stuck_reasons(task)
        out = agent_progress.render(
            "12:00:00", "working", dirty=55, baseline=660, stuck=stuck, task=task
        )
        self.assertIn("Task   [░░░░░░░░░░░░░░░░░░░░] 0%   0/2 steps done", out)
        self.assertIn("Stuck? YES — current chat task is blocked at Fix", out)

    def test_stale_chat_task_is_not_rendered(self) -> None:
        task = agent_progress.start_task_state("old task", ["Inspect"], now=1000.0)
        self.assertIsNone(agent_progress.active_task_or_none(task, now=1000.0 + 46 * 60))

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


class IoHelperTests(unittest.TestCase):
    def test_git_dirty_count_counts_nonblank_status_rows(self) -> None:
        result = SimpleNamespace(stdout=" M a.py\n\n?? b.py\n")
        with patch.object(agent_progress.subprocess, "run", return_value=result):
            self.assertEqual(agent_progress._git_dirty_count(), 2)

    def test_docker_quality_containers_returns_empty_when_no_targets(self) -> None:
        result = SimpleNamespace(stdout="web\tUp 9 minutes\tpython app.py\n")
        with patch.object(agent_progress.subprocess, "run", return_value=result):
            self.assertEqual(agent_progress._docker_quality_containers(), [])

    def test_docker_quality_containers_parses_targets_and_cpu(self) -> None:
        outputs = [
            SimpleNamespace(
                stdout=(
                    "xf-mutation\tUp 11 minutes\tpython -m mutmut\n"
                    "xf-quality\tUp 2 hours\tsh -lc 'tail -f /dev/null'\n"
                )
            ),
            SimpleNamespace(stdout="xf-mutation\t2.50%\nxf-quality\t0.00%\n"),
        ]
        with patch.object(agent_progress.subprocess, "run", side_effect=outputs):
            rows = agent_progress._docker_quality_containers()
        self.assertEqual(rows[0]["name"], "xf-mutation")
        self.assertEqual(rows[0]["cpu_percent"], 2.5)
        self.assertEqual(rows[1]["up_minutes"], 120)
        self.assertTrue(rows[1]["keepalive"])

    def test_minutes_from_running_for_handles_common_units(self) -> None:
        self.assertEqual(agent_progress._minutes_from_running_for("Up 2 hours"), 120)
        self.assertEqual(agent_progress._minutes_from_running_for("Up 30 seconds"), 0.5)
        self.assertEqual(agent_progress._minutes_from_running_for("Up 7 minutes"), 7)
        self.assertEqual(agent_progress._minutes_from_running_for("starting"), 0)

    def test_lock_age_handles_missing_and_present_lock(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            lock = Path(d) / "lock"
            original = agent_progress.MUTATION_LOCK
            agent_progress.MUTATION_LOCK = lock
            try:
                self.assertIsNone(agent_progress._lock_age_seconds(now=100.0))
                lock.write_text("locked", encoding="utf-8")
                os.utime(lock, (150.0, 150.0))
                self.assertGreaterEqual(agent_progress._lock_age_seconds(now=200.0), 0)
            finally:
                agent_progress.MUTATION_LOCK = original

    def test_read_state_returns_empty_for_missing_or_bad_json(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            state_path = Path(d) / "state.json"
            original = agent_progress.STATE_PATH
            agent_progress.STATE_PATH = state_path
            try:
                self.assertEqual(agent_progress._read_state(), {})
                state_path.write_text("{bad", encoding="utf-8")
                self.assertEqual(agent_progress._read_state(), {})
            finally:
                agent_progress.STATE_PATH = original

    def test_task_state_read_write_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            task_path = Path(d) / "task.json"
            original = agent_progress.TASK_STATE_PATH
            agent_progress.TASK_STATE_PATH = task_path
            try:
                agent_progress._write_task_state({"title": "x"})
                self.assertEqual(agent_progress._read_task_state(), {"title": "x"})
            finally:
                agent_progress.TASK_STATE_PATH = original

    def test_write_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            state_path = Path(d) / "state.json"
            original = agent_progress.STATE_PATH
            agent_progress.STATE_PATH = state_path
            try:
                agent_progress._write_state({"baseline": 3})
                self.assertEqual(
                    json.loads(state_path.read_text(encoding="utf-8")),
                    {"baseline": 3},
                )
            finally:
                agent_progress.STATE_PATH = original

    def test_notify_stuck_swallows_subprocess_errors(self) -> None:
        timeout = subprocess.TimeoutExpired("x", 1)
        with patch.object(agent_progress.subprocess, "run", side_effect=timeout):
            agent_progress._notify_stuck(["blocked"])


class CommandLineTests(unittest.TestCase):
    def test_build_parser_accepts_task_arguments(self) -> None:
        args = agent_progress._build_parser().parse_args(
            ["--start-task", "task", "--steps", "A|B", "--force"]
        )
        self.assertEqual(args.start_task, "task")
        self.assertEqual(args.steps, "A|B")
        self.assertTrue(args.force)

    def test_baseline_from_state_prefers_argument_then_state_then_dirty(self) -> None:
        parser = agent_progress._build_parser()
        self.assertEqual(
            agent_progress._baseline_from_state(parser.parse_args(["--baseline", "7"]), {}, 3),
            7,
        )
        self.assertEqual(
            agent_progress._baseline_from_state(parser.parse_args([]), {"baseline": 5}, 3),
            5,
        )
        self.assertEqual(agent_progress._baseline_from_state(parser.parse_args([]), {}, 3), 3)

    def test_apply_task_args_start_update_and_finish(self) -> None:
        parser = agent_progress._build_parser()
        args = parser.parse_args(["--start-task", "task", "--steps", "A|B"])
        task, display, changed = agent_progress._apply_task_args(args, {}, now=10.0)
        self.assertTrue(changed)
        self.assertEqual(display["title"], "task")

        args = parser.parse_args(["--step", "A", "--status", "done"])
        task, display, changed = agent_progress._apply_task_args(args, task, now=11.0)
        self.assertTrue(changed)
        self.assertEqual(agent_progress.chat_task_counts(display), (1, 2))

        args = parser.parse_args(["--finish-task"])
        task, display, changed = agent_progress._apply_task_args(args, task, now=12.0)
        self.assertTrue(changed)
        self.assertTrue(display["finished"])

    def test_apply_task_args_can_create_task_from_step_without_existing_state(self) -> None:
        parser = agent_progress._build_parser()
        args = parser.parse_args(["--label", "fallback", "--step", "Only"])
        _task, display, changed = agent_progress._apply_task_args(args, {}, now=10.0)
        self.assertTrue(changed)
        self.assertEqual(display["title"], "fallback")
        self.assertEqual(display["steps"][0]["name"], "Only")

    def test_main_writes_state_and_prints_when_forced(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            original_paths = (
                agent_progress.STATE_PATH,
                agent_progress.STATUS_PATH,
                agent_progress.TASK_STATE_PATH,
            )
            agent_progress.STATE_PATH = Path(d) / "state.json"
            agent_progress.STATUS_PATH = Path(d) / "latest.txt"
            agent_progress.TASK_STATE_PATH = Path(d) / "task.json"
            argv = [
                "agent_progress.py",
                "--start-task",
                "task",
                "--steps",
                "A|B",
                "--force",
            ]
            try:
                with patch.object(sys, "argv", argv), \
                     patch.object(agent_progress, "_git_dirty_count", return_value=4), \
                     patch.object(agent_progress, "_docker_quality_containers", return_value=[]), \
                     patch.object(agent_progress, "_lock_age_seconds", return_value=None), \
                     patch.object(agent_progress.time, "time", return_value=1000.0), \
                     patch.object(agent_progress.time, "localtime", return_value=time_tuple()), \
                     patch("builtins.print") as fake_print:
                    self.assertEqual(agent_progress.main(), 0)
                self.assertIn("task", agent_progress.STATUS_PATH.read_text(encoding="utf-8"))
                self.assertTrue(agent_progress.TASK_STATE_PATH.exists())
                fake_print.assert_called_once()
            finally:
                (
                    agent_progress.STATE_PATH,
                    agent_progress.STATUS_PATH,
                    agent_progress.TASK_STATE_PATH,
                ) = original_paths

    def test_main_background_notifies_stuck_without_printing(self) -> None:
        argv = ["agent_progress.py", "--background", "--notify-on-stuck"]
        with patch.object(sys, "argv", argv), \
             patch.object(agent_progress, "_read_state", return_value={}), \
             patch.object(agent_progress, "_read_task_state", return_value={}), \
             patch.object(agent_progress, "_git_dirty_count", return_value=4), \
             patch.object(agent_progress, "_docker_quality_containers", return_value=[]), \
             patch.object(
                 agent_progress,
                 "_lock_age_seconds",
                 return_value=agent_progress.STUCK_LOCK_MINUTES * 60,
             ), \
             patch.object(agent_progress, "_write_status_file"), \
             patch.object(agent_progress, "_notify_stuck") as notify, \
             patch("builtins.print") as fake_print:
            self.assertEqual(agent_progress.main(), 0)
        notify.assert_called_once()
        fake_print.assert_not_called()

    def test_main_quiet_when_throttled(self) -> None:
        argv = ["agent_progress.py"]
        with patch.object(sys, "argv", argv), \
             patch.object(
                 agent_progress,
                 "_read_state",
                 return_value={"last_emitted_at": 1000.0},
             ), \
             patch.object(agent_progress, "_read_task_state", return_value={}), \
             patch.object(agent_progress, "_git_dirty_count", return_value=4), \
             patch.object(agent_progress, "_docker_quality_containers", return_value=[]), \
             patch.object(agent_progress, "_lock_age_seconds", return_value=None), \
             patch.object(agent_progress.time, "time", return_value=1001.0), \
             patch.object(agent_progress, "_write_status_file"), \
             patch("builtins.print") as fake_print:
            self.assertEqual(agent_progress.main(), 0)
        fake_print.assert_not_called()


def time_tuple() -> time.struct_time:
    return time.struct_time((2026, 6, 16, 12, 0, 0, 1, 167, -1))


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
