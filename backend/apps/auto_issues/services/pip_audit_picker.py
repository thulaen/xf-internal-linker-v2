"""Dependency CVE scan → AutoIssue picker.

Closes a gap that GlitchTip + Pyroscope + pg_stat_statements all miss:
known security vulnerabilities in installed Python packages. Runs
`pip-audit --format json` once a week, parses the report, surfaces each
CVE as one AutoIssue row.

Cross-source dedup via `services.dedup.upsert_dedup` — the canonical
fingerprint is `(package_name, vulnerability_id)` so the same CVE
re-scanned a week later updates the existing row instead of duplicating.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import dataclass

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)

_PIP_AUDIT_TIMEOUT_S = 180
_MAX_PER_RUN = 25  # CVEs typically arrive in batches; allow up to 25/week


@dataclass(frozen=True)
class CVEFinding:
    package: str
    installed_version: str
    cve_id: str
    description: str
    fix_versions: tuple[str, ...]


def _run_pip_audit() -> dict | None:
    """Invoke `pip-audit --format json --strict`. Returns parsed JSON or None on error."""
    try:
        proc = subprocess.run(
            ["pip-audit", "--format", "json", "--strict"],
            capture_output=True,
            text=True,
            timeout=_PIP_AUDIT_TIMEOUT_S,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("[pip_audit_picker] cannot run pip-audit: %s", exc)
        return None
    # pip-audit exits 1 when vulns are found — that's NOT an error.
    if proc.returncode not in (0, 1):
        logger.warning("[pip_audit_picker] pip-audit exit %d: %s", proc.returncode, proc.stderr[:300])
        return None
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        logger.warning("[pip_audit_picker] pip-audit output not JSON: %s", exc)
        return None


def _parse_findings(report: dict) -> list[CVEFinding]:
    """Walk pip-audit's `dependencies` array, flatten to CVEFinding rows."""
    out: list[CVEFinding] = []
    for dep in report.get("dependencies", []):
        package = dep.get("name") or ""
        version = dep.get("version") or ""
        for vuln in dep.get("vulns") or []:
            out.append(
                CVEFinding(
                    package=package,
                    installed_version=version,
                    cve_id=vuln.get("id") or "?",
                    description=(vuln.get("description") or "")[:600],
                    fix_versions=tuple(vuln.get("fix_versions") or []),
                )
            )
    return out


def _severity_for(cve: CVEFinding) -> str:
    """No CVSS in pip-audit JSON — use prefix-based heuristic."""
    if cve.cve_id.startswith("GHSA-") or cve.cve_id.startswith("CVE-"):
        return AutoIssue.SEVERITY_HIGH
    return AutoIssue.SEVERITY_MEDIUM


def _stable_external_id(cve: CVEFinding) -> str:
    raw = f"pip-audit::{cve.package}::{cve.cve_id}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _format_title(cve: CVEFinding) -> str:
    fix = cve.fix_versions[0] if cve.fix_versions else "no fix"
    return f"CVE: {cve.package} {cve.installed_version} ({cve.cve_id}, fix: {fix})"


def _upsert_cve(cve: CVEFinding) -> str:
    """Single upsert through cross-source dedup."""
    title = _format_title(cve)
    canonical = canonical_fingerprint(title, cve.package)
    description = (
        f"{cve.description}\n\n"
        f"Installed: {cve.package}=={cve.installed_version}\n"
        f"CVE / advisory id: {cve.cve_id}\n"
        f"Fix versions: {', '.join(cve.fix_versions) or '(none yet)'}"
    )
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_AGENT,
        external_id=_stable_external_id(cve),
        fingerprint=_stable_external_id(cve),
        title=title,
        description=description,
        affected_files=["backend/requirements.txt"],
        severity=_severity_for(cve),
        priority_score=0.6 if cve.fix_versions else 0.4,
        occurrence_count=1,
    )
    return outcome


def pick_pip_audit_findings(*, limit: int = _MAX_PER_RUN) -> dict:
    """Run pip-audit, surface up to `limit` CVEs into auto_issues."""
    report = _run_pip_audit()
    if report is None:
        return {"status": "error", "reason": "pip_audit_unavailable"}
    findings = _parse_findings(report)
    if not findings:
        return {"status": "ok", "findings": 0, "promoted": 0}

    counts = {"created": 0, "merged": 0, "updated": 0}
    for cve in findings[:limit]:
        outcome = _upsert_cve(cve)
        counts[outcome] = counts.get(outcome, 0) + 1

    logger.info(
        "[auto_issues.pip_audit_picker] findings=%d created=%d merged=%d updated=%d",
        len(findings), counts["created"], counts["merged"], counts["updated"],
    )
    return {
        "status": "ok",
        "findings": len(findings),
        "promoted": sum(counts.values()),
        **counts,
    }
