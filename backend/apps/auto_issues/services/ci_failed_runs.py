"""GitHub Actions failed-runs picker — Phase 6 of the test-hardening plan.

Shells `gh run list --status failure --limit N` (N defaults to 10 via the
`gh_ci.fetch_limit` AppSetting), parses the JSON, and upserts each run
as an AutoIssue with source='gh_ci'. The opening-ritual line
`[CI FAILED RUNS READ: N latest — picked: #...]` enforced by
`.githooks/check-registry-read.py` is the freshness check; this picker
makes the runs visible in the standard 18-pick queue so the
auto-fix-18 quota can include them.

Graceful fallback when `gh` isn't installed: returns 0 (no rows
created) without raising. The opening-ritual marker handles the
"gh unavailable" case separately.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from opentelemetry import trace

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


def _appsetting(key: str, default: str) -> str:
    """Read an AppSetting value, falling back to *default* on any error."""
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
        if row and row.value:
            return str(row.value)
    except Exception:  # noqa: BLE001 — defensive at startup time
        pass
    return default


def pick_ci_failed_runs() -> int:
    """Fetch the latest failed CI runs and upsert each as an AutoIssue.

    Returns the count of rows that landed (created OR merged).
    """
    limit = int(_appsetting("gh_ci.fetch_limit", "10"))
    severity = _appsetting("gh_ci.severity", AutoIssue.SEVERITY_HIGH)

    runs = _fetch_gh_runs(limit)
    if not runs:
        return 0

    count = 0
    for run in runs:
        if _upsert_run(run, severity):
            count += 1
    return count


def _fetch_gh_runs(limit: int) -> list[dict[str, Any]]:
    """Shell `gh run list --status failure --limit N --json ...`.

    Empty list on any failure path — the picker is best-effort.
    """
    try:
        result = subprocess.run(
            [
                "gh", "run", "list",
                "--status", "failure",
                "--limit", str(limit),
                "--json", "databaseId,name,headBranch,conclusion,url,workflowName,createdAt",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.info("ci_failed_runs: gh CLI unavailable; skipping")
        return []

    if result.returncode != 0:
        logger.info("ci_failed_runs: gh returned non-zero; skipping")
        return []

    try:
        return json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        logger.warning("ci_failed_runs: gh stdout unparseable as JSON")
        return []


def _upsert_run(run: dict[str, Any], severity: str) -> bool:
    """Convert one failed-run record into an AutoIssue row.

    Returns True if an issue was created or merged; False on error.
    """
    db_id = str(run.get("databaseId", ""))
    if not db_id:
        return False

    name = run.get("name", "?")
    workflow = run.get("workflowName", "?")
    branch = run.get("headBranch", "?")
    url = run.get("url", "")

    title = f"[gh-ci-fail] {workflow}/{name} on {branch}"
    culprit = f"workflow:{workflow}|job:{name}"
    fp = canonical_fingerprint(title, culprit)

    with _tracer.start_as_current_span(
        "auto_issue.created",
        attributes={
            "source": AutoIssue.SOURCE_GH_CI,
            "kind": "ci-failure",
            "fingerprint": fp,
            "severity": severity,
            "tool": "gh",
        },
    ):
        try:
            issue, action = upsert_dedup(
                canonical=fp,
                source=AutoIssue.SOURCE_GH_CI,
                external_id=db_id,
                fingerprint=fp,
                title=title,
                description=f"Failed CI run: {url}",
                affected_files=[],
                severity=severity,
                priority_score=0.7,
                occurrence_count=1,
            )
        except Exception:  # noqa: BLE001 — defensive at picker time
            logger.exception("ci_failed_runs: upsert failed for run %s", db_id)
            return False

    logger.info("ci_failed_runs: %s issue #%s for run %s", action, issue.id, db_id)
    return True
