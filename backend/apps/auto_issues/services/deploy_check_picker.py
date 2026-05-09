"""Django deploy-check → AutoIssue picker.

Closes Gap #9 from `docs/OBSERVABILITY-GAPS-EXTENSION.md`. Catches
runtime security misconfigurations (e.g. `DEBUG=True` in production,
`ALLOWED_HOSTS=*`, missing `SECURE_HSTS_SECONDS`, CSRF cookie not
Secure). Django's `manage.py check --deploy` already enumerates these;
the picker captures the output and surfaces each warning as one
AutoIssue row.

Cross-source dedup via `services.dedup.upsert_dedup` — each warning
has a stable Django check-id (e.g. `security.W018`) so re-running the
check weekly updates the existing row instead of duplicating.
"""

from __future__ import annotations

import logging
import re
from io import StringIO

from django.core.management import call_command

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)

# Django check IDs follow `<app>.<level><number>` e.g. `security.W018`,
# `models.E007`. Parsing this lets us derive severity from the level
# letter (W = warning → medium, E = error → high, C = critical).
_CHECK_ID_RE = re.compile(r"^([?]:?)\s*(?P<id>[a-z_0-9]+\.[WEC]\d+):", re.I | re.M)
_LEVEL_TO_SEVERITY = {
    "W": AutoIssue.SEVERITY_MEDIUM,
    "E": AutoIssue.SEVERITY_HIGH,
    "C": AutoIssue.SEVERITY_CRITICAL,
}


def _run_deploy_check() -> str:
    """Capture `manage.py check --deploy` output as a string."""
    buf = StringIO()
    try:
        # check --deploy raises SystemExit when warnings found; suppress.
        call_command("check", deploy=True, stdout=buf, stderr=buf)
    except SystemExit:
        pass
    except Exception as exc:
        logger.warning("[deploy_check_picker] check --deploy failed: %s", exc)
    return buf.getvalue()


def _parse_findings(output: str) -> list[tuple[str, str, str]]:
    """Walk the `check --deploy` output, return [(check_id, level, body)]."""
    findings: list[tuple[str, str, str]] = []
    if not output:
        return findings
    # Split on the standard Django check-format header line. Each finding
    # is a stanza:
    #   ?: (security.W018) You should not have DEBUG set to True ...
    #         HINT: ...
    blocks = re.split(r"(?m)^\?:\s*\(", output)
    for block in blocks[1:]:
        match = re.match(r"([a-z_0-9]+)\.([WEC])(\d+)\)\s*(.*)", block, re.I | re.S)
        if not match:
            continue
        category, level, num, body = match.groups()
        check_id = f"{category}.{level}{num}"
        findings.append((check_id, level.upper(), body.strip()[:1500]))
    return findings


def _upsert_finding(check_id: str, level: str, body: str) -> str:
    """Single upsert through cross-source dedup."""
    severity = _LEVEL_TO_SEVERITY.get(level, AutoIssue.SEVERITY_MEDIUM)
    title = f"Django deploy-check: {check_id} — {body.splitlines()[0][:90]}"
    description = (
        f"`python manage.py check --deploy` reports `{check_id}` "
        f"(level `{level}`).\n\n{body}\n\n"
        f"To verify after fixing, re-run `python manage.py check --deploy` "
        f"in the backend container and confirm `{check_id}` no longer "
        f"appears in the output."
    )
    canonical = canonical_fingerprint(f"django-check::{check_id}", "")
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"django-check-{check_id}",
        fingerprint=f"django-check-{check_id}",
        title=title,
        description=description,
        affected_files=["backend/config/settings/"],
        severity=severity,
        priority_score=0.55 if severity == AutoIssue.SEVERITY_HIGH else 0.3,
        occurrence_count=1,
    )
    return outcome


def pick_deploy_check_findings() -> dict:
    """Run check --deploy, surface every finding into auto_issues."""
    output = _run_deploy_check()
    findings = _parse_findings(output)
    if not findings:
        return {"status": "ok", "findings": 0, "promoted": 0}

    counts = {"created": 0, "merged": 0, "updated": 0}
    for check_id, level, body in findings:
        outcome = _upsert_finding(check_id, level, body)
        counts[outcome] = counts.get(outcome, 0) + 1
    logger.info(
        "[auto_issues.deploy_check_picker] findings=%d created=%d merged=%d updated=%d",
        len(findings), counts["created"], counts["merged"], counts["updated"],
    )
    return {
        "status": "ok",
        "findings": len(findings),
        "promoted": sum(counts.values()),
        **counts,
    }
