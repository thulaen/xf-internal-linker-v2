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
from django.test import SimpleTestCase, TestCase, TransactionTestCase

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

    def test_malformed_json_report_raises_command_error(self):
        # Lines 310-311: a report that exists but is not valid JSON is a
        # hard error (the tool run is broken), unlike a missing report.
        from django.core.management.base import CommandError

        bad = self.tmp / "broken.json"
        bad.write_text("{not valid json", encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "could not parse"):
            self._run(tool="stryker", report=str(bad))

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


class CargoHelperFunctionTests(TestCase):
    """Unit tests for the helpers extracted from _parse_cargo_mutants (S3776 fix)."""

    def test_cargo_mutant_to_survivor_uses_file_and_line(self):
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _cargo_mutant_to_survivor,
        )
        mutant = {"file": "src/lib.rs", "line": 42, "replacement": "==", "type_": "BinaryOp"}
        result = _cargo_mutant_to_survivor(mutant)
        self.assertEqual(result["file"], "src/lib.rs")
        self.assertEqual(result["line"], 42)
        self.assertEqual(result["mutator"], "==")
        self.assertEqual(result["id"], "")

    def test_cargo_mutant_to_survivor_fallbacks_on_missing_fields(self):
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _cargo_mutant_to_survivor,
        )
        result = _cargo_mutant_to_survivor({})
        self.assertEqual(result["file"], "unknown")
        self.assertEqual(result["line"], 0)
        self.assertEqual(result["mutator"], "unknown")

    def test_cargo_missed_to_survivor_includes_id_with_package_function(self):
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _cargo_missed_to_survivor,
        )
        m = {
            "file": "src/lib.rs", "line": 10,
            "package": "mypkg", "function": "my_fn",
            "replacement": "!=", "type_": "BinaryOp",
        }
        result = _cargo_missed_to_survivor(m)
        self.assertEqual(result["file"], "src/lib.rs")
        self.assertIn("mypkg", result["id"])
        self.assertIn("my_fn", result["id"])

    def test_cargo_mutants_shape_a_reads_missed_and_outcomes(self):
        # Lines 217-224 + 244-246: object payload routes through shape A,
        # gathering both the flat `missed[]` list and `MissedMutant`
        # outcomes that carry a nested scenario.Mutant object.
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _parse_cargo_mutants,
        )
        payload = {
            "missed": [
                {"file": "src/a.rs", "line": 5, "replacement": "==",
                 "package": "p", "function": "f"},
            ],
            "outcomes": [
                {
                    "summary": "MissedMutant",
                    "scenario": {"Mutant": {"file": "src/b.rs", "line": 9,
                                             "replacement": "!="}},
                },
                {"summary": "CaughtMutant", "scenario": {"Mutant": {}}},
            ],
        }
        survivors = _parse_cargo_mutants(payload)
        self.assertEqual(len(survivors), 2)
        files = sorted(s["file"] for s in survivors)
        self.assertEqual(files, ["src/a.rs", "src/b.rs"])

    def test_cargo_mutants_shape_b_reads_array_of_outcomes(self):
        # Lines 227-234 + 247-248: list payload routes through shape B; only
        # MissedMutant outcomes with a real Mutant object become survivors.
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _parse_cargo_mutants,
        )
        payload = [
            {
                "summary": "MissedMutant",
                "scenario": {"Mutant": {"file": "src/c.rs", "line": 3,
                                         "replacement": "<="}},
            },
            {"summary": "CaughtMutant",
             "scenario": {"Mutant": {"file": "src/d.rs", "line": 4}}},
            {"summary": "MissedMutant", "scenario": {"Mutant": {}}},  # empty -> skipped
        ]
        survivors = _parse_cargo_mutants(payload)
        self.assertEqual(len(survivors), 1)
        self.assertEqual(survivors[0]["file"], "src/c.rs")
        self.assertEqual(survivors[0]["line"], 3)


class SupportedToolsAndMucheckTests(SimpleTestCase):
    """No-DB convention tests pinning the new tool wiring (cargo-mutants + mucheck)."""

    def test_supported_tools_set_has_exact_membership(self):
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _SUPPORTED_TOOLS,
        )
        self.assertEqual(
            _SUPPORTED_TOOLS,
            {"stryker", "mutmut", "mull", "go-mutesting", "cargo-mutants", "mucheck"},
        )

    def test_cargo_mutants_and_mucheck_have_registered_parsers(self):
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _PARSERS,
            _parse_cargo_mutants,
            _parse_mucheck,
        )
        self.assertIs(_PARSERS["cargo-mutants"], _parse_cargo_mutants)
        self.assertIs(_PARSERS["mucheck"], _parse_mucheck)

    def test_parse_mucheck_maps_each_survivor_field_exactly(self):
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _parse_mucheck,
        )
        survivors = _parse_mucheck({
            "survivors": [
                {"file": "src/a.hs", "line": 7, "mutator": "Flip", "replacement": "not", "id": "x1"},
                {"file": "src/b.hs", "line": 99, "mutator": "Drop", "replacement": ""},
            ]
        })
        self.assertEqual(len(survivors), 2)
        self.assertEqual(survivors[0]["file"], "src/a.hs")
        self.assertEqual(survivors[0]["line"], 7)
        self.assertEqual(survivors[0]["mutator"], "Flip")
        self.assertEqual(survivors[0]["replacement"], "not")
        self.assertEqual(survivors[0]["id"], "x1")
        # Missing fields fall back to safe defaults, never raising.
        self.assertEqual(survivors[1]["line"], 99)
        self.assertEqual(survivors[1]["id"], "")

    def test_parse_mucheck_defaults_missing_keys(self):
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _parse_mucheck,
        )
        survivors = _parse_mucheck({"survivors": [{}]})
        self.assertEqual(survivors[0]["file"], "unknown")
        self.assertEqual(survivors[0]["line"], 0)
        self.assertEqual(survivors[0]["mutator"], "unknown")

    def test_parse_mucheck_empty_payload_returns_empty_list(self):
        from apps.auto_issues.management.commands.file_mutation_survivors import (
            _parse_mucheck,
        )
        self.assertEqual(_parse_mucheck({}), [])
