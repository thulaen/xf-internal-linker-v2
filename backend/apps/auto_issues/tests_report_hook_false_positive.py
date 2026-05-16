"""TDD tests for report_hook_false_positive command (Rule H.31)."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue


class ReportHookFalsePositiveTests(TestCase):
    def test_creates_autoissue_with_hook_false_positive_category(self) -> None:
        out = StringIO()
        call_command(
            "report_hook_false_positive",
            "--hook", "check-debug-code",
            "--context",
            "The hook flagged a docstring containing the literal word "
            "'print' even though it was inside triple quotes describing how "
            "to format CLI output. The regex needs a backtick-string exclusion.",
            stdout=out,
        )
        self.assertIn("[HOOK FALSE POSITIVE FILED:", out.getvalue())
        ai = AutoIssue.objects.filter(
            category__key="hook_false_positive"
        ).first()
        self.assertIsNotNone(ai)
        self.assertEqual(ai.status, AutoIssue.STATUS_OPEN)

    def test_rejects_empty_hook(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "report_hook_false_positive",
                "--hook", "",
                "--context", "x",
                stdout=StringIO(),
            )

    def test_rejects_empty_context(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "report_hook_false_positive",
                "--hook", "check-debug-code",
                "--context", "",
                stdout=StringIO(),
            )

    def test_rejects_context_over_600_words(self) -> None:
        long_ctx = " ".join("word" for _ in range(601))
        with self.assertRaises(CommandError):
            call_command(
                "report_hook_false_positive",
                "--hook", "check-debug-code",
                "--context", long_ctx,
                stdout=StringIO(),
            )

    def test_dedup_collapses_repeat_reports(self) -> None:
        first = StringIO()
        call_command(
            "report_hook_false_positive",
            "--hook", "check-tdd-cycle",
            "--context",
            "Same first sentence triggers the dedup. The hook complained "
            "about Red-Green ordering but the test was added in the same "
            "commit as the source.",
            stdout=first,
        )
        first_count = AutoIssue.objects.filter(
            category__key="hook_false_positive"
        ).count()
        self.assertEqual(first_count, 1)

        second = StringIO()
        call_command(
            "report_hook_false_positive",
            "--hook", "check-tdd-cycle",
            "--context",
            "Same first sentence triggers the dedup. Different second "
            "sentence but the canonical fingerprint matches.",
            stdout=second,
        )
        self.assertIn("[HOOK FALSE POSITIVE DEDUPED:", second.getvalue())
        # Still exactly one row — the second was deduped.
        self.assertEqual(
            AutoIssue.objects.filter(category__key="hook_false_positive").count(),
            1,
        )
        bumped = AutoIssue.objects.get(category__key="hook_false_positive")
        self.assertGreaterEqual(bumped.occurrence_count, 2)
