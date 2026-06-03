"""Tests for GitHub Actions failure history reporting."""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory


class PrintFailedGithubActionsTests(TestCase):
    def test_since_handoff_lists_failures_after_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_handoff(root, "2026-05-21 00:10")
            _write_history(
                root,
                [
                    _failure("100", "2026-05-21T00:09:00+00:00"),
                    _failure("101", "2026-05-21T00:11:00+00:00"),
                    _failure("102", "2026-05-21T00:12:00+00:00"),
                ],
            )
            output = StringIO()

            call_command(
                "print_failed_github_actions",
                since_handoff=True,
                repo_root=str(root),
                stdout=output,
            )

        self.assertIn("2 failures since last handoff", output.getvalue())
        self.assertIn("#102, #101", output.getvalue())
        self.assertNotIn("#100", output.getvalue())

    def test_since_handoff_marker_format_exact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_handoff(root, "2026-05-21 00:10")
            _write_history(
                root,
                [
                    _failure("1", "2026-05-21T00:11:00+00:00"),
                    _failure("2", "2026-05-21T00:12:00+00:00"),
                    _failure("3", "2026-05-21T00:13:00+00:00"),
                    _failure("4", "2026-05-21T00:14:00+00:00"),
                    _failure("5", "2026-05-21T00:15:00+00:00"),
                ],
            )
            output = StringIO()

            call_command(
                "print_failed_github_actions",
                since_handoff=True,
                repo_root=str(root),
                stdout=output,
            )

        self.assertEqual(
            output.getvalue().strip(),
            "[GH ACTIONS READ: 5 failures since last handoff — picked: #5, #4, #3]",
        )

    def test_trend_groups_by_workflow_and_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(
                root,
                [
                    _failure("1", "2026-05-21T00:11:00+00:00", workflow="CI", job="backend"),
                    _failure("2", "2026-05-21T00:12:00+00:00", workflow="CI", job="backend"),
                    _failure("3", "2026-05-21T00:13:00+00:00", workflow="CI", job="frontend"),
                ],
            )
            output = StringIO()

            call_command("print_failed_github_actions", trend=True, top=5, repo_root=str(root), stdout=output)

        text = output.getvalue()
        self.assertIn("[GH ACTIONS TREND: top=5 groups=2]", text)
        self.assertIn("workflow=CI job=backend count=2", text)
        self.assertIn("workflow=CI job=frontend count=1", text)

    def test_trend_top_n_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(
                root,
                [
                    _failure("1", "2026-05-21T00:11:00+00:00", job="backend"),
                    _failure("2", "2026-05-21T00:12:00+00:00", job="frontend"),
                ],
            )
            output = StringIO()

            call_command("print_failed_github_actions", trend=True, top=1, repo_root=str(root), stdout=output)

        self.assertEqual(1, output.getvalue().count("workflow=CI job="))

    def test_resolution_appends_history_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "github_actions_failures.jsonl"
            issue = _autoissue_with_run("900")

            with patch("apps.auto_issues.services.gh_actions_history.HISTORY_PATH", history_path):
                issue.status = AutoIssue.STATUS_RESOLVED
                issue.resolved_at = timezone.now()
                issue.resolved_by = "codex-test"
                issue.lessons_learned = (
                    "Trap: failed CI runs need a closing audit line. "
                    "Fix shape: append a resolved history row when the issue closes."
                )
                issue.save()

            lines = history_path.read_text(encoding="utf-8").splitlines()
            resolved = json.loads(lines[-1])

        self.assertEqual(resolved["run_id"], "900")
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["resolved_by_autoissue_id"], issue.pk)
        self.assertIn("resolved_at", resolved)


def _write_handoff(root: Path, stamp: str) -> None:
    (root / "AGENT-HANDOFF.md").write_text(f"# {stamp} - Codex GPT-5 - Prior\n", encoding="utf-8")


def _write_history(root: Path, rows: list[dict]) -> None:
    audit = root / "audit"
    audit.mkdir(parents=True)
    (audit / "github_actions_failures.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _failure(
    run_id: str,
    failed_at: str,
    *,
    workflow: str = "CI",
    job: str = "backend",
    status: str = "open",
) -> dict:
    return {
        "run_id": run_id,
        "workflow": workflow,
        "branch": "master",
        "commit_sha": "abc123",
        "commit_message_first_line": "demo",
        "failed_at": failed_at,
        "failing_jobs": [{"name": job, "step": "pytest", "error_excerpt": "failed"}],
        "duration_seconds": 10,
        "run_url": f"https://github.com/o/r/actions/runs/{run_id}",
        "autoissue_ids": [int(run_id)],
        "status": status,
    }


def _autoissue_with_run(run_id: str) -> AutoIssue:
    category, _ = AutoIssueCategory.objects.get_or_create(
        key="ci_job_failure",
        defaults={"label": "CI job failure"},
    )
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_GH_CI,
        external_id=f"ci_failure::{run_id}",
        fingerprint=f"fp-{run_id}",
        canonical_fingerprint=f"fp-{run_id}",
        title="GitHub Actions failure",
        description="Failed run",
        severity=AutoIssue.SEVERITY_HIGH,
        category=category,
        status=AutoIssue.STATUS_OPEN,
        lessons_learned="Trap: open failure. Fix shape: resolve it.",
        source_observations=[{"run_id": run_id}],
    )
