"""Tests for the commit-chain batch verifier service."""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.chain_batch import batch_verify
from apps.paper_trail.models import PaperTrailEntry


class ChainBatchServiceTests(TestCase):
    def test_batch_verify_runs_one_query_per_autoissue_category(self) -> None:
        lesson = _autoissue("tdd_lesson", status=AutoIssue.STATUS_RESOLVED)
        test_case = _autoissue(
            "test_case",
            lessons="Given context\nWhen action\nThen result",
        )
        review = _autoissue("code_review_lesson", status=AutoIssue.STATUS_RESOLVED)

        with CaptureQueriesContext(connection) as captured:
            result = batch_verify(
                {
                    "tdd_lessons": [lesson.pk],
                    "test_cases": [test_case.pk],
                    "code_review_lessons": [review.pk],
                }
            )

        self.assertEqual(len(captured), 3)
        self.assertEqual(result["tdd_lessons"][str(lesson.pk)]["status"], "pass")
        self.assertEqual(result["test_cases"][str(test_case.pk)]["status"], "pass")
        self.assertEqual(
            result["code_review_lessons"][str(review.pk)]["status"],
            "pass",
        )

    def test_batch_verify_handles_empty_input(self) -> None:
        with CaptureQueriesContext(connection) as captured:
            result = batch_verify({})

        self.assertEqual(result, {})
        self.assertEqual(len(captured), 0)

    def test_batch_verify_preserves_quota_duplicates(self) -> None:
        rows = [
            _autoissue("quota_test", status=AutoIssue.STATUS_RESOLVED)
            for _ in range(39)
        ]
        ids = [row.pk for row in rows] + [rows[0].pk]

        result = batch_verify({"autoissue_quota": ids})

        self.assertEqual(result["autoissue_quota"]["status"], "fail")
        self.assertIn("duplicate AutoIssue ids", result["autoissue_quota"]["reason"])

    def test_batch_verify_requires_ten_sonarqube_quota_rows(self) -> None:
        rows = [
            _autoissue("quota_test", status=AutoIssue.STATUS_RESOLVED)
            for _ in range(40)
        ]

        result = batch_verify({"autoissue_quota": [row.pk for row in rows]})

        self.assertEqual(result["autoissue_quota"]["status"], "fail")
        self.assertIn("expected 10 SonarQube AutoIssues", result["autoissue_quota"]["reason"])

    def test_resolved_paper_evidence_requires_code_review_lesson_reference(self) -> None:
        entry = _resolved_paper_entry(
            resolution_lessons=(
                "Trap: resolution proof can name no review row. "
                "Fix shape: require a resolved code-review lesson reference."
            )
        )

        result = batch_verify({"paper_trail_evidence": [entry.pk]})

        self.assertEqual(result["paper_trail_evidence"][str(entry.pk)]["status"], "fail")
        self.assertIn(
            "missing resolved code_review_lesson reference",
            result["paper_trail_evidence"][str(entry.pk)]["reason"],
        )

    def test_resolved_paper_evidence_accepts_resolved_code_review_reference(self) -> None:
        review = _autoissue("code_review_lesson", status=AutoIssue.STATUS_RESOLVED)
        entry = _resolved_paper_entry(
            resolution_lessons=(
                "Trap: resolution proof needs a per-file review. "
                f"Fix shape: reference resolved code-review lesson #{review.pk}."
            )
        )

        result = batch_verify({"paper_trail_evidence": [entry.pk]})

        self.assertEqual(result["paper_trail_evidence"][str(entry.pk)]["status"], "pass")


def _autoissue(
    category_key: str,
    *,
    status: str = AutoIssue.STATUS_OPEN,
    lessons: str = "Trap: old path was slow. Fix shape: batch the checks.",
) -> AutoIssue:
    category, _ = AutoIssueCategory.objects.get_or_create(
        key=category_key,
        defaults={
            "label": category_key.replace("_", " ").title(),
            "description": "Test-only category.",
            "sort_order": 200,
        },
    )
    index = AutoIssue.objects.count() + 1
    resolved_at = timezone.now() if status == AutoIssue.STATUS_RESOLVED else None
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"chain-batch-{category_key}-{index}",
        fingerprint=f"chain-batch-{category_key}-{index}",
        canonical_fingerprint=f"chain-batch-{category_key}-{index}",
        title=f"Batch verifier {category_key} {index}",
        description="Test-only verifier row.",
        affected_files=["backend/apps/auto_issues/services/chain_batch.py"],
        severity=AutoIssue.SEVERITY_LOW,
        category=category,
        status=status,
        resolved_at=resolved_at,
        resolved_by="codex-test" if resolved_at else "",
        lessons_learned=lessons,
    )


def _resolved_paper_entry(*, resolution_lessons: str) -> PaperTrailEntry:
    return PaperTrailEntry.objects.create(
        category=PaperTrailEntry.CATEGORY_TOOLING_GAP,
        title="Resolved paper evidence row",
        abstract=(
            "Given a resolved paper-trail row has filing proof, "
            "When commit evidence is checked, "
            "Then resolution proof is also verified."
        ),
        deferred_by="codex-test",
        risk_on_inaction="A later agent could close work without review proof.",
        acceptance_criteria="The batch verifier rejects missing review proof.",
        test_case_autoissue_id=_autoissue(
            "test_case",
            lessons=(
                "Given a resolved paper-trail row\n"
                "When evidence is checked\n"
                "Then code-review proof is required\n"
                "Edge cases: missing review references fail\n"
                "Failure cases: open review rows fail\n"
                "Security: no private data is exposed\n"
                "Usability: failure messages explain the missing proof\n"
                "Scalability: referenced review rows are fetched in one query\n"
                "Maintainability: one helper owns resolution evidence\n"
                "Regression risks: unreviewed resolutions must stay blocked"
            ),
        ).pk,
        citations=["RFC 9110"],
        status=PaperTrailEntry.STATUS_RESOLVED,
        resolved_at=timezone.now(),
        resolved_by="codex-test",
        resolution_lessons=resolution_lessons,
    )
