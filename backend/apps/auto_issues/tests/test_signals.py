"""Tests for apps.auto_issues.signals.

Verifies that GitHub Actions CI issue resolutions are recorded in the
history log, and that failures in the history writer do not propagate.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.auto_issues.models import AutoIssue


class GhActionsResolutionSignalTests(TestCase):
    def _create_gh_ci_issue(self, status: str = AutoIssue.STATUS_OPEN) -> AutoIssue:
        return AutoIssue.objects.create(
            source=AutoIssue.SOURCE_GH_CI,
            external_id="gh-signal-test-1",
            fingerprint="gh-signal-fp-1",
            title="CI workflow failure",
            severity=AutoIssue.SEVERITY_HIGH,
            status=status,
        )

    def test_resolving_open_gh_ci_issue_appends_history(self):
        issue = self._create_gh_ci_issue(status=AutoIssue.STATUS_OPEN)
        with patch(
            "apps.auto_issues.services.gh_actions_history.append_resolution_history"
        ) as mock_append:
            issue.status = AutoIssue.STATUS_RESOLVED
            issue.save()
        mock_append.assert_called_once_with(issue)

    def test_non_gh_ci_source_does_not_append_history(self):
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="agent-signal-test-1",
            fingerprint="agent-signal-fp-1",
            title="Agent found issue",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_OPEN,
        )
        with patch(
            "apps.auto_issues.services.gh_actions_history.append_resolution_history"
        ) as mock_append:
            issue.status = AutoIssue.STATUS_RESOLVED
            issue.save()
        mock_append.assert_not_called()

    def test_already_resolved_gh_ci_does_not_append_again(self):
        """Pre_save remembers prior status=resolved → post_save skips append."""
        issue = self._create_gh_ci_issue(status=AutoIssue.STATUS_RESOLVED)
        with patch(
            "apps.auto_issues.services.gh_actions_history.append_resolution_history"
        ) as mock_append:
            issue.resolved_by = "updated-by-test"
            issue.save()
        mock_append.assert_not_called()

    def test_oserror_in_append_does_not_propagate(self):
        issue = self._create_gh_ci_issue(status=AutoIssue.STATUS_OPEN)
        with patch(
            "apps.auto_issues.services.gh_actions_history.append_resolution_history",
            side_effect=OSError("file locked"),
        ):
            issue.status = AutoIssue.STATUS_RESOLVED
            issue.save()  # must not raise OSError

    def test_creating_resolved_gh_ci_does_not_append(self):
        """Brand-new (created=True) rows must not trigger the history writer."""
        with patch(
            "apps.auto_issues.services.gh_actions_history.append_resolution_history"
        ) as mock_append:
            self._create_gh_ci_issue(status=AutoIssue.STATUS_RESOLVED)
        mock_append.assert_not_called()

    def test_gh_ci_transitioning_to_open_does_not_append(self):
        """Resolving only fires when status == RESOLVED, not on any other transition."""
        issue = self._create_gh_ci_issue(status=AutoIssue.STATUS_RESOLVED)
        with patch(
            "apps.auto_issues.services.gh_actions_history.append_resolution_history"
        ) as mock_append:
            issue.status = AutoIssue.STATUS_OPEN
            issue.save()
        mock_append.assert_not_called()
