"""Tests for manage.py file_task_issues."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TransactionTestCase

from apps.auto_issues.models import AutoIssue


class FileTaskIssuesTests(TransactionTestCase):
    """Exercise task follow-up filing, skips, and deduplication."""

    reset_sequences = False

    def tearDown(self) -> None:
        AutoIssue.objects.filter(external_id__startswith="task_followup::").delete()

    def _run(self, **kwargs) -> str:
        out = StringIO()
        call_command("file_task_issues", stdout=out, **kwargs)
        return out.getvalue()

    def test_files_each_issue_and_summary(self) -> None:
        output = self._run(
            turn_id="turn-123",
            agent="codex",
            issue=["Coverage command still needs wiring", "Mutation check timed out"],
        )
        rows = AutoIssue.objects.filter(external_id__startswith="task_followup::")
        self.assertEqual(rows.count(), 2)
        self.assertIn("[TASK ISSUE FILED:", output)
        self.assertIn(
            "[TASK ISSUES SUMMARY: turn=turn-123 filed=2 deduped=0 total=2]",
            output,
        )
        self.assertTrue(all(row.category.key == "task_followup" for row in rows))

    def test_repeated_issue_deduplicates_by_title_fingerprint(self) -> None:
        issue = "Coverage command still needs wiring. Keep this exact detail."
        self._run(turn_id="turn-123", agent="codex", issue=[issue])
        output = self._run(turn_id="turn-456", agent="codex", issue=[issue])
        rows = AutoIssue.objects.filter(external_id__startswith="task_followup::")
        self.assertEqual(rows.count(), 1)
        self.assertIn("[TASK ISSUE DEDUPED:", output)
        self.assertEqual(rows.first().occurrence_count, 2)
        self.assertEqual(rows.first().source_observations[-1]["turn_id"], "turn-456")

    def test_empty_turn_id_skips_filing(self) -> None:
        output = self._run(turn_id="", agent="codex", issue=["Unresolved item"])
        self.assertIn("[TASK ISSUES SKIPPED: empty --turn-id]", output)
        self.assertFalse(
            AutoIssue.objects.filter(external_id__startswith="task_followup::").exists()
        )

    def test_empty_issue_list_emits_zero_summary(self) -> None:
        output = self._run(turn_id="turn-empty", agent="codex", issue=[])
        self.assertIn(
            "[TASK ISSUES SUMMARY: turn=turn-empty filed=0 deduped=0 total=0]",
            output,
        )
