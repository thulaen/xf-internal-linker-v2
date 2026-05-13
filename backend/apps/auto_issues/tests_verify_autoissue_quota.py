"""Tests for the AutoIssue quota verifier management command."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue

_DEFAULT_RESOLVED_AT = object()


class VerifyAutoIssueQuotaCommandTests(TestCase):
    def test_thirty_resolved_issues_with_lessons_pass(self) -> None:
        issue_ids = _create_resolved_issues(30)
        out = StringIO()
        call_command("verify_autoissue_quota", ids=issue_ids, stdout=out)
        self.assertIn("30 resolved", out.getvalue())

    def test_twenty_nine_issues_fail(self) -> None:
        issue_ids = _create_resolved_issues(29)
        with self.assertRaisesMessage(CommandError, "Expected 30 picked AutoIssues"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_duplicate_issue_id_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        issue_ids.append(issue_ids[0])
        with self.assertRaisesMessage(CommandError, "Duplicate picked AutoIssue IDs"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_open_issue_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        open_issue = _create_issue(status=AutoIssue.STATUS_OPEN)
        issue_ids.append(str(open_issue.id))
        with self.assertRaisesMessage(CommandError, f"#{open_issue.id} is open"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_resolved_issue_without_lessons_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        empty_lesson = _create_issue(lessons_learned="")
        issue_ids.append(str(empty_lesson.id))
        with self.assertRaisesMessage(CommandError, "has no lessons_learned note"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_missing_resolved_time_fails(self) -> None:
        issue_ids = _create_resolved_issues(29)
        missing_time = _create_issue(resolved_at=None)
        issue_ids.append(str(missing_time.id))
        with self.assertRaisesMessage(CommandError, "has no resolved_at time"):
            call_command("verify_autoissue_quota", ids=issue_ids)

    def test_issue_resolved_before_previous_handoff_fails(self) -> None:
        old_time = timezone.now() - timedelta(days=2)
        issue_ids = _create_resolved_issues(29)
        old_issue = _create_issue(resolved_at=old_time)
        issue_ids.append(str(old_issue.id))
        yesterday = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        with self.assertRaisesMessage(CommandError, "before the previous handoff"):
            call_command(
                "verify_autoissue_quota",
                ids=issue_ids,
                resolved_after=yesterday,
            )

    def test_non_numeric_id_fails(self) -> None:
        with self.assertRaisesMessage(CommandError, "must be a number"):
            call_command("verify_autoissue_quota", ids=["abc"])


def _create_resolved_issues(count: int) -> list[str]:
    return [str(_create_issue().id) for _ in range(count)]


def _create_issue(
    *,
    status: str = AutoIssue.STATUS_RESOLVED,
    resolved_at=_DEFAULT_RESOLVED_AT,
    lessons_learned: str = "Trap: test trap.\nFix shape: test fix.",
) -> AutoIssue:
    if resolved_at is _DEFAULT_RESOLVED_AT and status == AutoIssue.STATUS_RESOLVED:
        resolved_at = timezone.now()
    if resolved_at is _DEFAULT_RESOLVED_AT:
        resolved_at = None
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"quota-test-{AutoIssue.objects.count()}",
        title="Quota verifier test issue",
        status=status,
        resolved_at=resolved_at,
        resolved_by="codex-test",
        lessons_learned=lessons_learned,
    )
