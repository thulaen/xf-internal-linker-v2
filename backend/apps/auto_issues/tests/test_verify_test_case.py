"""Strict-TDD Red test for `manage.py verify_test_case` (added 2026-05-17).

Asserts the command exit-code-0 when the referenced AutoIssue is a real
`category='test_case'` row with non-empty Given/When/Then, and non-zero
when missing, wrong-category, or stub.

Used by `.githooks/check-test-case-mandate.py` to validate that every ID in
a `[TEST CASE MAPPING: ... test_cases=#N]` marker resolves to a real row.

Spec: docs/TEST-CASE-FIRST-RULE.md
"""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


def _create_test_case_row(title: str = "demo", lessons: str = None) -> AutoIssue:
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key="test_case",
        defaults={"label": "Test case spec", "description": "...", "sort_order": 215},
    )
    fp = canonical_fingerprint(f"{title}::file.py::g::w::t")
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"tc::{fp}",
        fingerprint=f"tc::{fp}"[:64],
        canonical_fingerprint=fp,
        title=title,
        description="...",
        affected_files=["file.py"],
        severity=AutoIssue.SEVERITY_LOW,
        category=cat,
        status=AutoIssue.STATUS_OPEN,
        lessons_learned=(
            lessons
            if lessons is not None
            else "Given a precondition\nWhen an action happens\nThen an outcome occurs"
        ),
    )


class VerifyTestCaseCommandTests(TestCase):
    def test_real_row_passes_with_zero_exit(self):
        ai = _create_test_case_row()
        out = StringIO()
        call_command("verify_test_case", "--id", str(ai.pk), stdout=out)
        self.assertIn("[TEST CASE VERIFIED:", out.getvalue())

    def test_missing_id_fails(self):
        with self.assertRaises(CommandError):
            call_command("verify_test_case", "--id", "999999", stdout=StringIO())

    def test_wrong_category_fails(self):
        cat, _ = AutoIssueCategory.objects.get_or_create(
            key="tdd_lesson", defaults={"label": "x", "description": "x", "sort_order": 1}
        )
        ai = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="tdd::other",
            fingerprint="tdd::other",
            canonical_fingerprint="otherfp",
            title="not a test case",
            description="...",
            severity=AutoIssue.SEVERITY_LOW,
            category=cat,
            status=AutoIssue.STATUS_RESOLVED,
        )
        with self.assertRaises(CommandError):
            call_command("verify_test_case", "--id", str(ai.pk), stdout=StringIO())

    def test_missing_bdd_parts_fails(self):
        ai = _create_test_case_row(title="bad", lessons="just some prose, no BDD")
        with self.assertRaises(CommandError):
            call_command("verify_test_case", "--id", str(ai.pk), stdout=StringIO())
