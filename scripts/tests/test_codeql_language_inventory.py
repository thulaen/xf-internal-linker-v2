"""Convention tests for scripts/codeql_language_inventory.py.

BDD:
  Given a list of repo-relative file paths
  When detect_languages / should_scan_path / build_mode_for_language run
  Then the detected language set, scan-skip decisions, and build modes match
       exact expected values so mutation survivors on the changed lines die.

detect_languages is called with an explicit path list, so git is never invoked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cli = _load("codeql_language_inventory", "codeql_language_inventory.py")


class TestShouldScanPath(TestCase):
    def test_handwritten_python_scanned(self):
        self.assertTrue(cli.should_scan_path("backend/apps/api/views.py"))

    def test_skip_part_node_modules(self):
        self.assertFalse(cli.should_scan_path("frontend/node_modules/x/index.js"))

    def test_skip_migrations_under_backend_apps(self):
        self.assertFalse(cli.should_scan_path("backend/apps/audit/migrations/0001_x.py"))

    def test_generated_pb2_skipped(self):
        self.assertFalse(cli.should_scan_path("backend/apps/realtime/api_pb2.py"))

    def test_generated_pb_go_skipped(self):
        self.assertFalse(cli.should_scan_path("services/streamd/api/gen/api.pb.go"))

    def test_backslash_path_normalised(self):
        self.assertFalse(cli.should_scan_path("frontend\\node_modules\\a.js"))


class TestDetectLanguages(TestCase):
    def test_supported_languages_in_canonical_order(self):
        inv = cli.detect_languages(["a.py", "b.ts", "c.go", "d.cpp"])
        self.assertEqual(inv.languages, ["c-cpp", "go", "python", "javascript-typescript"])

    def test_unsupported_reported_sorted(self):
        inv = cli.detect_languages(["x.hs", "y.sql"])
        self.assertEqual(inv.languages, [])
        self.assertEqual(inv.unsupported_present, ["haskell", "sql"])

    def test_skipped_paths_excluded(self):
        inv = cli.detect_languages(["node_modules/a.js", "real.py"])
        self.assertEqual(inv.languages, ["python"])

    def test_unknown_extension_ignored(self):
        inv = cli.detect_languages(["README.md", "data.json"])
        self.assertEqual(inv.languages, [])
        self.assertEqual(inv.unsupported_present, [])


class TestBuildMode(TestCase):
    def test_c_cpp_is_manual(self):
        self.assertEqual(cli.build_mode_for_language("c-cpp"), "manual")

    def test_go_is_manual(self):
        self.assertEqual(cli.build_mode_for_language("go"), "manual")

    def test_python_is_none(self):
        self.assertEqual(cli.build_mode_for_language("python"), "none")

    def test_js_is_none(self):
        self.assertEqual(cli.build_mode_for_language("javascript-typescript"), "none")
