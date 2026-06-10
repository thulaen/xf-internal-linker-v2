"""Tests for the soft gate warning logging command."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.auto_issues.models import AutoIssue


class LogSoftGateWarningCommandTests(TestCase):
    def test_creates_auto_issue_with_default_detail(self):
        out = StringIO()

        call_command(
            "log_soft_gate_warning",
            "--hook",
            "check-missing-tests",
            stdout=out,
        )

        issue = AutoIssue.objects.get(external_id="check-missing-tests")
        self.assertEqual(issue.source, AutoIssue.SOURCE_PRE_COMMIT_WARNING)
        self.assertEqual(issue.title, "Soft gate warning: check-missing-tests")
        self.assertEqual(
            issue.description,
            "Pre-commit soft gate 'check-missing-tests' fired — no blocking detail captured."
        )
        self.assertEqual(issue.severity, AutoIssue.SEVERITY_LOW)
        self.assertEqual(issue.occurrence_count, 1)
        self.assertEqual(issue.priority_score, 0.25)
        self.assertEqual(issue.affected_files, [])

        output = out.getvalue()
        self.assertIn(f"[SOFT GATE WARNING LOGGED: AutoIssue=#{issue.pk} hook=check-missing-tests outcome=created]", output)

    def test_creates_auto_issue_with_provided_detail(self):
        out = StringIO()

        call_command(
            "log_soft_gate_warning",
            "--hook",
            "check-formatting",
            "--detail",
            "  Formatting failed in src/main.py  ",
            stdout=out,
        )

        issue = AutoIssue.objects.get(external_id="check-formatting")
        self.assertEqual(issue.description, "Formatting failed in src/main.py")

    def test_truncates_long_detail_at_200_chars(self):
        long_detail = "A" * 250
        out = StringIO()

        call_command(
            "log_soft_gate_warning",
            "--hook",
            "check-long-detail",
            "--detail",
            long_detail,
            stdout=out,
        )

        issue = AutoIssue.objects.get(external_id="check-long-detail")
        self.assertEqual(len(issue.description), 200)
        self.assertEqual(issue.description, "A" * 200)

    def test_deduplicates_and_increments_occurrence_count(self):
        call_command(
            "log_soft_gate_warning",
            "--hook",
            "check-missing-tests",
        )

        out = StringIO()
        call_command(
            "log_soft_gate_warning",
            "--hook",
            "check-missing-tests",
            "--detail",
            "Different detail on second run",
            stdout=out,
        )

        issues = list(AutoIssue.objects.filter(external_id="check-missing-tests"))
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.occurrence_count, 1)

        output = out.getvalue()
        self.assertIn(f"AutoIssue=#{issue.pk}", output)
        self.assertIn("outcome=updated]", output)

    def test_missing_hook_argument_raises_error(self):
        with self.assertRaises(CommandError):
            call_command("log_soft_gate_warning")
