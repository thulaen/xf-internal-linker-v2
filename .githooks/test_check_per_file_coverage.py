"""Tests for the per-staged-file coverage floor gate."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("check-per-file-coverage.py")
spec = importlib.util.spec_from_file_location("check_per_file_coverage", MODULE_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class _FakeResolver:
    def __init__(self, floor):
        self._floor = floor

    def tier_line_floor(self, path):  # noqa: ARG002 - signature match
        return self._floor


_PROD = "backend/apps/x/foo.py"
_TEST = "backend/apps/x/tests_foo.py"


class CheckPerFileCoverageTests(unittest.TestCase):
    def test_no_staged_files_passes(self) -> None:
        with patch.object(hook, "_staged_files", return_value=[]):
            self.assertEqual(hook.main(), 0)

    def test_below_floor_blocks(self) -> None:
        # A changed line (10) is in the file's missing-coverage set, so the
        # diff-coverage gate must block.
        with patch.object(hook, "_staged_files", return_value=[_PROD]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(90)), \
             patch.object(hook, "_test_paths_for", return_value=[_TEST]), \
             patch.object(hook, "_changed_lines", return_value={10}), \
             patch.object(hook, "_measure_missing_map",
                          return_value={_PROD: {10}}):
            self.assertEqual(hook.main(), 1)

    def test_at_floor_passes(self) -> None:
        # The changed line (10) is covered (missing set is empty) → pass.
        with patch.object(hook, "_staged_files", return_value=[_PROD]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(90)), \
             patch.object(hook, "_test_paths_for", return_value=[_TEST]), \
             patch.object(hook, "_changed_lines", return_value={10}), \
             patch.object(hook, "_measure_missing_map",
                          return_value={_PROD: set()}):
            self.assertEqual(hook.main(), 0)

    def test_no_test_file_blocks(self) -> None:
        # No test discovered → file is unmeasurable (None) and the gate blocks
        # with a "no test found" verdict.
        with patch.object(hook, "_staged_files", return_value=[_PROD]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(90)), \
             patch.object(hook, "_test_paths_for", return_value=[]), \
             patch.object(hook, "_measure_missing_map",
                          return_value={_PROD: None}):
            self.assertEqual(hook.main(), 1)

    def test_unmeasurable_blocks(self) -> None:
        # Tests exist but coverage could not be measured (None) → block.
        with patch.object(hook, "_staged_files", return_value=[_PROD]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(90)), \
             patch.object(hook, "_test_paths_for", return_value=[_TEST]), \
             patch.object(hook, "_measure_missing_map",
                          return_value={_PROD: None}):
            self.assertEqual(hook.main(), 1)

    def test_smoke_tier_skipped(self) -> None:
        # Floor of 0 means smoke tier — the file is skipped and the gate passes.
        with patch.object(hook, "_staged_files", return_value=[_PROD]), \
             patch.object(hook, "_load_resolver", return_value=_FakeResolver(0)):
            self.assertEqual(hook.main(), 0)

    def test_fail_message_has_three_parts(self) -> None:
        with patch.object(hook.sys.stderr, "write") as werr:
            hook._fail("detail")
        written = "".join(c.args[0] for c in werr.call_args_list)
        self.assertIn("FAIL check-per-file-coverage", written)
        self.assertIn("WHY:", written)
        self.assertIn("UNBLOCK:", written)


if __name__ == "__main__":
    unittest.main()
