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


class _FakeResolver:
    def __init__(self, mut_floor):
        self._f = mut_floor

    def tier_mutation_floor(self, path):  # noqa: ARG002
        return self._f


# A realistic mutmut v2 progress/summary line.
_GOOD = "⠼ 20/20  🎉 19 🫥 0 ⏰ 0 🤔 0 🙁 1 🔇 0"
_BAD = "⠼ 20/20  🎉 12 🫥 0 ⏰ 1 🤔 0 🙁 7 🔇 0"


class ParseKillRateTests(unittest.TestCase):
    def test_parses_high_kill_rate(self) -> None:
        # 19 killed / (19+1) = 95%
        self.assertAlmostEqual(hook._parse_kill_rate(_GOOD), 95.0, places=1)

    def test_parses_low_kill_rate(self) -> None:
        # 12 killed / (12+7+1) = 60%
        self.assertAlmostEqual(hook._parse_kill_rate(_BAD), 60.0, places=1)

    def test_no_mutants_returns_none(self) -> None:
        self.assertIsNone(hook._parse_kill_rate("nothing to mutate"))


class MainTests(unittest.TestCase):
    def test_no_staged_passes(self) -> None:
        with patch.object(hook, "_staged_python_files", return_value=[]):
            self.assertEqual(hook.main(), 0)

    def test_above_floor_passes(self) -> None:
        with patch.object(hook, "_staged_python_files",
                          return_value=["backend/apps/x/foo.py"]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(90)), \
             patch.object(hook, "_run_mutmut", return_value=(95.0, _GOOD)):
            self.assertEqual(hook.main(), 0)

    def test_below_floor_blocks(self) -> None:
        with patch.object(hook, "_staged_python_files",
                          return_value=["backend/apps/x/foo.py"]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(90)), \
             patch.object(hook, "_run_mutmut", return_value=(60.0, _BAD)):
            self.assertEqual(hook.main(), 1)

    def test_floor_capped_at_ninety(self) -> None:
        # tier1 mutation floor is 100 in config, but the ceiling caps it at 90,
        # so a 92% kill rate must PASS.
        with patch.object(hook, "_staged_python_files",
                          return_value=["backend/apps/x/foo.py"]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(100)), \
             patch.object(hook, "_run_mutmut", return_value=(92.0, _GOOD)):
            self.assertEqual(hook.main(), 0)

    def test_unmeasurable_blocks(self) -> None:
        with patch.object(hook, "_staged_python_files",
                          return_value=["backend/apps/x/foo.py"]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(90)), \
             patch.object(hook, "_run_mutmut", return_value=(None, "docker down")):
            self.assertEqual(hook.main(), 1)

    def test_zero_floor_skips(self) -> None:
        with patch.object(hook, "_staged_python_files",
                          return_value=["backend/apps/x/foo.py"]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(0)):
            self.assertEqual(hook.main(), 0)

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
