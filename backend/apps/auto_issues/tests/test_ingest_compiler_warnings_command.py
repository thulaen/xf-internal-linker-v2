"""Tests for the ingest_compiler_warnings management command (no DB).

The command is a thin file-reading wrapper: it validates --path, reads the log,
delegates to ingest_compiler_warnings, and prints a marker. These tests mock the
service seam and the filesystem so they run as SimpleTestCase (no database) and
stay fast even when the scoped-mutation gate re-runs them per mutant. Spec:
docs/specs/fr-compiler-warning-autoissues.md.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

_CMD = "ingest_compiler_warnings"
_SERVICE = "apps.auto_issues.management.commands.ingest_compiler_warnings.ingest_compiler_warnings"


class IngestCompilerWarningsCommandTests(SimpleTestCase):
    def test_missing_path_raises_command_error(self):
        with mock.patch("pathlib.Path.is_file", return_value=False):
            with self.assertRaises(CommandError):
                call_command(_CMD, "--path", "nope.log", "--language", "rust")

    def test_reads_file_and_reports_counts(self):
        out = StringIO()
        with (
            mock.patch("pathlib.Path.is_file", return_value=True),
            mock.patch("pathlib.Path.read_text", return_value="warning: x\n  --> src/a.rs:1:1"),
            mock.patch(_SERVICE, return_value={"parsed": 3, "filed": 2}) as ingest,
        ):
            call_command(_CMD, "--path", "warn.log", "--language", "rust", stdout=out)
        ingest.assert_called_once_with("warning: x\n  --> src/a.rs:1:1", "rust", dry_run=False)
        text = out.getvalue()
        self.assertIn("[RUST COMPILER WARNINGS:", text)
        self.assertIn("parsed=3", text)
        self.assertIn("filed=2", text)

    def test_dry_run_passes_flag_and_marks_output(self):
        out = StringIO()
        with (
            mock.patch("pathlib.Path.is_file", return_value=True),
            mock.patch("pathlib.Path.read_text", return_value="log"),
            mock.patch(_SERVICE, return_value={"parsed": 1, "filed": 0}) as ingest,
        ):
            call_command(_CMD, "--path", "w.log", "--language", "rust", "--dry-run", stdout=out)
        ingest.assert_called_once_with("log", "rust", dry_run=True)
        self.assertIn("[RUST COMPILER WARNINGS (dry-run):", out.getvalue())

    def test_removed_language_is_rejected_by_choices(self):
        with self.assertRaises(CommandError):
            call_command(_CMD, "--path", "w.log", "--language", "cpp")
