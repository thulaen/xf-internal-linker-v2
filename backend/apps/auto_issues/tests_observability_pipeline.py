"""Tests for observability-pipeline freshness checking.

Given AutoIssues from observability sources with various last_seen times,
When pipeline_freshness / silent_sources run over a window,
Then in-window issues count and out-of-window ones do not.

These tests use DELTA assertions (count before vs after) rather than absolute
counts, so they are robust to any pre-existing rows in a reused test database.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import observability_pipeline as op


def _recent_count(source: str, hours: int = 24) -> int:
    for f in op.pipeline_freshness(hours=hours):
        if f.source == source:
            return f.recent_count
    return -1


def _issue(source: str, *, age_hours: float) -> AutoIssue:
    issue = AutoIssue.objects.create(
        source=source,
        external_id=f"{source}-obs-{AutoIssue.objects.count()}",
        title=f"{source} finding",
    )
    AutoIssue.objects.filter(pk=issue.pk).update(
        last_seen=timezone.now() - timedelta(hours=age_hours)
    )
    return issue


class PipelineFreshnessTests(TestCase):
    def test_recent_issue_increments_count(self) -> None:
        before = _recent_count(AutoIssue.SOURCE_LOKI)
        _issue(AutoIssue.SOURCE_LOKI, age_hours=1)
        self.assertEqual(_recent_count(AutoIssue.SOURCE_LOKI), before + 1)

    def test_old_issue_not_counted_in_window(self) -> None:
        before = _recent_count(AutoIssue.SOURCE_TEMPO, hours=24)
        _issue(AutoIssue.SOURCE_TEMPO, age_hours=48)
        self.assertEqual(_recent_count(AutoIssue.SOURCE_TEMPO, hours=24), before)

    def test_issue_drops_out_of_shorter_window(self) -> None:
        before_1h = _recent_count(AutoIssue.SOURCE_GLITCHTIP, hours=1)
        before_24h = _recent_count(AutoIssue.SOURCE_GLITCHTIP, hours=24)
        _issue(AutoIssue.SOURCE_GLITCHTIP, age_hours=2)
        # The age-2h issue is inside the 24h window but outside the 1h window.
        self.assertEqual(_recent_count(AutoIssue.SOURCE_GLITCHTIP, hours=24), before_24h + 1)
        self.assertEqual(_recent_count(AutoIssue.SOURCE_GLITCHTIP, hours=1), before_1h)

    def test_silent_flag_is_zero_count(self) -> None:
        # Pure logic: a zero recent_count means silent.
        self.assertTrue(op.SourceFreshness("x", 0, True).is_silent)
        self.assertFalse(op.SourceFreshness("x", 3, False).is_silent)

    def test_silent_sources_excludes_fresh_source(self) -> None:
        _issue(AutoIssue.SOURCE_FARO, age_hours=1)
        self.assertNotIn(AutoIssue.SOURCE_FARO, op.silent_sources(hours=24))
