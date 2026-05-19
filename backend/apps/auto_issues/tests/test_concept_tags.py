"""Tests for controlled concept tags on AutoIssue lesson retrieval."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


class ModelFieldTests(TestCase):
    def test_concept_tags_defaults_to_empty_list(self) -> None:
        issue = _create_issue(title="Model field default")

        self.assertEqual(issue.concept_tags, [])


class ValidationTests(TestCase):
    def test_validate_tag_accepts_known_tag(self) -> None:
        from apps.auto_issues.concept_tags import validate_tag

        validate_tag("python-subprocess")

    def test_validate_tag_rejects_unknown(self) -> None:
        from apps.auto_issues.concept_tags import validate_tag

        with self.assertRaises(CommandError):
            validate_tag("nonsense-tag")


class LogTddLessonTests(TestCase):
    def test_concept_tag_flag_stored_on_row(self) -> None:
        out = StringIO()
        call_command(
            "log_tdd_lesson",
            "--file", "scripts/run.py",
            "--red-test", "backend/apps/auto_issues/tests/test_concept_tags.py",
            "--red-test-name", "LogTddLessonTests::test_concept_tag_flag_stored_on_row",
            "--red-run-at", "2026-05-18T04:00:00Z",
            "--green-run-at", "2026-05-18T04:01:00Z",
            "--trap", "Python subprocess calls need explicit text encoding on Windows.",
            "--fix-shape", "Store the approved concept tags on the lesson row.",
            "--concept-tag", "python-subprocess",
            "--concept-tag", "windows-encoding",
            "--agent", "codex-test",
            stdout=out,
        )

        issue = AutoIssue.objects.get(title__startswith="TDD cycle: scripts/run.py")
        self.assertEqual(issue.concept_tags, ["python-subprocess", "windows-encoding"])


class LogTestCaseTests(TestCase):
    def test_concept_tag_flag_stored_on_row(self) -> None:
        call_command(
            "log_test_case",
            "--file", "backend/apps/auto_issues/models.py",
            "--title", "Concept tags default to an empty list",
            "--given", "an agent creates an AutoIssue without tags",
            "--when", "the row is saved",
            "--then", "the concept tag list is empty",
            "--concept-tag", "django-management-command",
            stdout=StringIO(),
        )

        issue = AutoIssue.objects.get(title="Concept tags default to an empty list")
        self.assertEqual(issue.concept_tags, ["django-management-command"])


class LogCodeReviewLessonsTests(TestCase):
    def test_concept_tag_flag_stored_on_row(self) -> None:
        call_command(
            "log_code_review_lessons",
            "--file", "backend/apps/auto_issues/concept_tags.py",
            "--title", "Review concept-tag helper",
            "--abstract", "No issues found in the concept-tag helper.",
            "--concept-tag", "hook-marker-format",
            stdout=StringIO(),
        )

        issue = AutoIssue.objects.get(title="Review concept-tag helper")
        self.assertEqual(issue.concept_tags, ["hook-marker-format"])


class LogSelfReviewIssueTests(TestCase):
    def test_concept_tag_flag_stored_on_row(self) -> None:
        call_command(
            "log_self_review_issue",
            "--title", "Concept-tag validation found during review",
            "--description", "The tag list must reject unknown values.",
            "--file", "backend/apps/auto_issues/concept_tags.py",
            "--category", "correctness",
            "--concept-tag", "django-management-command",
            stdout=StringIO(),
        )

        issue = AutoIssue.objects.get(title="Concept-tag validation found during review")
        self.assertEqual(issue.concept_tags, ["django-management-command"])


class ReadScopedLessonsTests(TestCase):
    def test_tag_filter_returns_matching_lessons_across_areas(self) -> None:
        hook_issue = _create_issue(
            title="Hook subprocess lesson",
            affected_files=[".githooks/check-example.py"],
            concept_tags=["python-subprocess"],
            resolved_at=timezone.now() - timedelta(minutes=2),
        )
        script_issue = _create_issue(
            title="Script subprocess lesson",
            affected_files=["scripts/example.py"],
            concept_tags=["python-subprocess"],
        )

        out = StringIO()
        call_command(
            "read_scoped_lessons",
            "--tag", "python-subprocess",
            "--limit", "10",
            stdout=out,
        )

        text = out.getvalue()
        self.assertIn(f"#{hook_issue.id}", text)
        self.assertIn(f"#{script_issue.id}", text)
        self.assertIn("tags=python-subprocess", text)


class SearchResolvedIssuesTests(TestCase):
    def test_tag_filter_returns_matching_lessons_across_areas(self) -> None:
        hook_issue = _create_issue(
            title="Hook marker lesson",
            affected_files=[".githooks/check-example.py"],
            concept_tags=["hook-marker-format"],
        )
        script_issue = _create_issue(
            title="Script marker lesson",
            affected_files=["scripts/example.py"],
            concept_tags=["hook-marker-format"],
        )

        out = StringIO()
        call_command(
            "search_resolved_issues",
            "--area", ".githooks",
            "--tag", "hook-marker-format",
            stdout=out,
        )

        text = out.getvalue()
        self.assertIn(f"#{hook_issue.id}", text)
        self.assertIn(f"#{script_issue.id}", text)


class ListConceptTagsTests(TestCase):
    def test_prints_allowed_vocabulary(self) -> None:
        from apps.auto_issues.concept_tags import ALLOWED_CONCEPT_TAGS

        out = StringIO()
        call_command("list_concept_tags", stdout=out)

        lines = [line for line in out.getvalue().splitlines() if line.strip()]
        self.assertEqual(lines, sorted(ALLOWED_CONCEPT_TAGS))
        self.assertEqual(len(lines), 20)


def _create_issue(
    *,
    title: str,
    affected_files: list[str] | None = None,
    concept_tags: list[str] | None = None,
    resolved_at=None,
) -> AutoIssue:
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"concept-tag-{AutoIssue.objects.count()}",
        fingerprint=f"concept-tag-{AutoIssue.objects.count()}",
        title=title,
        description="Concept tag retrieval test issue.",
        affected_files=affected_files or ["backend/apps/auto_issues/models.py"],
        severity=AutoIssue.SEVERITY_MEDIUM,
        status=AutoIssue.STATUS_RESOLVED,
        resolved_at=resolved_at or timezone.now(),
        resolved_by="codex-test",
        lessons_learned="Trap: concept matches can span folders.\nFix shape: tag rows.",
        concept_tags=concept_tags or [],
    )
