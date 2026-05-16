#!/usr/bin/env python3
"""Tests for check-junk-files.py (Rule H.H2)."""

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
        "check_junk_files", here / "check-junk-files.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckJunkFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_services_report_json_is_blocked(self):
        """Rule L - go-mutesting writes services/<name>/report.json which
        is a build artefact, not source."""
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=["services/streamd/report.json"]), \
             mock.patch.object(sys, "stderr", StringIO()) as err:
            self.assertEqual(self.hook.main(), 2)
            self.assertIn("services/streamd/report.json", err.getvalue())

    def test_cover_out_files_are_blocked(self):
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=["services/streamd/internal/broker/cover.out"]), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_bench_txt_is_blocked(self):
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=["services/streamd/bench.txt"]), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_compile_lock_is_blocked(self):
        """The /opt/xf/compiled/.compile.lock file should never reach git."""
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=[".compile.lock"]), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_clean_passes(self):
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=["backend/apps/x.py"]):
            self.assertEqual(self.hook.main(), 0)

    def test_dotenv_blocked(self):
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=[".env"]), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_sqlite3_blocked(self):
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=["db.sqlite3"]), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_log_blocked(self):
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=["server.log"]), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_credentials_json_blocked(self):
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=["secrets/my-credentials.json"]), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_ds_store_blocked(self):
        with mock.patch.object(self.hook, "_staged_files",
                               return_value=["frontend/.DS_Store"]), \
             mock.patch.object(sys, "stderr", StringIO()):
            self.assertEqual(self.hook.main(), 2)

    def test_main_emits_plain_english_fail(self):
        with mock.patch.object(self.hook, "_staged_files", return_value=[".env"]), \
             mock.patch.object(sys, "stderr", StringIO()) as err:
            self.assertEqual(self.hook.main(), 2)
            msg = err.getvalue()
            self.assertIn("FAIL", msg)
            self.assertIn("WHY", msg)
            self.assertIn("UNBLOCK", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
