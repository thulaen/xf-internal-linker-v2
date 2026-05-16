#!/usr/bin/env python3
"""Tests for check-perf-proof.py (Rule A hard-block)."""

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
        "check_perf_proof", here / "check-perf-proof.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PerfProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_no_source_files_passes(self):
        with mock.patch.object(self.hook, "_staged_source_files", return_value=[]):
            self.assertEqual(self.hook.main(), 0)

    def test_source_without_handoff_fails(self):
        with mock.patch.object(self.hook, "_staged_source_files",
                               return_value=["backend/apps/x.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=""), \
             mock.patch.object(sys, "stderr", StringIO()) as err:
            self.assertEqual(self.hook.main(), 2)
            msg = err.getvalue()
            self.assertIn("FAIL", msg)
            self.assertIn("WHY", msg)
            self.assertIn("UNBLOCK", msg)

    def test_handoff_without_marker_fails(self):
        with mock.patch.object(self.hook, "_staged_source_files",
                               return_value=["backend/apps/x.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff",
                               return_value="some prose without marker"), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_handoff_with_proof_passes(self):
        marker = ("[PERFORMANCE PROOF: function=apps.x.y baseline_ns=10000 "
                  "post_ns=400 speedup=25.00x iterations=1/10]")
        with mock.patch.object(self.hook, "_staged_source_files",
                               return_value=["backend/apps/x.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=marker):
            self.assertEqual(self.hook.main(), 0)

    def test_handoff_with_exemption_passes(self):
        marker = ("[PERFORMANCE EXEMPTION: function=apps.x.y best_achieved=2.50x "
                  "iterations=10/10 reason=\"I/O bound\"]")
        with mock.patch.object(self.hook, "_staged_source_files",
                               return_value=["backend/apps/x.py"]), \
             mock.patch.object(self.hook, "_staged_handoff_diff", return_value=marker):
            self.assertEqual(self.hook.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
