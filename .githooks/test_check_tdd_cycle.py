#!/usr/bin/env python3
"""Tests for check-tdd-cycle.py (Rule B hard-block)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock


def _load_hook():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "check_tdd_cycle", here / "check-tdd-cycle.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TddCycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_no_source_files_passes(self):
        with mock.patch.object(self.hook, "_staged_source_files", return_value=[]):
            self.assertEqual(self.hook.main(), 0)

    def test_source_without_marker_fails_plain_english(self):
        with mock.patch.object(self.hook, "_staged_source_files",
                               return_value=["backend/apps/x.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff",
                               return_value="no marker here"), \
             mock.patch.object(sys, "stderr", StringIO()) as err:
            self.assertEqual(self.hook.main(), 2)
            msg = err.getvalue()
            self.assertIn("FAIL", msg)
            self.assertIn("WHY", msg)
            self.assertIn("UNBLOCK", msg)

    def test_with_marker_passes(self):
        marker = ("[TDD CYCLE: file=backend/apps/x.py "
                  "red=backend/apps/test_x.py:1 green=backend/apps/x.py:1 "
                  "refactor=\"ruff_clean=true\"]")
        with mock.patch.object(self.hook, "_staged_source_files",
                               return_value=["backend/apps/x.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=marker):
            self.assertEqual(self.hook.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
