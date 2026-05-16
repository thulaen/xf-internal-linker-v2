"""Tests for the print_open_issues quota picker command."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue


def _make_issue(**overrides) -> AutoIssue:
    index = AutoIssue.objects.count() + 1
    defaults = {
        "source": AutoIssue.SOURCE_AGENT,
        "external_id": f"quota-print-{index}",
        "fingerprint": f"quota-print-fp-{index}",
        "canonical_fingerprint": f"quota-print-canon-{index}",
        "title": f"Quota print issue {index}",
        "status": AutoIssue.STATUS_OPEN,
        "priority_score": float(100 - index),
        "spam_score": 0.0,
    }
    defaults.update(overrides)
    return AutoIssue.objects.create(**defaults)


class PrintOpenIssuesCommandTests(TestCase):
    def test_prints_zero_open_without_ci_probe(self) -> None:
        out = StringIO()
        call_command("print_open_issues", stdout=out)

        self.assertIn("[REGISTRY READ: 0 open auto-issues]", out.getvalue())

    @mock.patch(
        "apps.auto_issues.management.commands.print_open_issues.subprocess.run",
        side_effect=FileNotFoundError,
    )
    def test_printed_quota_rows_skip_duplicate_canonical_work(self, _mock_run) -> None:
        first = _make_issue(
            title="Same quota root cause",
            canonical_fingerprint="same-root",
            priority_score=90,
        )
        duplicate = _make_issue(
            title="Same quota root cause copy",
            canonical_fingerprint="same-root",
            priority_score=80,
        )
        unique = _make_issue(title="Unique quota root cause", priority_score=70)

        out = StringIO()
        call_command("print_open_issues", "--limit", "2", stdout=out)
        text = out.getvalue()

        self.assertIn(f"#{first.id}", text)
        self.assertIn(f"#{unique.id}", text)
        self.assertNotIn(f"#{duplicate.id}", text)

    @mock.patch(
        "apps.auto_issues.management.commands.print_open_issues.subprocess.run",
        side_effect=FileNotFoundError,
    )
    def test_source_filter_uses_source_specific_header(self, _mock_run) -> None:
        _make_issue(source=AutoIssue.SOURCE_AGENT, title="Agent row")
        glitchtip = _make_issue(
            source=AutoIssue.SOURCE_GLITCHTIP,
            external_id="gt-print-1",
            title="GlitchTip row",
        )

        out = StringIO()
        call_command(
            "print_open_issues",
            "--source",
            AutoIssue.SOURCE_GLITCHTIP,
            stdout=out,
        )
        text = out.getvalue()

        self.assertIn(f"#{glitchtip.id}", text)
        self.assertIn("showing top 1", text)
        self.assertNotIn("agent /", text)

    @mock.patch(
        "apps.auto_issues.management.commands.print_open_issues.subprocess.run",
        return_value=SimpleNamespace(returncode=1, stdout=""),
    )
    def test_ci_probe_nonzero_prints_skipped(self, _mock_run) -> None:
        _make_issue()
        out = StringIO()
        call_command("print_open_issues", stdout=out)

        self.assertIn("CI FAILED RUNS READ: skipped", out.getvalue())

    @mock.patch(
        "apps.auto_issues.management.commands.print_open_issues.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="{not-json"),
    )
    def test_ci_probe_bad_json_prints_unparseable(self, _mock_run) -> None:
        _make_issue()
        out = StringIO()
        call_command("print_open_issues", stdout=out)

        self.assertIn("gh JSON unparseable", out.getvalue())

    @mock.patch(
        "apps.auto_issues.management.commands.print_open_issues.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="[]"),
    )
    def test_ci_probe_empty_list_prints_zero_failed_runs(self, _mock_run) -> None:
        _make_issue()
        out = StringIO()
        call_command("print_open_issues", stdout=out)

        self.assertIn("0 latest", out.getvalue())

    @mock.patch(
        "apps.auto_issues.management.commands.print_open_issues.subprocess.run",
        return_value=SimpleNamespace(
            returncode=0,
            stdout=(
                '[{"databaseId": 123, "workflowName": "CI", "name": "test", '
                '"headBranch": "master", "url": "https://example.invalid/run"}]'
            ),
        ),
    )
    def test_ci_probe_failed_runs_are_printed(self, _mock_run) -> None:
        _make_issue()
        out = StringIO()
        call_command("print_open_issues", stdout=out)

        self.assertIn("[CI FAILED RUNS READ: 1 latest", out.getvalue())
        self.assertIn("#123 [CI/test]", out.getvalue())

    @mock.patch(
        "apps.auto_issues.management.commands.print_open_issues.subprocess.run",
        side_effect=FileNotFoundError,
    )
    def test_coverage_gap_rows_are_unique(self, _mock_run) -> None:
        first = _make_issue(
            title="[coverage-gap] same area",
            canonical_fingerprint="same-coverage-gap",
            priority_score=90,
        )
        duplicate = _make_issue(
            title="[coverage-gap] same area copy",
            canonical_fingerprint="same-coverage-gap",
            priority_score=80,
        )
        unique = _make_issue(title="[coverage-gap] unique area", priority_score=70)

        out = StringIO()
        call_command("print_open_issues", stdout=out)
        text = out.getvalue()

        self.assertIn(f"#{first.id}", text)
        self.assertIn(f"#{unique.id}", text)
        self.assertNotIn(f"#{duplicate.id} [agent/medium] [coverage-gap]", text)
