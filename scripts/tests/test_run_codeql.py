"""Tests for scripts/run_codeql.py argument builders.

BDD:
  Given a language with build_mode "manual"
  When _database_create_args() runs
  Then it appends the --command build flag and omits --build-mode=none

  Given a non-rust autobuild language
  When _database_create_args() runs
  Then it appends --build-mode=none

  Given a requested-language filter
  When _selected_languages() runs
  Then it returns the detected languages intersected with the request
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "run_codeql.py"


def _load():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("run_codeql", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_codeql"] = mod
    spec.loader.exec_module(mod)
    return mod


rc = _load()


class TestDatabaseCreateArgs(TestCase):
    def test_cpp_uses_cli_language_alias(self) -> None:
        with mock.patch.object(rc, "build_mode_for_language", return_value="manual"):
            args = rc._database_create_args(
                "codeql", "c-cpp", Path("/db/cpp"), "2", "6144"
            )
        self.assertIn("--language=cpp", args)
        self.assertIn("--command=bash scripts/codeql-build-cpp.sh", args)
        self.assertNotIn("--build-mode=none", args)

    def test_python_autobuild_sets_build_mode_none(self) -> None:
        with mock.patch.object(rc, "build_mode_for_language", return_value="none"):
            args = rc._database_create_args(
                "codeql", "python", Path("/db/python"), "4", "8192"
            )
        self.assertIn("--language=python", args)
        self.assertIn("--build-mode=none", args)
        self.assertIn("--threads=4", args)
        self.assertIn("--ram=8192", args)

    def test_rust_omits_build_mode_none(self) -> None:
        with mock.patch.object(rc, "build_mode_for_language", return_value="none"):
            args = rc._database_create_args(
                "codeql", "rust", Path("/db/rust"), "2", "6144"
            )
        self.assertNotIn("--build-mode=none", args)


class TestAnalyzeArgs(TestCase):
    def test_includes_query_suite_and_sarif_output(self) -> None:
        args = rc._analyze_args(
            "codeql", "go", Path("/db/go"), Path("/out/go.sarif"), "2", "6144"
        )
        self.assertIn(rc.QUERY_SUITES["go"], args)
        self.assertIn("--format=sarifv2.1.0", args)
        self.assertIn("--output=/out/go.sarif", args)


class TestSelectedLanguages(TestCase):
    def test_no_filter_returns_all_detected(self) -> None:
        inv = mock.Mock(languages=["python", "go"])
        with mock.patch.object(rc, "detect_languages", return_value=inv):
            self.assertEqual(rc._selected_languages([]), ["python", "go"])

    def test_filter_intersects_with_detected(self) -> None:
        inv = mock.Mock(languages=["python", "go", "rust"])
        with mock.patch.object(rc, "detect_languages", return_value=inv):
            self.assertEqual(rc._selected_languages(["go", "haskell"]), ["go"])


class TestRun(TestCase):
    def test_dry_run_skips_subprocess(self) -> None:
        with mock.patch.object(rc.subprocess, "run") as run:
            rc._run(["codeql", "version"], dry_run=True)
        run.assert_not_called()

    def test_real_run_invokes_subprocess(self) -> None:
        with mock.patch.object(rc.subprocess, "run") as run:
            rc._run(["codeql", "version"], dry_run=False)
        run.assert_called_once()
