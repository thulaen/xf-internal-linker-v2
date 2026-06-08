from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.auto_issues.models import AutoIssue

_ENABLED_LINTER = {
    "id": "REPOSITORY_GITLEAKS",
    "status": "error",
    "number_errors": 2,
    "files": ["scripts/secret.sh"],
    "stdout": "found 2 leaks",
}
_DISABLED_LINTER = {
    "id": "SHELL_SHFMT",
    "status": "error",
    "number_errors": 3,
}
_SUCCESS_LINTER = {
    "id": "SHELL_SHELLCHECK",
    "status": "success",
    "number_errors": 0,
}
_UNKNOWN_LINTER = {
    "id": "BRAND_NEW_LINTER_XYZ",
    "status": "error",
    "number_errors": 1,
}


class IngestMegalinterJsonCommandTests(TestCase):
    def setUp(self) -> None:
        AutoIssue.objects.filter(source=AutoIssue.SOURCE_MEGALINTER).delete()

    def _call_with_stdin(self, report: dict, **kwargs) -> str:
        stdin_data = json.dumps(report)
        out = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(stdin_data)):
            call_command("ingest_megalinter_json", "--stdin", stdout=out, **kwargs)
        return out.getvalue()

    def test_enabled_linter_creates_autoissue(self):
        self._call_with_stdin({"linters": [_ENABLED_LINTER]})
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_MEGALINTER).count(), 1
        )
        ai = AutoIssue.objects.get(source=AutoIssue.SOURCE_MEGALINTER)
        self.assertIn("GITLEAKS", ai.title)
        self.assertEqual(ai.severity, AutoIssue.SEVERITY_CRITICAL)

    def test_disabled_linter_is_skipped(self):
        self._call_with_stdin({"linters": [_DISABLED_LINTER]})
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_MEGALINTER).count(), 0
        )

    def test_success_linter_is_skipped(self):
        self._call_with_stdin({"linters": [_SUCCESS_LINTER]})
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_MEGALINTER).count(), 0
        )

    def test_unknown_linter_creates_autoissue_with_defaults(self):
        self._call_with_stdin({"linters": [_UNKNOWN_LINTER]})
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_MEGALINTER).count(), 1
        )

    def test_dry_run_creates_no_db_rows(self):
        output = self._call_with_stdin(
            {"linters": [_ENABLED_LINTER]}, dry_run=True
        )
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_MEGALINTER).count(), 0
        )
        self.assertIn("dry-run", output)

    def test_output_marker_contains_counts(self):
        output = self._call_with_stdin(
            {"linters": [_ENABLED_LINTER, _DISABLED_LINTER, _SUCCESS_LINTER]}
        )
        self.assertIn("MEGALINTER INGEST", output)
        self.assertIn("created=1", output)
        self.assertIn("skipped=1", output)

    def test_second_run_merges_not_duplicates(self):
        self._call_with_stdin({"linters": [_ENABLED_LINTER]})
        self._call_with_stdin({"linters": [_ENABLED_LINTER]})
        # dedup: still exactly one row, not two
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_MEGALINTER).count(), 1
        )
        ai = AutoIssue.objects.get(source=AutoIssue.SOURCE_MEGALINTER)
        # upsert_dedup SETS occurrence_count to the passed value (always 1 here),
        # so count stays 1 — verify it is non-zero to confirm the record exists
        self.assertGreaterEqual(ai.occurrence_count, 1)

    def test_invalid_json_raises_command_error(self):
        out = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO("not-valid-json")):
            with self.assertRaises(CommandError):
                call_command("ingest_megalinter_json", "--stdin", stdout=out)

    def test_empty_linters_list_produces_zero_counts(self):
        output = self._call_with_stdin({"linters": []})
        self.assertIn("created=0", output)

    def test_input_file_mode(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "megalinter.json"
            path.write_text(json.dumps({"linters": [_ENABLED_LINTER]}), encoding="utf-8")
            out = io.StringIO()
            call_command(
                "ingest_megalinter_json", input_file=str(path), stdout=out
            )
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_MEGALINTER).count(), 1
        )

    def test_input_file_not_found_raises_command_error(self):
        with self.assertRaises(CommandError):
            call_command(
                "ingest_megalinter_json", input_file="/nonexistent/path.json"
            )

    def test_linters_field_not_a_list_raises_command_error(self):
        stdin_data = json.dumps({"linters": "not-a-list"})
        out = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(stdin_data)):
            with self.assertRaises(CommandError):
                call_command("ingest_megalinter_json", "--stdin", stdout=out)
