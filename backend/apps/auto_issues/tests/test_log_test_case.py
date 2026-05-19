"""Strict-TDD Red test for `manage.py log_test_case` (added 2026-05-17).

Asserts the command creates an `AutoIssue(category='test_case', status='open')`
row with Given/When/Then captured in `lessons_learned`, and that re-running
with the same args bumps `occurrence_count` instead of creating a duplicate.

Spec: docs/TEST-CASE-FIRST-RULE.md
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, AutoIssueCategory


def _test_case(title: str) -> AutoIssue:
    return AutoIssue.objects.filter(category__key="test_case", title=title).get()


class LogTestCaseCommandTests(TestCase):
    """Behaviour: filing a test case before code edits."""

    def test_creates_test_case_autoissue(self):
        out = StringIO()
        call_command(
            "log_test_case",
            "--file", "backend/apps/foo/bar.py",
            "--title", "exposure_prob rejects negative inputs",
            "--given", "the exposure_prob function is called",
            "--when", "the input is negative",
            "--then", "the function raises ValueError with a plain-English message",
            stdout=out,
        )
        marker_line = out.getvalue()
        self.assertIn("[TEST CASE WRITTEN: AutoIssue=#", marker_line)
        ai = _test_case("exposure_prob rejects negative inputs")
        self.assertEqual(ai.status, AutoIssue.STATUS_OPEN)
        self.assertIn("Given the exposure_prob function is called", ai.lessons_learned)
        self.assertIn("When the input is negative", ai.lessons_learned)
        self.assertIn("Then the function raises ValueError", ai.lessons_learned)
        self.assertIn("backend/apps/foo/bar.py", ai.affected_files)

    def test_duplicate_filing_bumps_occurrence_count(self):
        for _ in range(2):
            call_command(
                "log_test_case",
                "--file", "backend/apps/foo/bar.py",
                "--title", "exposure_prob rejects negative inputs",
                "--given", "the exposure_prob function is called",
                "--when", "the input is negative",
                "--then", "the function raises ValueError with a plain-English message",
                stdout=StringIO(),
            )
        rows = AutoIssue.objects.filter(
            category__key="test_case",
            title="exposure_prob rejects negative inputs",
        )
        self.assertEqual(rows.count(), 1)
        ai = rows.get()
        self.assertEqual(ai.occurrence_count, 2)

    def test_creates_category_on_first_use(self):
        call_command(
            "log_test_case",
            "--file", "backend/apps/foo/bar.py",
            "--title", "foo title",
            "--given", "a precondition",
            "--when", "an action happens",
            "--then", "an outcome is observed by the caller",
            stdout=StringIO(),
        )
        category = AutoIssueCategory.objects.get(key="test_case")
        self.assertEqual(category.label, "Test case spec")

    def test_emits_marker_with_real_id(self):
        out = StringIO()
        call_command(
            "log_test_case",
            "--file", "backend/apps/foo/bar.py",
            "--title", "foo title",
            "--given", "a precondition",
            "--when", "an action happens",
            "--then", "an outcome is observed by the caller",
            stdout=out,
        )
        ai = _test_case("foo title")
        self.assertIn(f"AutoIssue=#{ai.pk}", out.getvalue())
        self.assertIn("file=backend/apps/foo/bar.py", out.getvalue())

    def test_extended_fields_land_in_lessons(self):
        call_command(
            "log_test_case",
            "--file", "backend/apps/foo/bar.py",
            "--title", "foo title",
            "--given", "a precondition",
            "--when", "an action happens",
            "--then", "an outcome is observed",
            "--edge-cases", "0 returns 0.0; NaN raises a separate ValueError",
            "--security", "no input reaches eval or shell; bytes are bounded by 1 MiB",
            stdout=StringIO(),
        )
        ai = _test_case("foo title")
        self.assertIn("Edge cases: 0 returns 0.0", ai.lessons_learned)
        self.assertIn("Security: no input reaches eval", ai.lessons_learned)

    def test_verify_test_case_accepts_repeated_ids(self):
        first = self._write_case("first repeated verifier case")
        second = self._write_case("second repeated verifier case")
        out = StringIO()

        call_command(
            "verify_test_case",
            "--id", str(first.pk),
            "--id", str(second.pk),
            stdout=out,
        )

        text = out.getvalue()
        self.assertIn(f"[TEST CASE VERIFIED: AutoIssue=#{first.pk}", text)
        self.assertIn(f"[TEST CASE VERIFIED: AutoIssue=#{second.pk}", text)

    def _write_case(self, title: str) -> AutoIssue:
        call_command(
            "log_test_case",
            "--file", "backend/apps/foo/bar.py",
            "--title", title,
            "--given", "a precondition exists",
            "--when", "the verifier checks the stored contract",
            "--then", "the command prints the verified marker",
            stdout=StringIO(),
        )
        return _test_case(title)
