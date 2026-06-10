# xf: no_dry_run -- filing the test-failure AutoIssue is the command's only purpose.
"""File one failed distributed-shard test as an AutoIssue.

Usage:
    python manage.py file_test_failure \\
        --tool mutmut --test-target backend.apps.audit \\
        --test-file apps/audit/tasks.py --test-name test_mutation_line_42 \\
        --failure-summary "Mutant survived: replace + with -" \\
        --severity medium --run-id run-001 --shard-id shard-0 \\
        [--artifact-ref sha256=abc... blob_path=/srv/xf/... tool=mutmut]
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_CATEGORY_KEY = "failed_test"
_CATEGORY_LABEL = "Failed test"
_MAX_KEY_CHARS = 20
_MAX_TITLE_CHARS = 200
_MAX_SUMMARY_CHARS = 600
_MAX_OBSERVATIONS = 50
_KEY_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")

_VALID_SEVERITIES = {
    "high": AutoIssue.SEVERITY_HIGH,
    "medium": AutoIssue.SEVERITY_MEDIUM,
    "low": AutoIssue.SEVERITY_LOW,
}


def _determine_source(tool: str) -> str:
    tool_lower = tool.lower()
    if tool_lower == "pytest":
        return AutoIssue.SOURCE_PYTEST_FAILURE
    if tool_lower in ("cargo_test", "cargo-test", "rust"):
        return AutoIssue.SOURCE_RUST_TEST_FAILURE
    return AutoIssue.SOURCE_TEST_FAILURE


def file_test_failure(
    *,
    tool: str,
    test_target: str,
    test_file: str,
    test_name: str,
    failure_summary: str,
    severity: str,
    run_id: str,
    shard_id: str,
    artifact_refs: list[dict] | None = None,
    worker: str = "windows",
) -> tuple[AutoIssue, str]:
    """Create or update one AutoIssue for a failed shard test.

    Returns (issue, action) where action is 'created', 'updated', or 'reopened'.
    """
    _validate(tool=tool, failure_summary=failure_summary, severity=severity)
    now = timezone.now()
    fp = _failure_fingerprint(failure_summary)
    ext_id = _external_id(tool, test_target, test_file, test_name, fp)
    sev = _VALID_SEVERITIES[severity]
    refs = list(artifact_refs or [])
    source_val = _determine_source(tool)

    existing = AutoIssue.objects.filter(
        source=source_val, external_id=ext_id
    ).first()

    if existing is not None:
        action = "reopened" if existing.status == AutoIssue.STATUS_RESOLVED else "updated"
        _update_existing(existing, run_id=run_id, shard_id=shard_id, worker=worker,
                         severity=sev, refs=refs, now=now, reopen=(action == "reopened"))
        return existing, action

    issue = _create_issue(
        source_val=source_val,
        external_id=ext_id,
        tool=tool,
        test_target=test_target,
        test_file=test_file,
        test_name=test_name,
        failure_summary=failure_summary,
        severity=sev,
        run_id=run_id,
        shard_id=shard_id,
        worker=worker,
        refs=refs,
        now=now,
    )
    return issue, "created"


def _failure_fingerprint(summary: str) -> str:
    """Normalise and hash the failure summary for stable deduplication."""
    return canonical_fingerprint(summary)


def _validate(*, tool: str, failure_summary: str, severity: str) -> None:
    missing = [n for n, v in [("tool", tool), ("failure_summary", failure_summary)] if not str(v).strip()]
    if missing:
        raise CommandError(f"missing required value(s): {', '.join(missing)}")
    if severity not in _VALID_SEVERITIES:
        raise CommandError(f"severity must be one of: {', '.join(_VALID_SEVERITIES)}")


def _key(value: str) -> str:
    cleaned = _KEY_CHARS.sub("-", value.strip()).strip("-")
    return (cleaned or "unknown")[:_MAX_KEY_CHARS]


def _external_id(tool: str, test_target: str, test_file: str, test_name: str, fp: str) -> str:
    return f"failed_test::{_key(tool)}::{_key(test_target)}::{_key(test_file)}::{_key(test_name)}::{fp}"


def _get_or_create_category() -> AutoIssueCategory:
    category, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": "A test that failed during a distributed shard run.",
            "sort_order": 250,
        },
    )
    return category


def _observation(*, source_val: str, run_id: str, shard_id: str, worker: str, now) -> dict:
    return {
        "source": source_val,
        "run_id": run_id,
        "shard_id": shard_id,
        "worker": worker,
        "first_seen": now.isoformat(),
        "last_seen": now.isoformat(),
        "occurrence_count": 1,
    }


def _create_issue(
    *,
    source_val: str,
    external_id: str,
    tool: str,
    test_target: str,
    test_file: str,
    test_name: str,
    failure_summary: str,
    severity: str,
    run_id: str,
    shard_id: str,
    worker: str,
    refs: list[dict],
    now,
) -> AutoIssue:
    title = f"[{tool}] {test_target}: {test_name}"[:_MAX_TITLE_CHARS]
    description = f"Failure summary: {failure_summary[:_MAX_SUMMARY_CHARS]}\nFile: {test_file}\nRun: {run_id} shard: {shard_id} worker: {worker}"
    obs = _observation(source_val=source_val, run_id=run_id, shard_id=shard_id, worker=worker, now=now)
    fp = _failure_fingerprint(failure_summary)
    return AutoIssue.objects.create(
        source=source_val,
        external_id=external_id,
        category=_get_or_create_category(),
        title=title,
        description=description,
        severity=severity,
        status=AutoIssue.STATUS_OPEN,
        occurrence_count=1,
        source_observations=[obs],
        artifact_refs=refs,
        fingerprint=fp,
        canonical_fingerprint=fp,
    )


def _update_existing(
    issue: AutoIssue,
    *,
    run_id: str,
    shard_id: str,
    worker: str,
    severity: str,
    refs: list[dict],
    now,
    reopen: bool,
) -> None:
    issue.occurrence_count += 1
    obs = issue.source_observations or []
    obs = obs[-(_MAX_OBSERVATIONS - 1):] if len(obs) >= _MAX_OBSERVATIONS else obs
    obs.append(_observation(source_val=issue.source, run_id=run_id, shard_id=shard_id, worker=worker, now=now))
    issue.source_observations = obs
    if refs:
        issue.artifact_refs = list(issue.artifact_refs or []) + refs
    if reopen:
        issue.status = AutoIssue.STATUS_OPEN
    issue.save(update_fields=["occurrence_count", "source_observations", "artifact_refs", "status"])


class Command(BaseCommand):
    help = "File a failed shard test as an AutoIssue (create / update / reopen)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--tool", required=True)
        parser.add_argument("--test-target", required=True)
        parser.add_argument("--test-file", required=True)
        parser.add_argument("--test-name", required=True)
        parser.add_argument("--failure-summary", required=True)
        parser.add_argument("--severity", required=True, choices=list(_VALID_SEVERITIES))
        parser.add_argument("--run-id", required=True)
        parser.add_argument("--shard-id", required=True)
        parser.add_argument("--worker", default="windows")
        parser.add_argument(
            "--artifact-ref",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="Add an artifact reference (e.g. sha256=abc... blob_path=/srv/xf/...). Repeatable.",
        )

    def handle(self, *args, **options) -> None:
        refs = [dict(pair.split("=", 1) for pair in entry.split(" ") if "=" in pair)
                for entry in options["artifact_ref"]]
        issue, action = file_test_failure(
            tool=options["tool"],
            test_target=options["test_target"],
            test_file=options["test_file"],
            test_name=options["test_name"],
            failure_summary=options["failure_summary"],
            severity=options["severity"],
            run_id=options["run_id"],
            shard_id=options["shard_id"],
            artifact_refs=refs,
            worker=options["worker"],
        )
        self.stdout.write(f"[TEST FAILURE AUTOISSUE: #{issue.pk} action={action} external_id={issue.external_id}]")
