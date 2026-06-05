"""Tests for the scoped mutation-testing gate."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("check-scoped-mutation.py")
spec = importlib.util.spec_from_file_location("check_scoped_mutation", MODULE_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class _FakeCov:
    """Stand-in for the coverage hook: returns canned changed-line sets."""

    def __init__(self, changed):
        self._changed = changed

    def _changed_lines(self, path):  # noqa: ARG002
        return self._changed


# Raw helper output the diff-scope runner prints. A completed run ends with
# DONE (or NO_CHANGED_MUTANTS) and lists each survivor on its own `LIVE ` line.
_CLEAN = "scanning\nNO_CHANGED_MUTANTS\n"
_SURVIVORS = "scanning\nLIVE apps/x/foo.py:12 (m3)\nLIVE apps/x/foo.py:14 (m9)\nDONE\n"
_INCOMPLETE = "scanning\ncontainer crashed before any verdict\n"


class ParseLiveTests(unittest.TestCase):
    def test_completed_run_with_survivors_lists_them(self) -> None:
        self.assertEqual(
            hook._parse_live(_SURVIVORS),
            ["apps/x/foo.py:12 (m3)", "apps/x/foo.py:14 (m9)"],
        )

    def test_completed_run_with_no_survivors_is_empty_list(self) -> None:
        self.assertEqual(hook._parse_live(_CLEAN), [])

    def test_incomplete_run_returns_none(self) -> None:
        self.assertIsNone(hook._parse_live(_INCOMPLETE))


class MainTests(unittest.TestCase):
    def _patches(self, *, changed, run_mutmut):
        """Patch the seams main() uses: staged files, the coverage hook
        (changed-line source), the run lock, and the mutation runner.

        `changed` is the set returned by cov._changed_lines (or None for a
        brand-new file). `run_mutmut` is the (live, raw) tuple the runner yields.
        """
        return (
            patch.object(hook, "_staged_python_files",
                         return_value=["backend/apps/x/foo.py"]),
            patch.object(hook, "_load_coverage_hook",
                         return_value=_FakeCov(changed)),
            patch.object(hook, "_acquire_lock_or_heal", return_value=0),
            patch.object(hook, "_run_mutmut", return_value=run_mutmut),
        )

    def test_no_staged_passes(self) -> None:
        with patch.object(hook, "_staged_python_files", return_value=[]):
            self.assertEqual(hook.main(), 0)

    def test_no_changed_lines_skips(self) -> None:
        # Only comment / blank edits → no changed code → nothing to mutate-check.
        p_staged, p_cov, p_lock, p_run = self._patches(
            changed=set(), run_mutmut=([], _CLEAN))
        with p_staged, p_cov, p_lock:
            self.assertEqual(hook.main(), 0)

    def test_no_survivors_passes(self) -> None:
        p_staged, p_cov, p_lock, p_run = self._patches(
            changed={12}, run_mutmut=([], _CLEAN))
        with p_staged, p_cov, p_lock, p_run:
            self.assertEqual(hook.main(), 0)

    def test_survivor_on_changed_line_blocks(self) -> None:
        p_staged, p_cov, p_lock, p_run = self._patches(
            changed={12}, run_mutmut=(["apps/x/foo.py:12 (m3)"], _SURVIVORS))
        with p_staged, p_cov, p_lock, p_run:
            self.assertEqual(hook.main(), 1)

    def test_unmeasurable_blocks(self) -> None:
        # live is None → mutation could not run → fail closed.
        p_staged, p_cov, p_lock, p_run = self._patches(
            changed={12}, run_mutmut=(None, "docker down"))
        with p_staged, p_cov, p_lock, p_run:
            self.assertEqual(hook.main(), 1)

    def test_live_lock_aborts(self) -> None:
        # A live competing run holds the lock → main returns the abort code.
        with patch.object(hook, "_staged_python_files",
                          return_value=["backend/apps/x/foo.py"]), \
             patch.object(hook, "_load_coverage_hook",
                          return_value=_FakeCov({12})), \
             patch.object(hook, "_acquire_lock_or_heal", return_value=2):
            self.assertEqual(hook.main(), 2)

    def test_fail_message_has_three_parts(self) -> None:
        with patch.object(hook.sys.stderr, "write") as werr:
            hook._fail("detail")
        written = "".join(c.args[0] for c in werr.call_args_list)
        self.assertIn("FAIL check-scoped-mutation", written)
        self.assertIn("WHY:", written)
        self.assertIn("UNBLOCK:", written)


class SnapshotRestoreTests(unittest.TestCase):
    def test_restore_rewrites_changed_file(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.py"
            p.write_bytes(b"original")
            snap = hook._snapshot([p])
            p.write_bytes(b"MUTATED")  # simulate a left-over mutant
            hook._restore(snap)
            self.assertEqual(p.read_bytes(), b"original")

    def test_restore_noop_when_unchanged(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.py"
            p.write_bytes(b"same")
            snap = hook._snapshot([p])
            hook._restore(snap)
            self.assertEqual(p.read_bytes(), b"same")


class PurgeRemoteCacheTests(unittest.TestCase):
    """The remote source sync must purge any stale .mutmut-cache after extract.

    A persistent named volume keeps `.mutmut-cache` between runs; reusing it
    makes the remote report different survivors than a clean local run. The sync
    must purge it after a SUCCESSFUL extract and skip the purge when the extract
    itself failed.
    """

    def test_sync_purges_stale_cache_after_successful_extract(self) -> None:
        calls = []
        with patch.object(hook, "_pipe_tar_into", return_value=None), patch.object(
            hook, "_purge_remote_mutmut_cache", side_effect=lambda ctx, env: calls.append(ctx)
        ):
            err = hook._sync_source_to_mint("dell", {})
        self.assertIsNone(err)
        self.assertEqual(calls, ["dell"])

    def test_sync_skips_purge_when_extract_fails(self) -> None:
        calls = []
        with patch.object(hook, "_pipe_tar_into", return_value="extract boom"), patch.object(
            hook, "_purge_remote_mutmut_cache", side_effect=lambda ctx, env: calls.append(ctx)
        ):
            err = hook._sync_source_to_mint("dell", {})
        self.assertEqual(err, "extract boom")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
