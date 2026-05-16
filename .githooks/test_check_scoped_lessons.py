#!/usr/bin/env python3
"""Tests for check-scoped-lessons.py (Rule D hard-block)."""

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
        "check_scoped_lessons", here / "check-scoped-lessons.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScopedLessonsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_no_code_files_passes(self):
        with mock.patch.object(self.hook, "_staged_code_files", return_value=[]):
            self.assertEqual(self.hook.main(), 0)

    def test_code_without_marker_fails_plain_english(self):
        with mock.patch.object(self.hook, "_staged_code_files",
                               return_value=["backend/apps/x.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff",
                               return_value="no marker"), \
             mock.patch.object(sys, "stderr", StringIO()) as err:
            self.assertEqual(self.hook.main(), 2)
            msg = err.getvalue()
            self.assertIn("FAIL", msg)
            self.assertIn("WHY", msg)
            self.assertIn("UNBLOCK", msg)

    def test_marker_with_zero_lessons_still_passes(self):
        marker = "[SCOPED LESSONS READ: 0 lessons in backend/apps/audit]"
        with mock.patch.object(self.hook, "_staged_code_files",
                               return_value=["backend/apps/audit/x.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff",
                               return_value=marker):
            self.assertEqual(self.hook.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
