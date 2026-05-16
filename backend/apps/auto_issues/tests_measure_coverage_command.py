"""Tests for the measure_coverage management command.

Verifies the parsing logic + the human-readable / JSON output paths.
The subprocess shelling is mocked so the tests run instantly without
actually executing pytest.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.auto_issues.management.commands.measure_coverage import Command


class ParseReportTests(SimpleTestCase):
    """Unit tests for the `_parse_report` helper — no subprocess needed."""

    def test_parses_simple_total_line(self) -> None:
        text = (
            "Name                                   Stmts   Miss  Cover\n"
            "----------------------------------------\n"
            "apps/x.py                                100     10  90.0%\n"
            "----------------------------------------\n"
            "TOTAL                                    100     10  90.0%\n"
        )
        pct, branch_pct = Command._parse_report(text, branches=False)
        self.assertEqual(pct, 90.0)
        self.assertIsNone(branch_pct)

    def test_parses_total_with_branch_columns(self) -> None:
        text = (
            "Name        Stmts   Miss Branch BrPart  Cover\n"
            "---------------------------------------------\n"
            "TOTAL          50      5     20      4  85.0%\n"
        )
        pct, branch_pct = Command._parse_report(text, branches=True)
        self.assertEqual(pct, 85.0)

    def test_parses_decimal_percentages(self) -> None:
        text = "TOTAL  1000  37  96.3%\n"
        pct, _ = Command._parse_report(text, branches=False)
        self.assertAlmostEqual(pct, 96.3)

    def test_raises_when_total_line_missing(self) -> None:
        with self.assertRaises(CommandError):
            Command._parse_report("no total here\n", branches=False)


class MeasureCoverageCommandTests(SimpleTestCase):
    """Integration tests — mock subprocess, exercise the command."""

    def _mock_runs(self, report_text: str):
        """Return a side_effect callable that returns canned subprocess.CompletedProcess."""
        class FakeResult:
            def __init__(self, stdout="", stderr="", returncode=0):
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode

        def fake_run(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if cmd[:2] == ["coverage", "report"]:
                return FakeResult(stdout=report_text)
            return FakeResult()

        return fake_run

    def test_human_readable_output_format(self) -> None:
        report = "TOTAL  100  10  90.0%\n"
        out = StringIO()
        with patch(
            "apps.auto_issues.management.commands.measure_coverage.subprocess.run",
            side_effect=self._mock_runs(report),
        ):
            call_command("measure_coverage", "--module", "apps/x.py", stdout=out)
        self.assertIn("[COVERAGE: target=apps/x.py line=90.0%]", out.getvalue())

    def test_json_output_format(self) -> None:
        report = "TOTAL  50  5  90.0%\n"
        out = StringIO()
        with patch(
            "apps.auto_issues.management.commands.measure_coverage.subprocess.run",
            side_effect=self._mock_runs(report),
        ):
            call_command(
                "measure_coverage", "--module", "apps/y.py", "--json", stdout=out,
            )
        import json

        payload = json.loads(out.getvalue())
        self.assertEqual(payload["target"], "apps/y.py")
        self.assertEqual(payload["line_pct"], 90.0)

    def test_module_or_app_required(self) -> None:
        with self.assertRaises(CommandError):
            call_command("measure_coverage")

    def test_app_dotted_path_is_converted_to_slash(self) -> None:
        report = "TOTAL  20  2  90.0%\n"
        out = StringIO()
        with patch(
            "apps.auto_issues.management.commands.measure_coverage.subprocess.run",
            side_effect=self._mock_runs(report),
        ):
            call_command(
                "measure_coverage", "--app", "apps.auto_issues", stdout=out,
            )
        self.assertIn("target=apps/auto_issues", out.getvalue())

    def test_scoped_run_ignores_repo_wide_pytest_coverage_defaults(self) -> None:
        report = "TOTAL  20  2  90.0%\n"
        calls: list[list[str]] = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            return self._mock_runs(report)(cmd)

        out = StringIO()
        with patch(
            "apps.auto_issues.management.commands.measure_coverage.subprocess.run",
            side_effect=fake_run,
        ):
            call_command("measure_coverage", "--module", "apps/x.py", stdout=out)

        coverage_run = next(cmd for cmd in calls if cmd[:2] == ["coverage", "run"])
        self.assertIn("--override-ini", coverage_run)
        self.assertIn("addopts=", coverage_run)
        self.assertNotIn("--cov=apps", coverage_run)
        self.assertNotIn("--cov=config", coverage_run)
