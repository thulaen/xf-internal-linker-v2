"""Tests for manage.py file_gh_helper_autoissue."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase

from apps.auto_issues.management.commands.file_gh_helper_autoissue import Command
from apps.auto_issues.models import AutoIssue


class FileGhHelperAutoIssueTests(TransactionTestCase):
    """Exercise kind-specific filing and deduplication."""

    reset_sequences = False

    def tearDown(self) -> None:
        AutoIssue.objects.filter(external_id__startswith="gh_helper::").delete()

    def _run(self, **kwargs) -> str:
        out = StringIO()
        call_command("file_gh_helper_autoissue", stdout=out, **kwargs)
        return out.getvalue()

    def test_api_failure_files_kind_specific_autoissue(self) -> None:
        output = self._run(
            kind="api_failure",
            context="branch 'feature/demo' was not found",
            agent="codex",
        )
        row = AutoIssue.objects.get(external_id="gh_helper::api_failure")
        self.assertIn("[GH HELPER AUTOISSUE FILED:", output)
        self.assertEqual(row.title, "gh CLI api call returned empty or non-zero")
        self.assertIn("branch 'feature/demo'", row.description)
        self.assertEqual(row.source, AutoIssue.SOURCE_AGENT)
        self.assertEqual(row.category.key, "gh_tooling_broken")
        self.assertEqual(row.source_observations[0]["kind"], "api_failure")

    def test_repeated_missing_kind_deduplicates(self) -> None:
        self._run(kind="missing", context="first caller", agent="codex")
        output = self._run(kind="missing", context="second caller", agent="codex")
        rows = AutoIssue.objects.filter(external_id="gh_helper::missing")
        self.assertEqual(rows.count(), 1)
        self.assertIn("[GH HELPER AUTOISSUE DEDUPED:", output)
        self.assertEqual(rows.first().occurrence_count, 2)
        self.assertEqual(rows.first().source_observations[-1]["agent"], "codex")

    def test_unknown_kind_is_rejected_before_writing(self) -> None:
        with self.assertRaises(CommandError):
            Command().handle(kind="unknown", context="", agent="codex")
        self.assertFalse(
            AutoIssue.objects.filter(external_id="gh_helper::unknown").exists()
        )
