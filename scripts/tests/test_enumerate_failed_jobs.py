"""Convention tests for scripts/enumerate_failed_jobs.py pure helpers.

BDD:
  Given GitHub Actions job dicts
  When commands_for_failed_jobs / first_failed_step_name / default_error_excerpt
       / _extract_jobs run
  Then only failed jobs yield command arrays, the first failed step name is
       chosen, the excerpt wording is exact, and slurped pages are flattened —
       killing mutation survivors on the changed lines.

The only subprocess (fetch_failed_run_jobs / gh api) is never invoked here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import TestCase

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


efj = _load("enumerate_failed_jobs", "enumerate_failed_jobs.py")


class TestFirstFailedStepName(TestCase):
    def test_returns_failed_step_name(self):
        job = {"name": "build", "steps": [
            {"name": "checkout", "conclusion": "success"},
            {"name": "pytest", "conclusion": "failure"},
        ]}
        self.assertEqual(efj.first_failed_step_name(job), "pytest")

    def test_falls_back_to_job_name_when_no_failed_step(self):
        job = {"name": "lint", "steps": [{"name": "ruff", "conclusion": "success"}]}
        self.assertEqual(efj.first_failed_step_name(job), "lint")

    def test_unknown_when_no_name(self):
        self.assertEqual(efj.first_failed_step_name({"steps": []}), "unknown")


class TestDefaultErrorExcerpt(TestCase):
    def test_excerpt_with_url(self):
        job = {"name": "build", "html_url": "https://x/job/1"}
        out = efj.default_error_excerpt(job, "compile")
        self.assertEqual(out, "build failed at compile; see job https://x/job/1")

    def test_excerpt_without_url(self):
        out = efj.default_error_excerpt({"name": "build"}, "compile")
        self.assertEqual(out, "build failed at compile")


class TestExtractJobs(TestCase):
    def test_single_page_dict(self):
        self.assertEqual(efj._extract_jobs({"jobs": [{"name": "a"}]}), [{"name": "a"}])

    def test_slurped_pages_flattened(self):
        payload = [{"jobs": [{"name": "a"}]}, {"jobs": [{"name": "b"}]}]
        self.assertEqual(efj._extract_jobs(payload), [{"name": "a"}, {"name": "b"}])

    def test_non_list_non_dict_raises(self):
        with self.assertRaises(RuntimeError):
            efj._extract_jobs("nope")


class TestCommandsForFailedJobs(TestCase):
    def _jobs(self):
        return [
            {"name": "ok-job", "conclusion": "success",
             "steps": [{"name": "s", "conclusion": "success"}]},
            {"name": "bad-job", "conclusion": "failure",
             "steps": [{"name": "compile", "conclusion": "failure"}]},
        ]

    def test_only_failed_jobs_yield_commands(self):
        cmds = efj.commands_for_failed_jobs(
            self._jobs(), run_id="42", workflow="CI", repo="o/r")
        self.assertEqual(len(cmds), 1)

    def test_command_args_carry_run_id_and_step(self):
        cmds = efj.commands_for_failed_jobs(
            self._jobs(), run_id="42", workflow="CI", repo="o/r")
        args = cmds[0]
        self.assertEqual(args[args.index("--run-id") + 1], "42")
        self.assertEqual(args[args.index("--job-name") + 1], "bad-job")
        self.assertEqual(args[args.index("--step") + 1], "compile")
        self.assertEqual(args[args.index("--workflow") + 1], "CI")
        self.assertEqual(args[args.index("--repo") + 1], "o/r")

    def test_excerpt_truncated_to_limit(self):
        jobs = [{"name": "j", "conclusion": "failure",
                 "steps": [{"name": "s", "conclusion": "failure"}]}]
        cmds = efj.commands_for_failed_jobs(
            jobs, run_id="1", workflow="CI", repo="o/r",
            excerpt_lookup=lambda job, step: "X" * 999)
        excerpt = cmds[0][cmds[0].index("--error-excerpt") + 1]
        self.assertEqual(len(excerpt), 500)
