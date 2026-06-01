"""Crash-safety tests for check-scoped-mutation.py (TASK #10).

A killed commit must NEVER leave mutmut looping or strand mutants in the working
tree. These tests exercise the lockfile + orphan-container sweep + index-restore
backstop with every Docker / git / process boundary mocked — no real mutation,
no real Docker, no real git checkout runs here.

Covered behaviours:
- stale lock (dead pid)  -> self-heal: orphan sweep + index restore, run proceeds
- live lock              -> abort with exit code 2, no heal, no run
- atexit/crash cleanup   -> restores staged files from the git index
- orphan-container sweep -> finds by label, force-removes locally + on context
- timeout backstop       -> force-removes the named daemon-side container
"""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import call, patch

_HOOK = Path(__file__).resolve().parent / "check-scoped-mutation.py"
_spec = importlib.util.spec_from_file_location("check_scoped_mutation_safety", _HOOK)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class PidIsLiveTests(unittest.TestCase):
    def test_non_positive_pid_is_never_live(self):
        self.assertFalse(mod._pid_is_live(0))
        self.assertFalse(mod._pid_is_live(-5))

    def test_posix_live_pid_via_kill_zero(self):
        with (
            patch.object(mod.os, "name", "posix"),
            patch.object(mod.os, "kill", return_value=None) as mk,
        ):
            self.assertTrue(mod._pid_is_live(1234))
        mk.assert_called_once_with(1234, 0)

    def test_posix_dead_pid_raises_process_lookup(self):
        with (
            patch.object(mod.os, "name", "posix"),
            patch.object(mod.os, "kill", side_effect=ProcessLookupError),
        ):
            self.assertFalse(mod._pid_is_live(1234))

    def test_windows_live_pid_when_in_tasklist(self):
        with (
            patch.object(mod.os, "name", "nt"),
            patch.object(mod.subprocess, "check_output",
                         return_value="proc.exe 4321 Console 1 10,000 K\n"),
        ):
            self.assertTrue(mod._pid_is_live(4321))

    def test_windows_dead_pid_when_absent_from_tasklist(self):
        with (
            patch.object(mod.os, "name", "nt"),
            patch.object(mod.subprocess, "check_output",
                         return_value="INFO: No tasks are running.\n"),
        ):
            self.assertFalse(mod._pid_is_live(4321))


class ReadLockPidTests(unittest.TestCase):
    def test_missing_lock_returns_none(self):
        with patch.object(mod.Path, "read_text", side_effect=OSError):
            self.assertIsNone(mod._read_lock_pid())

    def test_garbage_lock_returns_none(self):
        with patch.object(mod.Path, "read_text", return_value="not-a-pid"):
            self.assertIsNone(mod._read_lock_pid())

    def test_valid_lock_returns_int(self):
        with patch.object(mod.Path, "read_text", return_value="  9988  \n"):
            self.assertEqual(mod._read_lock_pid(), 9988)


class AcquireLockOrHealTests(unittest.TestCase):
    def test_live_lock_aborts_with_exit_2_and_no_heal(self):
        with (
            patch.object(mod, "_read_lock_pid", return_value=777),
            patch.object(mod, "_pid_is_live", return_value=True),
            patch.object(mod, "_sweep_orphan_containers") as sweep,
            patch.object(mod, "_restore_from_index") as restore,
            patch.object(mod.atexit, "register") as reg,
        ):
            rc = mod._acquire_lock_or_heal(["apps/x.py"])
        self.assertEqual(rc, 2)
        sweep.assert_not_called()
        restore.assert_not_called()
        reg.assert_not_called()

    def test_stale_lock_self_heals_then_proceeds(self):
        order = []
        with (
            patch.object(mod, "_read_lock_pid", return_value=999),
            patch.object(mod, "_pid_is_live", return_value=False),
            patch.object(mod, "_sweep_orphan_containers",
                         side_effect=lambda: order.append("sweep")),
            patch.object(mod, "_restore_from_index",
                         side_effect=lambda paths: order.append(("restore", paths))),
            patch.object(mod.Path, "write_text"),
            patch.object(mod.Path, "mkdir"),
            patch.object(mod.atexit, "register"),
            patch.object(mod.signal, "signal"),
        ):
            rc = mod._acquire_lock_or_heal(["apps/x.py"])
        self.assertEqual(rc, 0)
        self.assertIn("sweep", order)
        self.assertIn(("restore", ["apps/x.py"]), order)
        self.assertEqual(mod._GUARDED_REL_PATHS, ["apps/x.py"])

    def test_no_existing_lock_skips_heal_but_arms_handlers(self):
        with (
            patch.object(mod, "_read_lock_pid", return_value=None),
            patch.object(mod, "_sweep_orphan_containers") as sweep,
            patch.object(mod, "_restore_from_index") as restore,
            patch.object(mod.Path, "write_text") as wt,
            patch.object(mod.Path, "mkdir"),
            patch.object(mod.atexit, "register") as reg,
            patch.object(mod.signal, "signal") as sig,
        ):
            rc = mod._acquire_lock_or_heal(["apps/x.py"])
        self.assertEqual(rc, 0)
        sweep.assert_not_called()       # no crashed predecessor → no heal
        restore.assert_not_called()
        wt.assert_called_once()         # current pid written
        reg.assert_called_once()        # atexit armed
        self.assertGreaterEqual(sig.call_count, 1)  # signal handlers armed


class RestoreFromIndexTests(unittest.TestCase):
    def test_each_staged_file_is_git_checked_out_from_index(self):
        calls = []

        def fake_run(cmd, **k):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(mod.subprocess, "run", side_effect=fake_run):
            mod._restore_from_index(["apps/x.py", "backend/apps/y.py"])

        self.assertEqual(calls[0], ["git", "checkout", "--", "backend/apps/x.py"])
        self.assertEqual(calls[1], ["git", "checkout", "--", "backend/apps/y.py"])

    def test_git_failure_is_swallowed_not_raised(self):
        with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError):
            mod._restore_from_index(["apps/x.py"])  # must not raise


class SweepOrphanContainersTests(unittest.TestCase):
    def test_finds_by_label_and_force_removes(self):
        def fake_check_output(cmd, **k):
            self.assertIn("label=xf.mutation=scoped", cmd)
            return "id1\nid2\n"

        removed = []

        def fake_run(cmd, **k):
            removed.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        with (
            patch.object(mod.subprocess, "check_output", side_effect=fake_check_output),
            patch.object(mod.subprocess, "run", side_effect=fake_run),
        ):
            mod._sweep_orphan_containers()

        # rm -f id1 id2 issued for both contexts (local + mint)
        self.assertTrue(all("rm" in c and "-f" in c for c in removed))
        self.assertTrue(any("id1" in c and "id2" in c for c in removed))

    def test_no_orphans_means_no_rm(self):
        with (
            patch.object(mod.subprocess, "check_output", return_value="\n"),
            patch.object(mod.subprocess, "run") as mr,
        ):
            mod._sweep_orphan_containers()
        mr.assert_not_called()

    def test_docker_missing_is_swallowed(self):
        with patch.object(mod.subprocess, "check_output", side_effect=FileNotFoundError):
            mod._sweep_orphan_containers()  # must not raise


class CrashCleanupTests(unittest.TestCase):
    def test_atexit_cleanup_restores_index_sweeps_and_drops_lock(self):
        mod._GUARDED_REL_PATHS[:] = ["apps/z.py"]
        with (
            patch.object(mod, "_restore_from_index") as restore,
            patch.object(mod, "_sweep_orphan_containers") as sweep,
            patch.object(mod.Path, "unlink") as unlink,
        ):
            mod._crash_cleanup()
        restore.assert_called_once_with(["apps/z.py"])
        sweep.assert_called_once()
        unlink.assert_called_once()

    def test_cleanup_unlink_failure_is_swallowed(self):
        mod._GUARDED_REL_PATHS[:] = []
        with (
            patch.object(mod, "_restore_from_index"),
            patch.object(mod, "_sweep_orphan_containers"),
            patch.object(mod.Path, "unlink", side_effect=OSError),
        ):
            mod._crash_cleanup()  # must not raise


class ForceRemoveContainerTests(unittest.TestCase):
    def test_local_force_remove_by_name(self):
        with patch.object(mod.subprocess, "run") as mr:
            mod._force_remove_container("xf-mutation-123")
        mr.assert_called_once()
        cmd = mr.call_args[0][0]
        self.assertEqual(cmd, ["docker", "rm", "-f", "xf-mutation-123"])

    def test_context_force_remove_includes_context_flag(self):
        with patch.object(mod.subprocess, "run") as mr:
            mod._force_remove_container("xf-mutation-mint-9", "mint")
        cmd = mr.call_args[0][0]
        self.assertEqual(cmd, ["docker", "--context", "mint", "rm", "-f", "xf-mutation-mint-9"])

    def test_docker_missing_is_swallowed(self):
        with patch.object(mod.subprocess, "run", side_effect=FileNotFoundError):
            mod._force_remove_container("x")  # must not raise


class LocalRunSafetyWiringTests(unittest.TestCase):
    def test_local_run_command_carries_name_and_label(self):
        captured = {}

        def fake_run(cmd, **k):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="DONE", stderr="")

        with (
            patch.object(mod.subprocess, "run", side_effect=fake_run),
            patch.object(mod, "_snapshot", return_value={}),
            patch.object(mod, "_restore"),
        ):
            mod._local_run(["apps/x.py"], ["apps/x.py:1"], {"apps/x.py": ["tests_x.py"]})

        cmd = captured["cmd"]
        self.assertIn("--label", cmd)
        self.assertIn("xf.mutation=scoped", cmd)
        self.assertIn("--name", cmd)

    def test_local_run_timeout_force_removes_named_container(self):
        with (
            patch.object(mod.subprocess, "run", side_effect=subprocess.TimeoutExpired("d", 1)),
            patch.object(mod, "_snapshot", return_value={}),
            patch.object(mod, "_restore"),
            patch.object(mod, "_force_remove_container") as frc,
        ):
            live, raw = mod._local_run(["apps/x.py"], ["apps/x.py:1"],
                                       {"apps/x.py": ["tests_x.py"]})
        self.assertIsNone(live)
        frc.assert_called_once()


if __name__ == "__main__":
    unittest.main()
