"""Tests for the resolved AutoIssue history search command."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


class SearchResolvedIssuesCommandTests(TestCase):
    def test_area_search_matches_path_prefix(self) -> None:
        matching = _create_issue(
            title="Audit retry fix",
            affected_files=["backend/apps/resolved_search_audit/tasks.py"],
        )
        _create_issue(
            title="Pipeline fix",
            affected_files=["backend/apps/resolved_search_pipeline/tasks.py"],
        )
        output = StringIO()

        call_command(
            "search_resolved_issues",
            area="backend/apps/resolved_search_audit",
            limit=5,
            stdout=output,
        )

        text = output.getvalue()
        self.assertIn(f"#{matching.id}", text)
        self.assertIn("Audit retry fix", text)
        self.assertNotIn("Pipeline fix", text)

    def test_area_search_accepts_windows_separators(self) -> None:
        matching = _create_issue(
            title="Windows path fix",
            affected_files=["backend/apps/resolved_search_windows/tasks.py"],
        )
        output = StringIO()

        call_command(
            "search_resolved_issues",
            area=r"backend\apps\resolved_search_windows",
            stdout=output,
        )

        self.assertIn(f"#{matching.id}", output.getvalue())

    def test_multiple_area_searches_run_in_one_command(self) -> None:
        audit = _create_issue(
            title="Audit path fix",
            affected_files=["backend/apps/resolved_search_batch_audit/tasks.py"],
        )
        pipeline = _create_issue(
            title="Pipeline path fix",
            affected_files=["backend/apps/resolved_search_batch_pipeline/tasks.py"],
        )
        output = StringIO()

        call_command(
            "search_resolved_issues",
            area=[
                "backend/apps/resolved_search_batch_audit",
                "backend/apps/resolved_search_batch_pipeline",
            ],
            stdout=output,
        )

        text = output.getvalue()
        self.assertIn("backend/apps/resolved_search_batch_audit: 1 prior fix", text)
        self.assertIn(f"#{audit.id}", text)
        self.assertIn("backend/apps/resolved_search_batch_pipeline: 1 prior fix", text)
        self.assertIn(f"#{pipeline.id}", text)

    def test_area_search_is_limited(self) -> None:
        _create_issue(
            title="Older match outside scan limit",
            affected_files=["backend/apps/resolved_search_limited/tasks.py"],
            resolved_at=timezone.now() - timedelta(days=3),
        )
        _create_issue(
            title="Newest non-match",
            affected_files=["backend/apps/resolved_search_other/tasks.py"],
            resolved_at=timezone.now(),
        )
        output = StringIO()

        call_command(
            "search_resolved_issues",
            area="backend/apps/resolved_search_limited",
            scan_limit=1,
            stdout=output,
        )

        self.assertIn("0 matches", output.getvalue())


def _create_issue(
    *,
    title: str,
    affected_files: list[str],
    resolved_at=None,
) -> AutoIssue:
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"resolved-search-{AutoIssue.objects.count()}",
        fingerprint=f"resolved-search-{AutoIssue.objects.count()}",
        title=title,
        description="Resolved search command test issue.",
        affected_files=affected_files,
        severity=AutoIssue.SEVERITY_MEDIUM,
        status=AutoIssue.STATUS_RESOLVED,
        resolved_at=resolved_at or timezone.now(),
        resolved_by="codex-test",
        lessons_learned="Trap: broad searches must stay fast.\nFix: use bounded scans.",
    )
