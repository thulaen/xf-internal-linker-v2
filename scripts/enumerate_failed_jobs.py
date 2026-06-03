#!/usr/bin/env python3
"""List failed GitHub Actions jobs as file_ci_failure argument arrays."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from typing import Any


_MAX_ERROR_EXCERPT_CHARS = 500
_GH_TIMEOUT_SECONDS = 30
_DEFAULT_WORKFLOW = "CI"


def fetch_failed_run_jobs(*, run_id: str, repo: str) -> list[dict[str, Any]]:
    """Fetch jobs for one workflow run through the GitHub command-line tool."""
    endpoint = f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        capture_output=True,
        check=False,
        text=True,
        timeout=_GH_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api returned a non-zero exit code")
    payload = json.loads(result.stdout or "[]")
    jobs = _extract_jobs(payload)
    return [job for job in jobs if isinstance(job, dict)]


def _extract_jobs(payload: Any) -> list[Any]:
    """Collect jobs from one API page or many slurped pages."""
    if isinstance(payload, dict):
        jobs = payload.get("jobs", [])
        return jobs if isinstance(jobs, list) else []
    if not isinstance(payload, list):
        raise RuntimeError("gh api response did not include workflow job pages")
    jobs: list[Any] = []
    for page in payload:
        if isinstance(page, dict):
            page_jobs = page.get("jobs", [])
            if isinstance(page_jobs, list):
                jobs.extend(page_jobs)
    return jobs


def commands_for_failed_jobs(
    jobs: Iterable[dict[str, Any]],
    *,
    run_id: str,
    workflow: str,
    repo: str,
    excerpt_lookup: Callable[[dict[str, Any], str], str] | None = None,
) -> list[list[str]]:
    """Build one manage.py argument list for each failed job."""
    lookup = excerpt_lookup or default_error_excerpt
    commands: list[list[str]] = []
    for job in jobs:
        if job.get("conclusion") != "failure":
            continue
        step = first_failed_step_name(job)
        excerpt = lookup(job, step)[:_MAX_ERROR_EXCERPT_CHARS]
        commands.append(_command_args(run_id, job, step, excerpt, workflow, repo))
    return commands


def first_failed_step_name(job: dict[str, Any]) -> str:
    """Return the first failed step name, or the job name as a fallback."""
    for step in job.get("steps", []) or []:
        if isinstance(step, dict) and step.get("conclusion") == "failure":
            return str(step.get("name") or job.get("name") or "unknown")
    return str(job.get("name") or "unknown")


def default_error_excerpt(job: dict[str, Any], step: str) -> str:
    """Return a short failure summary when raw logs are unavailable."""
    job_name = str(job.get("name") or "unknown")
    job_url = str(job.get("html_url") or job.get("url") or "")
    detail = f"{job_name} failed at {step}"
    if job_url:
        detail = f"{detail}; see job {job_url}"
    return detail[:_MAX_ERROR_EXCERPT_CHARS]


def _command_args(
    run_id: str,
    job: dict[str, Any],
    step: str,
    excerpt: str,
    workflow: str,
    repo: str,
) -> list[str]:
    return [
        "--run-id",
        run_id,
        "--job-name",
        str(job.get("name") or "unknown"),
        "--step",
        step,
        "--error-excerpt",
        excerpt,
        "--workflow",
        workflow,
        "--repo",
        repo,
    ]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--workflow", default=os.environ.get("GITHUB_WORKFLOW", _DEFAULT_WORKFLOW))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if not args.repo:
        raise SystemExit("--repo or GITHUB_REPOSITORY is required")
    jobs = fetch_failed_run_jobs(run_id=args.run_id, repo=args.repo)
    for command_args in commands_for_failed_jobs(
        jobs,
        run_id=args.run_id,
        workflow=args.workflow,
        repo=args.repo,
    ):
        print(json.dumps(command_args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
