#!/usr/bin/env python3
"""Tests for check-debug-code.py (Rule H.H1)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock


def _load_hook():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "check_debug_code", here / "check-debug-code.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckDebugCodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def _scan_text(self, suffix: str, text: str):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / f"sample{suffix}"
            f.write_text(text, encoding="utf-8")
            return self.hook._scan(f)

    def test_no_files_passes(self):
        with mock.patch.object(self.hook, "_staged_files", return_value=[]):
            self.assertEqual(self.hook.main(), 0)

    def test_pdb_set_trace_detected(self):
        hits = self._scan_text(".py", "def f():\n    import pdb; pdb.set_trace()\n")
        self.assertGreaterEqual(len(hits), 1)

    def test_breakpoint_detected(self):
        hits = self._scan_text(".py", "def f():\n    breakpoint()\n")
        self.assertEqual(len(hits), 1)

    def test_top_level_debug_true_detected(self):
        hits = self._scan_text(".py", "DEBUG = True\n")
        self.assertEqual(len(hits), 1)

    def test_console_log_in_ts_detected(self):
        hits = self._scan_text(".ts", "function f() { console.log('x'); }\n")
        self.assertEqual(len(hits), 1)

    def test_debugger_in_ts_detected(self):
        hits = self._scan_text(".ts", "function f() {\n    debugger ;\n}\n")
        self.assertEqual(len(hits), 1)

    def test_main_emits_plain_english_fail(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.py"
            path.write_text("import pdb\npdb.set_trace()\n", encoding="utf-8")
            with mock.patch.object(self.hook, "REPO_ROOT", Path(td)), \
                 mock.patch.object(self.hook, "_staged_files", return_value=[path]), \
                 mock.patch.object(sys, "stderr", StringIO()) as err:
                self.assertEqual(self.hook.main(), 2)
                msg = err.getvalue()
                self.assertIn("FAIL", msg)
                self.assertIn("WHY", msg)
                self.assertIn("UNBLOCK", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
