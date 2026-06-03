"""Tests for scope-cap AutoIssue filing."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.management.commands.file_hook_finding import file_hook_finding
from apps.auto_issues.models import AutoIssue


class ScopeCapAutoIssueTests(TestCase):
    def test_scope_exceeded_files_autoissue_with_category_scope_cap_exceeded(self) -> None:
        issue, created = file_hook_finding(
            category="scope_cap_exceeded",
            severity=AutoIssue.SEVERITY_MEDIUM,
            subject="scripts/run-python-quality.sh:mutmut",
            message=(
                "FAIL scope cap: mutmut targets=47 cap=20.\n"
                "UNBLOCK: narrow the commit, increase cap with documented reason, "
                "or move whole-tree run to CI (XF_QUALITY_ENV=ci)."
            ),
            external_id="scope_cap_exceeded::scripts/run-python-quality.sh::mutmut",
        )

        self.assertTrue(created)
        self.assertEqual(issue.category.key, "scope_cap_exceeded")
        self.assertEqual(issue.external_id, "scope_cap_exceeded::scripts/run-python-quality.sh::mutmut")

    def test_scope_exceeded_dedupes_on_wrapper_plus_tool(self) -> None:
        kwargs = {
            "category": "scope_cap_exceeded",
            "severity": AutoIssue.SEVERITY_MEDIUM,
            "subject": "scripts/run-python-quality.sh:mutmut",
            "message": (
                "FAIL scope cap: mutmut targets=47 cap=20.\n"
                "UNBLOCK: narrow the commit, increase cap with documented reason, "
                "or move whole-tree run to CI (XF_QUALITY_ENV=ci)."
            ),
            "external_id": "scope_cap_exceeded::scripts/run-python-quality.sh::mutmut",
        }

        first, created_first = file_hook_finding(**kwargs)
        second, created_second = file_hook_finding(**kwargs)

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.occurrence_count, 2)

    def test_commit_blocker_uses_explicit_lessons(self) -> None:
        lessons = (
            "Trap: the staged file is a private environment file.\n"
            "Fix shape: remove the file from the staged set and retry the commit."
        )

        out = StringIO()
        call_command(
            "file_hook_finding",
            category="commit_blocker",
            severity=AutoIssue.SEVERITY_HIGH,
            subject="scripts/precommit-docker.sh:1",
            message=(
                "check-junk-files refused commit at 2026-05-21T01:55:00Z. "
                "check-junk-files blocked commit: staged .env"
            ),
            external_id="commit_blocker::check-junk-files::abc123",
            lessons_learned=lessons,
            stdout=out,
        )

        self.assertIn("[HOOK FINDING FILED:", out.getvalue())
        issue = AutoIssue.objects.get(
            external_id="commit_blocker::check-junk-files::abc123",
        )
        self.assertEqual(issue.lessons_learned, lessons)
        self.assertNotIn("<UNBLOCK section>", issue.lessons_learned)

    def test_commit_blocker_dedup_updates_explicit_lessons(self) -> None:
        kwargs = {
            "category": "commit_blocker",
            "severity": AutoIssue.SEVERITY_HIGH,
            "subject": "scripts/precommit-docker.sh:1",
            "message": (
                "check-junk-files refused commit at 2026-05-21T01:55:00Z. "
                "check-junk-files blocked commit: staged .env"
            ),
            "external_id": "commit_blocker::check-junk-files::repeat",
            "lessons_learned": "Trap: old reason.\nFix shape: old fix.",
        }

        first, created_first = file_hook_finding(**kwargs)
        kwargs["lessons_learned"] = "Trap: current reason.\nFix shape: current fix."
        second, created_second = file_hook_finding(**kwargs)

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.occurrence_count, 2)
        self.assertEqual(
            second.lessons_learned,
            "Trap: current reason.\nFix shape: current fix.",
        )

    def test_repeated_hook_finding_reopens_resolved_issue_with_lesson_preserved(self) -> None:
        lessons = (
            "Trap: hook findings bypass the shared dedup helper.\n"
            "Fix shape: reopen the same row when the same hook finding appears again."
        )
        kwargs = {
            "category": "commit_blocker",
            "severity": AutoIssue.SEVERITY_HIGH,
            "subject": "scripts/precommit-docker.sh:1",
            "message": (
                "check-junk-files refused commit at 2026-05-23T22:28:00Z. "
                "check-junk-files blocked commit: staged private file."
            ),
            "external_id": "commit_blocker::check-junk-files::reopen",
            "lessons_learned": lessons,
        }

        issue, created = file_hook_finding(**kwargs)
        self.assertTrue(created)
        issue.status = AutoIssue.STATUS_RESOLVED
        issue.resolved_at = timezone.now()
        issue.resolved_by = "codex"
        issue.fix_commit_sha = "abc1234"
        issue.save(update_fields=["status", "resolved_at", "resolved_by", "fix_commit_sha"])

        reopened, created_again = file_hook_finding(**kwargs)

        self.assertFalse(created_again)
        reopened.refresh_from_db()
        self.assertEqual(reopened.pk, issue.pk)
        self.assertEqual(reopened.status, AutoIssue.STATUS_OPEN)
        self.assertIsNone(reopened.resolved_at)
        self.assertEqual(reopened.resolved_by, "")
        self.assertEqual(reopened.fix_commit_sha, "")
        self.assertEqual(reopened.lessons_learned, lessons)
        self.assertEqual(reopened.occurrence_count, 2)
