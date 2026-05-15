"""Tests for logging task-scoped self-review findings."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.auto_issues.models import AutoIssue


class LogSelfReviewIssueCommandTests(TestCase):
    def test_creates_open_agent_issue(self) -> None:
        out = StringIO()
        call_command(
            "log_self_review_issue",
            "--title", "Long function in task scope",
            "--description", "The changed helper does too many jobs.",
            "--file", "backend/apps/example.py",
            "--category", "maintainability",
            stdout=out,
        )

        issue = AutoIssue.objects.get()
        self.assertEqual(issue.source, AutoIssue.SOURCE_AGENT)
        self.assertEqual(issue.status, AutoIssue.STATUS_OPEN)
        self.assertEqual(issue.affected_files, ["backend/apps/example.py"])
        self.assertIn("Self-review category: maintainability", issue.description)
        self.assertIn("AutoIssue #", out.getvalue())

    def test_fixed_issue_requires_lessons_learned(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "log_self_review_issue",
                "--title", "Duplication in task scope",
                "--description", "Two blocks repeated the same parsing.",
                "--file", "backend/apps/example.py",
                "--fixed",
            )

    def test_fixed_issue_marks_row_resolved(self) -> None:
        call_command(
            "log_self_review_issue",
            "--title", "Duplication in task scope",
            "--description", "Two blocks repeated the same parsing.",
            "--file", "backend/apps/example.py",
            "--fixed",
            "--lessons-learned", "Trap: repeated parsing hides drift. Fix shape: shared helper.",
            "--agent", "codex-test",
        )

        issue = AutoIssue.objects.get()
        self.assertEqual(issue.status, AutoIssue.STATUS_RESOLVED)
        self.assertEqual(issue.resolved_by, "codex-test")
        self.assertIn("Fix shape", issue.lessons_learned)

    def test_repeat_finding_dedupes_to_one_issue(self) -> None:
        args = (
            "--title", "Overengineered task helper",
            "--description", "A small branch used a large abstraction.",
            "--file", "backend/apps/example.py",
        )
        call_command("log_self_review_issue", *args)
        call_command("log_self_review_issue", *args)

        issue = AutoIssue.objects.get()
        self.assertEqual(AutoIssue.objects.count(), 1)
        self.assertEqual(issue.occurrence_count, 1)
