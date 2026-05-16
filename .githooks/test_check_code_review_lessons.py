#!/usr/bin/env python3
"""Tests for check-code-review-lessons.py (Rule G hard-block)."""

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
        "check_code_review_lessons", here / "check-code-review-lessons.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CodeReviewLessonsTests(unittest.TestCase):
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
                               return_value="no marker here"), \
             mock.patch.object(sys, "stderr", StringIO()) as err:
            self.assertEqual(self.hook.main(), 2)
            msg = err.getvalue()
            self.assertIn("FAIL", msg)
            self.assertIn("WHY", msg)
            self.assertIn("UNBLOCK", msg)

    def test_summary_marker_with_too_few_files_fails(self):
        marker = "[CODE REVIEW LESSONS: 1 logged from 1 files; deduped 0 against prior]"
        with mock.patch.object(self.hook, "_staged_code_files",
                               return_value=["backend/apps/x.py",
                                              "backend/apps/y.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=marker), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_marker_with_n_plus_k_below_m_fails(self):
        # M is 3 (touched files in marker), but N+K is 1+1=2.
        marker = "[CODE REVIEW LESSONS: 1 logged from 3 files; deduped 1 against prior]"
        with mock.patch.object(self.hook, "_staged_code_files",
                               return_value=["backend/apps/a.py",
                                              "backend/apps/b.py",
                                              "backend/apps/c.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=marker), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_valid_marker_passes(self):
        marker = "[CODE REVIEW LESSONS: 2 logged from 2 files; deduped 0 against prior]"
        with mock.patch.object(self.hook, "_staged_code_files",
                               return_value=["backend/apps/a.py",
                                              "backend/apps/b.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=marker):
            self.assertEqual(self.hook.main(), 0)

    def test_dedup_only_passes(self):
        # All files were deduped; N+K (0+2) covers M (2).
        marker = "[CODE REVIEW LESSONS: 0 logged from 2 files; deduped 2 against prior]"
        with mock.patch.object(self.hook, "_staged_code_files",
                               return_value=["backend/apps/a.py",
                                              "backend/apps/b.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=marker):
            self.assertEqual(self.hook.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
