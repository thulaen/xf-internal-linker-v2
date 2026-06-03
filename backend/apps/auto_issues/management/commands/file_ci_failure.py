# xf: no_dry_run -- filing the CI failure AutoIssue is the command's only purpose.
"""File one GitHub Actions failed job as an AutoIssue."""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services import gh_actions_history
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_CATEGORY_KEY = "ci_job_failure"
_CATEGORY_LABEL = "CI job failure"
_MAX_EXCERPT_CHARS = 500
_MAX_DESCRIPTION_CHARS = 4000
_MAX_TITLE_CHARS = 200
_MAX_OBSERVATIONS = 50
_MAX_KEY_CHARS = 40
_PRIORITY_CREATED = 0.75
_PRIORITY_REPEAT_STEP = 0.05
_PRIORITY_MAX = 1.0
_KEY_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def file_ci_failure(
    *,
    run_id: str,
    job_name: str,
    step: str,
    error_excerpt: str,
    workflow: str,
    repo: str,
    branch: str = "",
    commit_sha: str = "",
    commit_message_first_line: str = "",
    failed_at: str = "",
    duration_seconds: int = 0,
    run_url: str = "",
) -> tuple[AutoIssue, bool]:
    """Create or update one AutoIssue for a failed CI job."""
    _validate_inputs(run_id, job_name, step, error_excerpt, workflow, repo)
    now = timezone.now()
    excerpt = _clean_excerpt(error_excerpt)
    run_url = run_url or _run_url(repo, run_id)
    history = {
        "run_id": run_id,
        "workflow": workflow,
        "branch": branch,
        "commit_sha": commit_sha,
        "commit_message_first_line": commit_message_first_line,
        "failed_at": failed_at or now.isoformat(),
        "job_name": job_name,
        "step": step,
        "excerpt": excerpt,
        "duration_seconds": duration_seconds,
        "run_url": run_url,
    }
    fingerprint = canonical_fingerprint(excerpt)
    external_id = _external_id(workflow, job_name, fingerprint)
    existing = AutoIssue.objects.filter(external_id=external_id).first()
    if existing is not None:
        _update_existing(existing, run_id, run_url, step, excerpt, now)
        _append_open_history(existing, history)
        return existing, False
    issue = _create_issue(
        category=_get_or_create_category(),
        run_id=run_id,
        run_url=run_url,
        job_name=job_name,
        step=step,
        excerpt=excerpt,
        workflow=workflow,
        fingerprint=fingerprint,
        external_id=external_id,
        now=now,
    )
    _append_open_history(issue, history)
    return issue, True


def _validate_inputs(
    run_id: str,
    job_name: str,
    step: str,
    error_excerpt: str,
    workflow: str,
    repo: str,
) -> None:
    required = {
        "run_id": run_id,
        "job_name": job_name,
        "step": step,
        "error_excerpt": error_excerpt,
        "workflow": workflow,
        "repo": repo,
    }
    missing = [name for name, value in required.items() if not str(value).strip()]
    if missing:
        raise CommandError(f"missing required value(s): {', '.join(missing)}")
    if "/" not in repo:
        raise CommandError("repo must look like owner/name")


def _get_or_create_category() -> AutoIssueCategory:
    category, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": "GitHub Actions job failure filed from a completed workflow run.",
            "sort_order": 240,
        },
    )
    return category


def _external_id(workflow: str, job_name: str, fingerprint: str) -> str:
    return f"ci_failure::{_key(workflow)}::{_key(job_name)}::{fingerprint}"


def _key(value: str) -> str:
    cleaned = _KEY_CHARS.sub("-", value.strip()).strip("-")
    return (cleaned or "unknown")[:_MAX_KEY_CHARS]


def _tag(value: str) -> str:
    return _key(value).lower()[:64]


def _run_url(repo: str, run_id: str) -> str:
    return f"https://github.com/{repo.strip()}/actions/runs/{run_id.strip()}"


def _clean_excerpt(value: str) -> str:
    return " ".join(value.strip().split())[:_MAX_EXCERPT_CHARS]


def _observation(
    *,
    run_id: str,
    run_url: str,
    step: str,
    excerpt: str,
    now,
    occurrence_count: int,
) -> dict:
    return {
        "source": AutoIssue.SOURCE_GH_CI,
        "run_id": str(run_id),
        "run_url": run_url,
        "step": step[:120],
        "error_excerpt": excerpt[:200],
        "first_seen": now.isoformat(),
        "last_seen": now.isoformat(),
        "occurrence_count": occurrence_count,
    }


def _history_entry(
    *,
    issue: AutoIssue,
    run_id: str,
    workflow: str,
    branch: str,
    commit_sha: str,
    commit_message_first_line: str,
    failed_at: str,
    job_name: str,
    step: str,
    excerpt: str,
    duration_seconds: int,
    run_url: str,
) -> dict:
    return {
        "run_id": str(run_id),
        "workflow": workflow,
        "branch": branch,
        "commit_sha": commit_sha,
        "commit_message_first_line": commit_message_first_line,
        "failed_at": failed_at,
        "failing_jobs": [{"name": job_name, "step": step, "error_excerpt": excerpt}],
        "duration_seconds": max(int(duration_seconds), 0),
        "run_url": run_url,
        "autoissue_ids": [issue.pk],
        "status": "open",
    }


def _append_open_history(issue: AutoIssue, values: dict) -> None:
    gh_actions_history.append_history(_history_entry(issue=issue, **values))


def _update_existing(
    issue: AutoIssue,
    run_id: str,
    run_url: str,
    step: str,
    excerpt: str,
    now,
) -> None:
    issue.occurrence_count += 1
    issue.last_seen = now
    issue.priority_score = max(_PRIORITY_MAX, issue.priority_score + _PRIORITY_REPEAT_STEP)
    issue.status = AutoIssue.STATUS_OPEN
    issue.resolved_at = None
    issue.resolved_by = ""
    issue.fix_commit_sha = ""
    issue.source_observations = [
        *(issue.source_observations or []),
        _observation(
            run_id=run_id,
            run_url=run_url,
            step=step,
            excerpt=excerpt,
            now=now,
            occurrence_count=issue.occurrence_count,
        ),
    ][-_MAX_OBSERVATIONS:]
    issue.save(update_fields=[
        "occurrence_count",
        "last_seen",
        "priority_score",
        "status",
        "resolved_at",
        "resolved_by",
        "fix_commit_sha",
        "source_observations",
    ])


def _create_issue(
    *,
    category: AutoIssueCategory,
    run_id: str,
    run_url: str,
    job_name: str,
    step: str,
    excerpt: str,
    workflow: str,
    fingerprint: str,
    external_id: str,
    now,
) -> AutoIssue:
    title = f"[gh-ci-fail] {workflow}/{job_name} failed at {step}"[:_MAX_TITLE_CHARS]
    description = (
        f"GitHub Actions run: {run_url}\n"
        f"Workflow: {workflow}\n"
        f"Job: {job_name}\n"
        f"Step: {step}\n"
        f"Error excerpt: {excerpt}"
    )[:_MAX_DESCRIPTION_CHARS]
    lessons = (
        f"Trap: CI failed at {step} with output {excerpt}; see run {run_url}\n"
        "Fix shape: open the run link, inspect the failed job logs, and fix the "
        "underlying code or workflow error."
    )
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_GH_CI,
        external_id=external_id,
        fingerprint=fingerprint,
        canonical_fingerprint=fingerprint,
        title=title,
        description=description,
        severity=AutoIssue.SEVERITY_HIGH,
        category=category,
        status=AutoIssue.STATUS_OPEN,
        priority_score=_PRIORITY_CREATED,
        occurrence_count=1,
        first_seen=now,
        last_seen=now,
        lessons_learned=lessons,
        concept_tags=sorted({"ci-failure", _tag(workflow), _tag(job_name)}),
        source_observations=[
            _observation(
                run_id=run_id,
                run_url=run_url,
                step=step,
                excerpt=excerpt,
                now=now,
                occurrence_count=1,
            )
        ],
    )


class Command(BaseCommand):
    help = "File one GitHub Actions failed job as an AutoIssue."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--run-id", required=True)
        parser.add_argument("--job-name", required=True)
        parser.add_argument("--step", required=True)
        parser.add_argument("--error-excerpt", required=True)
        parser.add_argument("--workflow", required=True)
        parser.add_argument("--repo", required=True)
        parser.add_argument("--branch", default="")
        parser.add_argument("--commit-sha", default="")
        parser.add_argument("--commit-message-first-line", default="")
        parser.add_argument("--failed-at", default="")
        parser.add_argument("--duration-seconds", type=int, default=0)
        parser.add_argument("--run-url", default="")

    def handle(self, *args, **options) -> None:
        issue, created = file_ci_failure(
            run_id=options["run_id"],
            job_name=options["job_name"],
            step=options["step"],
            error_excerpt=options["error_excerpt"],
            workflow=options["workflow"],
            repo=options["repo"],
            branch=options["branch"],
            commit_sha=options["commit_sha"],
            commit_message_first_line=options["commit_message_first_line"],
            failed_at=options["failed_at"],
            duration_seconds=options["duration_seconds"],
            run_url=options["run_url"],
        )
        if created:
            self.stdout.write(f"[CI FAILURE FILED: AutoIssue=#{issue.pk}]")
        else:
            self.stdout.write(f"[CI FAILURE DEDUPED: matched AutoIssue=#{issue.pk}]")
