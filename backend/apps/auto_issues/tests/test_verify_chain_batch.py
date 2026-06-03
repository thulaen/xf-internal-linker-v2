"""Tests for the verify_chain_batch management command."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.paper_trail.models import PaperTrailEntry


_TDD_LESSON = "Trap: per-id checks are slow. Fix shape: check ids in one command."
_TEST_CASE = "Given context\nWhen action\nThen result"
_FULL_TEST_CASE = (
    "Given deferred work has proof\n"
    "When evidence is checked\n"
    "Then the row passes\n"
    "Edge cases: empty input fails\n"
    "Failure cases: missing citations fail\n"
    "Security: no private data is exposed\n"
    "Usability: failure messages explain the fix\n"
    "Scalability: batched checks keep query count bounded\n"
    "Maintainability: one helper owns the rule\n"
    "Regression risks: fake evidence must fail"
)


class VerifyChainBatchCommandTests(TestCase):
    def test_tdd_lessons_match_per_id_result(self) -> None:
        first = _autoissue("tdd_lesson", status=AutoIssue.STATUS_RESOLVED)
        second = _autoissue("tdd_lesson", status=AutoIssue.STATUS_RESOLVED)
        third = _autoissue("tdd_lesson", status=AutoIssue.STATUS_RESOLVED)
        wrong = _autoissue("other", status=AutoIssue.STATUS_RESOLVED)

        data = _call_json("--tdd-lessons", _csv(first, second, third, wrong))

        self.assertEqual(data["tdd_lessons"][str(first.pk)]["status"], "pass")
        self.assertEqual(data["tdd_lessons"][str(second.pk)]["status"], "pass")
        self.assertEqual(data["tdd_lessons"][str(third.pk)]["status"], "pass")
        self.assertEqual(data["tdd_lessons"][str(wrong.pk)]["status"], "fail")
        self.assertIn("wrong category", data["tdd_lessons"][str(wrong.pk)]["reason"])

    def test_all_six_categories_in_one_invocation(self) -> None:
        lesson = _autoissue("tdd_lesson", status=AutoIssue.STATUS_RESOLVED)
        test_case = _autoissue("test_case", lessons=_TEST_CASE)
        review = _autoissue("code_review_lesson", status=AutoIssue.STATUS_RESOLVED)
        autoissue_quota = _resolved_autoissues(33)
        autoissue_quota += _resolved_autoissues(
            10,
            source=AutoIssue.SOURCE_SONARQUBE,
        )
        paper_quota = _resolved_paper_entries(10)
        evidence = _paper_evidence_entry()

        data = _call_json(
            "--tdd-lessons", str(lesson.pk),
            "--test-cases", str(test_case.pk),
            "--code-review-lessons", str(review.pk),
            "--autoissue-quota", ",".join(str(row.pk) for row in autoissue_quota),
            "--paper-trail-quota", ",".join(str(row.pk) for row in paper_quota),
            "--paper-trail-evidence", str(evidence.pk),
        )

        self.assertEqual(data["tdd_lessons"][str(lesson.pk)]["status"], "pass")
        self.assertEqual(data["test_cases"][str(test_case.pk)]["status"], "pass")
        self.assertEqual(
            data["code_review_lessons"][str(review.pk)]["status"],
            "pass",
        )
        self.assertEqual(data["autoissue_quota"]["status"], "pass")
        self.assertEqual(data["paper_trail_quota"]["status"], "pass")
        self.assertEqual(
            data["paper_trail_evidence"][str(evidence.pk)]["status"],
            "pass",
        )

    def test_50_ids_completes_under_one_second(self) -> None:
        lessons = [
            _autoissue("tdd_lesson", status=AutoIssue.STATUS_RESOLVED)
            for _ in range(50)
        ]

        started = time.perf_counter()
        data = _call_json("--tdd-lessons", ",".join(str(row.pk) for row in lessons))
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 1.0)
        self.assertTrue(
            all(row["status"] == "pass" for row in data["tdd_lessons"].values())
        )

    def test_invalid_id_reports_fail_with_reason(self) -> None:
        data = _call_json("--tdd-lessons", "999999")

        self.assertEqual(data["tdd_lessons"]["999999"]["status"], "fail")
        self.assertIn("does not exist", data["tdd_lessons"]["999999"]["reason"])

    def test_health_postgres_ok_returns_exit_0(self) -> None:
        data = _call_json("--health")

        self.assertEqual(data["postgres"], "ok")
        self.assertEqual(data["backend"], "ok")
        self.assertEqual(data["auto_issues_table"], "ok")

    def test_health_postgres_down_returns_exit_1(self) -> None:
        with mock.patch(
            "apps.auto_issues.services.chain_batch.connection.cursor",
            side_effect=RuntimeError("connection refused"),
        ):
            with self.assertRaises(SystemExit) as raised:
                _call_json("--health")

        self.assertEqual(raised.exception.code, 1)

    def test_health_includes_helper_failure_rate(self) -> None:
        data = _call_json("--health")

        self.assertIn("helper_failure_rate_per_hour", data)
        self.assertIsInstance(data["helper_failure_rate_per_hour"], int)

    def test_command_does_not_spawn_subprocesses(self) -> None:
        lesson = _autoissue("tdd_lesson", status=AutoIssue.STATUS_RESOLVED)

        with mock.patch.object(subprocess, "run", side_effect=AssertionError):
            data = _call_json("--tdd-lessons", str(lesson.pk))

        self.assertEqual(data["tdd_lessons"][str(lesson.pk)]["status"], "pass")


def _call_json(*args: str) -> dict:
    out = StringIO()
    call_command("verify_chain_batch", *args, "--json", stdout=out)
    return json.loads(out.getvalue())


def _csv(*rows) -> str:
    return ",".join(str(row.pk) for row in rows)


def _autoissue(
    category_key: str,
    *,
    status: str = AutoIssue.STATUS_OPEN,
    lessons: str = _TDD_LESSON,
    source: str = AutoIssue.SOURCE_AGENT,
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
        source=source,
        external_id=f"verify-chain-batch-{category_key}-{index}",
        fingerprint=f"verify-chain-batch-{category_key}-{index}",
        canonical_fingerprint=f"verify-chain-batch-{category_key}-{index}",
        title=f"Batch verifier {category_key} {index}",
        description="Test-only verifier row.",
        affected_files=["backend/apps/auto_issues/management/commands/verify_chain_batch.py"],
        severity=AutoIssue.SEVERITY_LOW,
        category=category,
        status=status,
        resolved_at=resolved_at,
        resolved_by="codex-test" if resolved_at else "",
        lessons_learned=lessons,
    )


def _resolved_autoissues(
    count: int,
    *,
    source: str = AutoIssue.SOURCE_AGENT,
) -> list[AutoIssue]:
    return [
        _autoissue(
            "quota_test",
            status=AutoIssue.STATUS_RESOLVED,
            lessons="Trap: quota row needs proof. Fix shape: store lessons.",
            source=source,
        )
        for _ in range(count)
    ]


def _resolved_paper_entries(count: int) -> list[PaperTrailEntry]:
    rows = []
    for index in range(count):
        row = PaperTrailEntry.objects.create(
            category=PaperTrailEntry.CATEGORY_TOOLING_GAP,
            title=f"Resolved paper quota row {index}",
            abstract=(
                "Given a deferred tooling item exists, "
                "When the quota verifier checks it, "
                "Then resolved entries with lessons pass."
            ),
            deferred_by="codex-test",
            risk_on_inaction="A later agent could miss required deferred work.",
            acceptance_criteria="The batch verifier accepts this resolved row.",
            test_case_autoissue_id=_autoissue("test_case", lessons=_FULL_TEST_CASE).pk,
            citations=["RFC 9110"],
            status=PaperTrailEntry.STATUS_RESOLVED,
            resolved_at=timezone.now() - timedelta(seconds=index),
            resolved_by="codex-test",
            resolution_lessons="Trap: paper rows use resolution_lessons. Fix shape: read that field.",
        )
        rows.append(row)
    return rows


def _paper_evidence_entry() -> PaperTrailEntry:
    return PaperTrailEntry.objects.create(
        category=PaperTrailEntry.CATEGORY_TOOLING_GAP,
        title="Paper evidence batch row",
        abstract=(
            "Given a paper-trail row has linked proof, "
            "When the batch verifier checks it, "
            "Then complete evidence passes."
        ),
        deferred_by="codex-test",
        risk_on_inaction="A later agent could follow an unproven deferral.",
        acceptance_criteria="The batch verifier accepts complete proof.",
        test_case_autoissue_id=_autoissue("test_case", lessons=_FULL_TEST_CASE).pk,
        citations=["RFC 9110"],
    )
