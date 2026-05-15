"""Tests for resolving AutoIssue rows with required lessons."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.auto_issues.models import AutoIssue


class ResolveAutoIssueCommandTests(TestCase):
    def _issue(self, external_id: str) -> AutoIssue:
        return AutoIssue.objects.create(
            source=AutoIssue.SOURCE_PYROSCOPE,
            external_id=external_id,
            fingerprint=external_id,
            title=f"Pyroscope issue {external_id}",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_OPEN,
        )

    def test_requires_two_part_lesson(self) -> None:
        issue = self._issue("missing-lesson")

        with self.assertRaisesMessage(CommandError, "Trap:"):
            call_command(
                "resolve_autoissue",
                "--id",
                str(issue.id),
                "--lessons-learned",
                "Fixed it.",
            )

    def test_resolves_multiple_rows_with_lessons(self) -> None:
        first = self._issue("first")
        second = self._issue("second")
        lessons = "Trap: profiler setup can look like app heat. Fix shape: group it."
        output = StringIO()

        call_command(
            "resolve_autoissue",
            "--id",
            str(first.id),
            "--id",
            str(second.id),
            "--lessons-learned",
            lessons,
            "--agent",
            "codex",
            stdout=output,
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, AutoIssue.STATUS_RESOLVED)
        self.assertEqual(second.status, AutoIssue.STATUS_RESOLVED)
        self.assertEqual(first.lessons_learned, lessons)
        self.assertEqual(second.resolved_by, "codex")
        self.assertIsNotNone(first.resolved_at)
        self.assertIn("#", output.getvalue())
