"""Tests for the code-review lesson logging command."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue


class BulkCodeReviewLessonsCommandTests(TestCase):
    def test_dry_run_reports_without_writing_issue(self):
        out = StringIO()
        before_count = AutoIssue.objects.count()

        call_command(
            "log_code_review_lessons",
            "--file",
            "backend/apps/example.py",
            "--title",
            "Dry run code review",
            "--abstract",
            "No issues found during the dry-run command preview.",
            "--severity",
            "none",
            "--agent",
            "codex",
            "--dry-run",
            stdout=out,
        )

        self.assertEqual(AutoIssue.objects.count(), before_count)
        self.assertIn("[CODE REVIEW LESSON DRY-RUN:", out.getvalue())

    def test_bulk_per_file_prints_one_marker_per_file(self):
        title = "Bulk command review smoke"
        files = [
            ".githooks/check-one.py",
            ".githooks/check-two.py",
            ".githooks/check-three.py",
        ]
        out = StringIO()

        call_command(
            "log_code_review_lessons",
            "--file",
            files[0],
            "--file",
            files[1],
            "--file",
            files[2],
            "--title",
            title,
            "--abstract",
            (
                "Reviewed grouped hook files for marker coverage, silent "
                "errors, maintainability, duplication, and long functions. "
                "No new issue was found in this command test."
            ),
            "--severity",
            "none",
            "--agent",
            "codex",
            "--bulk-per-file",
            stdout=out,
        )

        lines = [line for line in out.getvalue().splitlines() if line]
        self.assertEqual(len(lines), len(files))
        self.assertIn("[CODE REVIEW LESSON LOGGED:", lines[0])
        self.assertTrue(
            all("[CODE REVIEW LESSON DEDUPED:" in line for line in lines[1:])
        )
        issue = AutoIssue.objects.get(title=title)
        self.assertEqual(issue.affected_files, files)
        self.assertEqual(issue.occurrence_count, len(files))
