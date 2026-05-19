"""TDD tests for the defer_work management command."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import dedup as dedup_service


_BDD_ABSTRACT = (
    "Given a deferral needs filing for the defer_work test suite, "
    "When the command is invoked with the standard arguments, "
    "Then a PaperTrailEntry row is created and the dedup index updated."
)
_REQUIRED_FIELDS = (
    "--risk-on-inaction", "Tests rely on this row.",
    "--acceptance-criteria", "Test passes when the row is created.",
)


def _make_test_case() -> AutoIssue:
    category, _ = AutoIssueCategory.objects.get_or_create(
        key="test_case",
        defaults={
            "label": "Test case spec",
            "description": "Test-only full BDD contract.",
            "sort_order": 215,
        },
    )
    index = AutoIssue.objects.filter(category=category).count() + 1
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"defer-work-test-case-{index}",
        fingerprint=f"defer-work-test-case-{index}",
        canonical_fingerprint=f"defer-work-test-case-{index}",
        title=f"Defer work test case {index}",
        description="Test-only defer_work evidence contract.",
        affected_files=["backend/apps/paper_trail/management/commands/defer_work.py"],
        severity=AutoIssue.SEVERITY_LOW,
        category=category,
        status=AutoIssue.STATUS_OPEN,
        lessons_learned=(
            "Given a deferral command needs a complete contract\n"
            "When defer_work validates the paper-trail evidence rule\n"
            "Then the command can link the row to a real test case\n"
            "Edge cases: duplicate and superseded entries still keep evidence\n"
            "Failure cases: missing citation or missing test case fails\n"
            "Security: citation values are stable public references\n"
            "Usability: the error message explains the missing proof\n"
            "Scalability: one linked row keeps lookup bounded\n"
            "Maintainability: tests build evidence through one helper\n"
            "Regression risks: old command calls without proof must fail"
        ),
    )


def _evidence_args() -> tuple[str, ...]:
    test_case = _make_test_case()
    return ("--test-case-autoissue", str(test_case.pk), "--citation", "RFC 9110")


class DeferWorkTests(TestCase):
    def setUp(self) -> None:
        dedup_service.reset_index_for_tests()

    def test_creates_new_entry(self) -> None:
        out = StringIO()
        before_count = PaperTrailEntry.objects.count()
        call_command(
            "defer_work",
            "--title", "Test deferral title",
            "--category", "other",
            "--abstract", _BDD_ABSTRACT,
            "--deferred-by", "claude",
            *_REQUIRED_FIELDS,
            *_evidence_args(),
            stdout=out,
        )
        self.assertIn("PAPER TRAIL FILED:", out.getvalue())
        self.assertEqual(PaperTrailEntry.objects.count(), before_count + 1)

    def test_duplicate_call_bumps_occurrence(self) -> None:
        before_count = PaperTrailEntry.objects.count()
        call_command(
            "defer_work",
            "--title", "Same title for dupe test",
            "--category", "other",
            "--abstract", _BDD_ABSTRACT,
            "--deferred-by", "claude",
            *_REQUIRED_FIELDS,
            *_evidence_args(),
            stdout=StringIO(),
        )
        out = StringIO()
        call_command(
            "defer_work",
            "--title", "Same title for dupe test",
            "--category", "other",
            "--abstract", _BDD_ABSTRACT,
            "--deferred-by", "claude",
            *_REQUIRED_FIELDS,
            *_evidence_args(),
            stdout=out,
        )
        self.assertIn("PAPER TRAIL DUPED:", out.getvalue())
        self.assertEqual(PaperTrailEntry.objects.count(), before_count + 1)
        entry = PaperTrailEntry.objects.get(title="Same title for dupe test")
        self.assertEqual(entry.occurrence_count, 2)

    def test_rejects_long_abstract(self) -> None:
        # 1201 BDD-shaped words exceeds the new 1200-word cap.
        header = "Given X When Y Then Z."
        long_abstract = header + " " + " ".join("word" for _ in range(1201))
        with self.assertRaises(CommandError):
            call_command(
                "defer_work",
                "--title", "Too long abstract",
                "--category", "other",
                "--abstract", long_abstract,
                "--deferred-by", "claude",
                *_REQUIRED_FIELDS,
                stdout=StringIO(),
            )

    def test_rejects_abstract_missing_bdd_section(self) -> None:
        """New 2026-05-16 rule: abstracts must contain Given/When/Then."""
        with self.assertRaises(CommandError):
            call_command(
                "defer_work",
                "--title", "Missing BDD shape",
                "--category", "other",
                "--abstract",
                "Just some narrative prose without the required structure.",
                "--deferred-by", "claude",
                *_REQUIRED_FIELDS,
                stdout=StringIO(),
            )

    def test_rejects_missing_risk_and_acceptance(self) -> None:
        """New 2026-05-16 rule: --risk-on-inaction and --acceptance-criteria are required."""
        with self.assertRaises(CommandError) as cm:
            call_command(
                "defer_work",
                "--title", "Missing required fields",
                "--category", "other",
                "--abstract", _BDD_ABSTRACT,
                "--deferred-by", "claude",
                stdout=StringIO(),
            )
        msg = str(cm.exception)
        self.assertIn("risk-on-inaction", msg)
        self.assertIn("acceptance-criteria", msg)

    def test_supersedes_flag_marks_old_entry(self) -> None:
        """--supersedes <N> sets the old row status=superseded + FK."""
        old_abstract = (
            "Given the old approach uses pattern A for the supersede test, "
            "When the agent files the original deferral, "
            "Then a paper-trail row exists for pattern A so it can later be "
            "marked superseded by a newer pattern B entry."
        )
        new_abstract = (
            "Given the new approach uses pattern B for the supersede test, "
            "When the agent files the replacement deferral with --supersedes, "
            "Then the old pattern-A row is marked status=superseded and "
            "points at the new row via the superseded_by foreign key."
        )
        call_command(
            "defer_work",
            "--title", "Old approach pattern A",
            "--category", "other",
            "--abstract", old_abstract,
            "--deferred-by", "claude",
            "--similarity-threshold", "0.99",
            *_REQUIRED_FIELDS,
            *_evidence_args(),
            stdout=StringIO(),
        )
        old = PaperTrailEntry.objects.first()
        out = StringIO()
        call_command(
            "defer_work",
            "--title", "New approach pattern B",
            "--category", "other",
            "--abstract", new_abstract,
            "--deferred-by", "claude",
            "--supersedes", str(old.pk),
            "--similarity-threshold", "0.99",
            *_REQUIRED_FIELDS,
            *_evidence_args(),
            stdout=out,
        )
        old.refresh_from_db()
        self.assertEqual(old.status, PaperTrailEntry.STATUS_SUPERSEDED)
        self.assertIsNotNone(old.superseded_by_id)
        self.assertIn("SUPERSEDED", out.getvalue())

    def test_links_to_autoissue(self) -> None:
        call_command(
            "defer_work",
            "--title", "Linked-autoissue deferral",
            "--category", "autoissue_deferral",
            "--abstract",
            "Given the upstream AutoIssue #252 needs multi-session work, "
            "When the agent defers it via this command, "
            "Then the paper-trail row links back to AutoIssue #252.",
            "--deferred-by", "claude",
            "--linked-autoissue", "252",
            *_REQUIRED_FIELDS,
            *_evidence_args(),
            stdout=StringIO(),
        )
        entry = PaperTrailEntry.objects.get(title="Linked-autoissue deferral")
        self.assertEqual(entry.linked_autoissue_id, 252)
        self.assertEqual(entry.category, "autoissue_deferral")

    def test_rejects_missing_test_case_autoissue(self) -> None:
        with self.assertRaisesMessage(CommandError, "--test-case-autoissue is required"):
            call_command(
                "defer_work",
                "--title", "Missing test case proof",
                "--category", "other",
                "--abstract", _BDD_ABSTRACT,
                "--deferred-by", "claude",
                *_REQUIRED_FIELDS,
                "--citation", "RFC 9110",
                stdout=StringIO(),
            )

    def test_rejects_missing_citation(self) -> None:
        test_case = _make_test_case()
        with self.assertRaisesMessage(CommandError, "--citation is required"):
            call_command(
                "defer_work",
                "--title", "Missing citation proof",
                "--category", "other",
                "--abstract", _BDD_ABSTRACT,
                "--deferred-by", "claude",
                *_REQUIRED_FIELDS,
                "--test-case-autoissue", str(test_case.pk),
                stdout=StringIO(),
            )
