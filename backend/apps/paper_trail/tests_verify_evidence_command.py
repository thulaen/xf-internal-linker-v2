"""Tests for the paper-trail evidence verifier command."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.paper_trail.models import PaperTrailEntry


_FULL_LESSON = (
    "Given a deferred work item needs a complete contract\n"
    "When verify_paper_trail_evidence checks the linked AutoIssue\n"
    "Then the command accepts the paper-trail row\n"
    "Edge cases: empty citations and missing links fail\n"
    "Failure cases: incomplete BDD fields are rejected\n"
    "Security: citations are public stable identifiers\n"
    "Usability: errors explain how the operator can unblock\n"
    "Scalability: one linked row keeps verification bounded\n"
    "Maintainability: helpers keep required evidence obvious\n"
    "Regression risks: fake proof must not pass the hook"
)


def _test_case(*, lessons: str = _FULL_LESSON, category_key: str = "test_case") -> AutoIssue:
    category, _ = AutoIssueCategory.objects.get_or_create(
        key=category_key,
        defaults={
            "label": category_key.replace("_", " ").title(),
            "description": "Test-only category.",
            "sort_order": 215,
        },
    )
    index = AutoIssue.objects.count() + 1
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"paper-evidence-test-{index}",
        fingerprint=f"paper-evidence-test-{index}",
        canonical_fingerprint=f"paper-evidence-test-{index}",
        title=f"Paper evidence test {index}",
        description="Test-only evidence verifier row.",
        affected_files=["backend/apps/paper_trail/management/commands/verify_paper_trail_evidence.py"],
        severity=AutoIssue.SEVERITY_LOW,
        category=category,
        status=AutoIssue.STATUS_OPEN,
        lessons_learned=lessons,
    )


def _entry(*, test_case: AutoIssue | None = None, citations: list[str] | None = None) -> PaperTrailEntry:
    linked = test_case or _test_case()
    return PaperTrailEntry.objects.create(
        category=PaperTrailEntry.CATEGORY_OTHER,
        title=f"Evidence verifier row {PaperTrailEntry.objects.count() + 1}",
        abstract=(
            "Given a paper-trail row has linked proof, "
            "When the verifier command checks it, "
            "Then the row is accepted only when the proof is complete."
        ),
        deferred_by="test-agent",
        risk_on_inaction="The next agent could follow an unproven deferral.",
        acceptance_criteria="The verifier accepts complete proof and rejects bad proof.",
        test_case_autoissue_id=linked.pk,
        citations=citations if citations is not None else ["RFC 9110"],
    )


class VerifyPaperTrailEvidenceCommandTests(TestCase):
    def test_complete_test_case_and_citation_pass(self) -> None:
        entry = _entry()
        out = StringIO()

        call_command("verify_paper_trail_evidence", "--paper-trail-id", str(entry.pk), stdout=out)

        self.assertIn(f"[PAPER TRAIL EVIDENCE VERIFIED: #{entry.pk}", out.getvalue())

    def test_incomplete_test_case_fails(self) -> None:
        test_case = _test_case(lessons="Given context\nWhen action\nThen result")
        entry = _entry(test_case=test_case)

        with self.assertRaisesMessage(CommandError, "missing required BDD section"):
            call_command("verify_paper_trail_evidence", "--paper-trail-id", str(entry.pk))

    def test_invalid_citation_fails(self) -> None:
        entry = _entry(citations=["some blog post"])

        with self.assertRaisesMessage(CommandError, "accepted form"):
            call_command("verify_paper_trail_evidence", "--paper-trail-id", str(entry.pk))
