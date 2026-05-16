"""TDD tests for Rule G — log_code_review_lessons management command.

Red phase: these tests define the contract before the command exists.
Green phase: implementation in commands/log_code_review_lessons.py.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue


class LogCodeReviewLessonsTests(TestCase):
    def test_creates_autoissue_and_emits_logged_marker(self) -> None:
        out = StringIO()
        call_command(
            "log_code_review_lessons",
            "--file", "backend/apps/audit/error_ingest.py",
            "--title", "Review of error_ingest refactor",
            "--abstract",
            "No issues — the refactor preserves behaviour, reduces "
            "cyclomatic complexity from 12 to 6, and adds a defensive "
            "null-check at line 142. The async-context guard is correctly "
            "applied. Test coverage stays at 88% for this file.",
            "--severity", "low",
            stdout=out,
        )
        self.assertIn("[CODE REVIEW LESSON LOGGED:", out.getvalue())
        ai = AutoIssue.objects.filter(
            category__key="code_review_lesson"
        ).first()
        self.assertIsNotNone(ai)
        self.assertIn("backend/apps/audit/error_ingest.py", ai.affected_files)
        self.assertEqual(ai.status, AutoIssue.STATUS_RESOLVED)
        self.assertTrue(ai.lessons_learned)

    def test_rejects_empty_title(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "log_code_review_lessons",
                "--file", "backend/apps/x.py",
                "--title", "",
                "--abstract", "Some abstract text here.",
                stdout=StringIO(),
            )

    def test_rejects_title_over_200_chars(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "log_code_review_lessons",
                "--file", "backend/apps/x.py",
                "--title", "X" * 201,
                "--abstract", "Some abstract text here.",
                stdout=StringIO(),
            )

    def test_rejects_abstract_over_600_words(self) -> None:
        long_abstract = " ".join("word" for _ in range(601))
        with self.assertRaises(CommandError):
            call_command(
                "log_code_review_lessons",
                "--file", "backend/apps/x.py",
                "--title", "OK title",
                "--abstract", long_abstract,
                stdout=StringIO(),
            )

    def test_dedup_bumps_occurrence_not_new_row(self) -> None:
        first = StringIO()
        call_command(
            "log_code_review_lessons",
            "--file", "backend/apps/x.py",
            "--title", "Repeat review title",
            "--abstract", "First review of this file. No issues found.",
            stdout=first,
        )
        first_count = AutoIssue.objects.filter(
            category__key="code_review_lesson"
        ).count()
        self.assertEqual(first_count, 1)

        second = StringIO()
        call_command(
            "log_code_review_lessons",
            "--file", "backend/apps/x.py",
            "--title", "Repeat review title",
            "--abstract", "Second review of this file. Still no issues.",
            stdout=second,
        )
        self.assertIn("[CODE REVIEW LESSON DEDUPED:", second.getvalue())
        # Still exactly one row — the second was deduped.
        self.assertEqual(
            AutoIssue.objects.filter(category__key="code_review_lesson").count(),
            1,
        )
        bumped = AutoIssue.objects.get(category__key="code_review_lesson")
        self.assertGreaterEqual(bumped.occurrence_count, 2)

    def test_no_issues_lesson_accepted(self) -> None:
        """The user-clarified 'no issues' outcome is a valid lesson."""
        out = StringIO()
        call_command(
            "log_code_review_lessons",
            "--file", "backend/apps/y.py",
            "--title", "Clean review of y.py",
            "--abstract",
            "No issues — the change follows the existing pattern at "
            "backend/apps/y.py:42 and the test suite remains green.",
            "--severity", "none",
            stdout=out,
        )
        self.assertIn("[CODE REVIEW LESSON LOGGED:", out.getvalue())

    def test_links_to_existing_autoissue(self) -> None:
        # When an agent resolves an AutoIssue, the code-review lesson
        # can link to it so the lessons aggregate around the fix.
        parent = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="parent_for_link_test",
            fingerprint="parent_for_link_test",
            title="Some parent AutoIssue",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_OPEN,
        )
        out = StringIO()
        call_command(
            "log_code_review_lessons",
            "--file", "backend/apps/z.py",
            "--title", "Lesson linked to parent",
            "--abstract", "Review found an issue covered by AutoIssue link.",
            "--autoissue-id", str(parent.id),
            stdout=out,
        )
        self.assertIn("[CODE REVIEW LESSON LOGGED:", out.getvalue())
