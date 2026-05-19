"""Tests for manage.py file_mutation_survivors (Phase I/K7).

Exercises the per-tool JSON parsers + dedup via canonical_fingerprint.
Uses synthetic in-memory reports written to a tmpdir so no live
mutation run is needed.
"""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TransactionTestCase

from apps.auto_issues.models import AutoIssue


class FileMutationSurvivorsTests(TransactionTestCase):
    """End-to-end Django test: write report → run command → inspect rows."""

    reset_sequences = False

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        # Tidy up any survivor rows the test created so the next test
        # starts clean. TransactionTestCase wraps in a transaction but
        # belt-and-braces.
        AutoIssue.objects.filter(
            external_id__startswith="mutation::"
        ).delete()

    def _write(self, name: str, payload: dict) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _run(self, **kwargs) -> str:
        out = StringIO()
        call_command("file_mutation_survivors", stdout=out, **kwargs)
        return out.getvalue()

    def test_stryker_files_one_autoissue_per_survivor(self):
        report = self._write("stryker.json", {
            "files": {
                "frontend/src/app/foo.ts": {
                    "mutants": [
                        {
                            "id": "m1",
                            "mutatorName": "EqualityOperator",
                            "status": "Survived",
                            "location": {"start": {"line": 42}},
                            "replacement": "!=",
                        },
                        {
                            "id": "m2",
                            "mutatorName": "BlockStatement",
                            "status": "Killed",
                            "location": {"start": {"line": 50}},
                        },
                    ],
                },
            },
        })
        output = self._run(tool="stryker", report=str(report))
        # Exactly one survived → one row.
        rows = AutoIssue.objects.filter(
            external_id__startswith="mutation::stryker::"
        )
        self.assertEqual(rows.count(), 1)
        self.assertIn("filed=1", output)
        # Severity of EqualityOperator is high.
        row = rows.first()
        self.assertEqual(row.severity, AutoIssue.SEVERITY_HIGH)
        self.assertEqual(row.source, AutoIssue.SOURCE_MUTATION)

    def test_rerun_with_same_report_dedups(self):
        report = self._write("stryker.json", {
            "files": {
                "frontend/src/app/foo.ts": {
                    "mutants": [
                        {
                            "id": "m1",
                            "mutatorName": "EqualityOperator",
                            "status": "Survived",
                            "location": {"start": {"line": 42}},
                        }
                    ],
                },
            },
        })
        self._run(tool="stryker", report=str(report))
        # Second run should hit the dedup path.
        output = self._run(tool="stryker", report=str(report))
        rows = AutoIssue.objects.filter(
            external_id__startswith="mutation::stryker::"
        )
        self.assertEqual(rows.count(), 1)
        self.assertIn("deduped=1", output)
        # Occurrence count bumped to 2.
        self.assertEqual(rows.first().occurrence_count, 2)

    def test_empty_report_writes_clean_marker(self):
        report = self._write("empty.json", {"files": {}})
        output = self._run(tool="stryker", report=str(report))
        self.assertIn("none — clean run", output)
        self.assertEqual(
            AutoIssue.objects.filter(
                external_id__startswith="mutation::stryker::"
            ).count(),
            0,
        )

    def test_missing_report_treated_as_clean_run(self):
        # Phase I rule: a missing report is NOT an error; the mutation
        # tool may have crashed or hit the 5-min cap. No survivors to
        # file; no exception.
        output = self._run(tool="stryker",
                           report=str(self.tmp / "does-not-exist.json"))
        self.assertIn("none — report missing", output)

    def test_mull_parses_survived_and_notcovered(self):
        report = self._write("mull.json", {
            "mutants": [
                {
                    "id": "1",
                    "mutator": "cxx_lt_to_le",
                    "status": "Survived",
                    "location": {"file": "backend/extensions/scoring.cpp",
                                  "line": 100},
                },
                {
                    "id": "2",
                    "mutator": "cxx_increment",
                    "status": "NotCovered",
                    "location": {"file": "backend/extensions/scoring.cpp",
                                  "line": 105},
                },
                {
                    "id": "3",
                    "mutator": "cxx_lt_to_le",
                    "status": "Killed",
                    "location": {"file": "backend/extensions/scoring.cpp",
                                  "line": 110},
                },
            ],
        })
        self._run(tool="mull", report=str(report))
        rows = AutoIssue.objects.filter(
            external_id__startswith="mutation::mull::"
        )
        self.assertEqual(rows.count(), 2)

    def test_go_mutesting_passed_true_means_survived(self):
        # go-mutesting: result.passed == True means the tests DID NOT
        # detect the mutation (i.e. mutant survived).
        report = self._write("gomut.json", {
            "mutators": [
                {
                    "file": "services/streamd/internal/foo.go",
                    "line": 10,
                    "type": "branch/if",
                    "result": {"passed": True},
                },
                {
                    "file": "services/streamd/internal/foo.go",
                    "line": 20,
                    "type": "expression/swap",
                    "result": {"passed": False},  # killed
                },
            ],
        })
        self._run(tool="go-mutesting", report=str(report))
        rows = AutoIssue.objects.filter(
            external_id__startswith="mutation::go-mutesting::"
        )
        self.assertEqual(rows.count(), 1)

    def test_mutmut_parses_dict_survivors(self):
        report = self._write("mutmut.json", {
            "survivors": [
                {
                    "file": "apps/foo/bar.py",
                    "line": 12,
                    "type": "operator",
                    "replacement": "!=",
                },
                {
                    "file": "apps/foo/bar.py",
                    "line": 30,
                    "type": "string",
                    "replacement": "''",
                },
            ],
        })
        self._run(tool="mutmut", report=str(report))
        rows = AutoIssue.objects.filter(
            external_id__startswith="mutation::mutmut::"
        )
        self.assertEqual(rows.count(), 2)
        # operator is high, string is low.
        severities = sorted(r.severity for r in rows)
        self.assertEqual(severities, [AutoIssue.SEVERITY_HIGH,
                                       AutoIssue.SEVERITY_LOW])

    def test_mutmut_parses_string_survivors(self):
        # mutmut also outputs survivors as `"module::mutator__N"` strings.
        report = self._write("mutmut_str.json", {
            "survivors": [
                "apps.foo.bar::operator__1",
            ],
        })
        self._run(tool="mutmut", report=str(report))
        rows = AutoIssue.objects.filter(
            external_id__startswith="mutation::mutmut::"
        )
        self.assertEqual(rows.count(), 1)
