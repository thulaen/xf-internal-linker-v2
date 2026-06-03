"""Tests for filing GitHub Actions job failures as AutoIssues."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml
from django.core.management import call_command
from django.test import TransactionTestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


REPO_ROOT = Path(os.environ.get("XF_REPO_ROOT", "/repo"))
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-failure-to-autoissue.yml"
WORKFLOW_TEST_PATH = REPO_ROOT / ".github" / "workflows" / "test_ci_failure_workflow.yml.test"
SCRIPT_PATH = REPO_ROOT / "scripts" / "enumerate_failed_jobs.py"


class FileCiFailureTests(TransactionTestCase):
    """Exercise command behavior and the workflow contract."""

    reset_sequences = False

    def tearDown(self) -> None:
        AutoIssue.objects.filter(external_id__startswith="ci_failure::").delete()

    def _run(
        self,
        *,
        run_id: str = "123456",
        job_name: str = "frontend-build-and-test",
        step: str = "Trivy",
        error_excerpt: str = "HIGH vulnerability in package foo",
        workflow: str = "CI",
    ) -> str:
        out = StringIO()
        call_command(
            "file_ci_failure",
            run_id=run_id,
            job_name=job_name,
            step=step,
            error_excerpt=error_excerpt,
            workflow=workflow,
            repo="thulaen/xf-internal-linker-v2",
            stdout=out,
        )
        return out.getvalue()

    def test_creates_autoissue_with_gh_ci_source(self) -> None:
        output = self._run()
        row = AutoIssue.objects.get(external_id__startswith="ci_failure::CI::")

        self.assertIn("[CI FAILURE FILED:", output)
        self.assertEqual(row.source, AutoIssue.SOURCE_GH_CI)
        self.assertEqual(row.category.key, "ci_job_failure")
        self.assertIn("frontend-build-and-test", row.title)

    def test_includes_run_url_in_description(self) -> None:
        self._run(run_id="98765")
        row = AutoIssue.objects.get(external_id__startswith="ci_failure::")

        self.assertIn(
            "https://github.com/thulaen/xf-internal-linker-v2/actions/runs/98765",
            row.description,
        )

    def test_lessons_learned_template_populated(self) -> None:
        self._run(step="Install deps", error_excerpt="pip failed with exit code 1")
        row = AutoIssue.objects.get(external_id__startswith="ci_failure::")

        self.assertIn(
            "Trap: CI failed at Install deps with output pip failed with exit code 1; see run",
            row.lessons_learned,
        )

    def test_dedups_on_job_name_and_error_fingerprint(self) -> None:
        self._run(run_id="100")
        self._run(run_id="200")
        row = AutoIssue.objects.get(external_id__startswith="ci_failure::")

        self.assertEqual(row.occurrence_count, 2)
        self.assertEqual([obs["run_id"] for obs in row.source_observations], ["100", "200"])

    def test_repeated_ci_failure_reopens_resolved_issue_with_lesson_preserved(self) -> None:
        self._run(run_id="100")
        row = AutoIssue.objects.get(external_id__startswith="ci_failure::")
        lesson = "Trap: CI job failed before.\nFix shape: inspect failed logs."
        row.status = AutoIssue.STATUS_RESOLVED
        row.resolved_at = timezone.now()
        row.resolved_by = "codex-test"
        row.fix_commit_sha = "abc1234"
        row.lessons_learned = lesson
        row.save(
            update_fields=[
                "status",
                "resolved_at",
                "resolved_by",
                "fix_commit_sha",
                "lessons_learned",
            ]
        )

        self._run(run_id="200")
        row.refresh_from_db()

        self.assertEqual(row.status, AutoIssue.STATUS_OPEN)
        self.assertIsNone(row.resolved_at)
        self.assertEqual(row.resolved_by, "")
        self.assertEqual(row.fix_commit_sha, "")
        self.assertEqual(row.lessons_learned, lesson)
        self.assertEqual(row.occurrence_count, 2)

    def test_concept_tags_include_failing_workflow_name(self) -> None:
        self._run(workflow="Scoped Mutation (CI)")
        row = AutoIssue.objects.get(external_id__startswith="ci_failure::")

        self.assertIn("scoped-mutation-ci", row.concept_tags)

    def test_workflow_yaml_parses_and_targets_failed_runs(self) -> None:
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
        contract = yaml.safe_load(WORKFLOW_TEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(contract["workflow"], "ci-failure-to-autoissue.yml")
        self.assertEqual(
            workflow["on"]["workflow_run"]["workflows"],
            ["CI", "Scoped Mutation (CI)"],
        )
        self.assertEqual(workflow["on"]["workflow_run"]["types"], ["completed"])
        job = workflow["jobs"]["file-failures"]
        self.assertEqual(
            job["if"],
            "${{ github.event.workflow_run.conclusion == 'failure' }}",
        )
        run_script = job["steps"][-1]["run"]
        self.assertIn("file_ci_failure", run_script)

    def test_workflow_files_into_running_backend_not_runner_database(self) -> None:
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
        job = workflow["jobs"]["file-failures"]
        run_script = job["steps"][-1]["run"]

        self.assertEqual(job["runs-on"], "self-hosted")
        for token in ['"docker"', '"compose"', '"exec"', '"-T"', '"backend"']:
            self.assertIn(token, run_script)
        self.assertNotIn("python backend/manage.py file_ci_failure", run_script)

    def test_workflow_uses_bash_shell_on_self_hosted_runner(self) -> None:
        workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
        step = workflow["jobs"]["file-failures"]["steps"][-1]

        self.assertEqual(step["shell"], "bash")

    def test_enumerator_prints_file_ci_failure_arguments_for_failed_step(self) -> None:
        module = _load_enumerator()
        jobs = [
            {
                "name": "frontend-build-and-test",
                "conclusion": "failure",
                "steps": [
                    {"name": "Install deps", "conclusion": "success"},
                    {"name": "Trivy", "conclusion": "failure"},
                ],
            }
        ]

        commands = module.commands_for_failed_jobs(
            jobs,
            run_id="123456",
            workflow="CI",
            repo="thulaen/xf-internal-linker-v2",
            excerpt_lookup=lambda job, step: "first 500 characters",
        )

        self.assertEqual(1, len(commands))
        self.assertIn("--job-name", commands[0])
        self.assertIn("frontend-build-and-test", commands[0])
        self.assertIn("--step", commands[0])
        self.assertIn("Trivy", commands[0])

    def test_writes_history_line_alongside_autoissue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "github_actions_failures.jsonl"
            with patch(
                "apps.auto_issues.management.commands.file_ci_failure.gh_actions_history.HISTORY_PATH",
                history_path,
            ):
                self._run(run_id="555", workflow="CI", step="Unit tests")

            row = AutoIssue.objects.get(external_id__startswith="ci_failure::")
            history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(history["run_id"], "555")
        self.assertEqual(history["workflow"], "CI")
        self.assertEqual(history["failing_jobs"][0]["name"], "frontend-build-and-test")
        self.assertEqual(history["failing_jobs"][0]["step"], "Unit tests")
        self.assertEqual(history["autoissue_ids"], [row.pk])
        self.assertEqual(history["status"], "open")


def _load_enumerator():
    spec = importlib.util.spec_from_file_location("enumerate_failed_jobs", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module
