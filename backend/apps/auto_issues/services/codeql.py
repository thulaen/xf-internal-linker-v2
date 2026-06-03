"""Import CodeQL SARIF findings into deduped AutoIssues."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lz4.frame

from apps.auto_issues.models import AutoIssue, CodeQLFindingEvidence
from apps.auto_issues.services.dedup import upsert_dedup

CODEQL_TAG = "codeql"
CODEQL_CATEGORY = "codeql_security"
DEFAULT_REPRO_COMMAND = "python scripts/run_codeql.py --language {language}"
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass(frozen=True)
class CodeQLIngestResult:
    """Small summary for a CodeQL SARIF import."""

    created: int
    updated: int
    skipped: int
    total: int


@dataclass(frozen=True)
class CodeQLFinding:
    """One CodeQL finding after SARIF fields are normalized."""

    language: str
    rule_id: str
    file_path: str
    line: int
    message: str
    severity: str
    recommendation: str


def _load_sarif(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _rule_map(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rules = run.get("tool", {}).get("driver", {}).get("rules", [])
    return {str(rule.get("id", "")): rule for rule in rules if rule.get("id")}


def _security_severity(rule: dict[str, Any]) -> float:
    raw = rule.get("properties", {}).get("security-severity", 0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _project_severity(result: dict[str, Any], rule: dict[str, Any]) -> str:
    score = _security_severity(rule)
    if score >= 8:
        return AutoIssue.SEVERITY_CRITICAL
    if score >= 6:
        return AutoIssue.SEVERITY_HIGH
    level = str(result.get("level") or "warning").lower()
    return {"error": "high", "warning": "medium", "note": "low"}.get(level, "medium")


def _recommendation(rule: dict[str, Any]) -> str:
    return (
        rule.get("help", {}).get("text")
        or rule.get("fullDescription", {}).get("text")
        or rule.get("shortDescription", {}).get("text")
        or "Review the CodeQL rule help and apply the safer pattern it recommends."
    )


def _finding_from_result(language: str, result: dict[str, Any], rules: dict[str, dict[str, Any]]) -> CodeQLFinding | None:
    locations = result.get("locations") or []
    if not locations:
        return None
    physical = locations[0].get("physicalLocation", {})
    file_path = physical.get("artifactLocation", {}).get("uri", "")
    if not file_path:
        return None
    rule_id = str(result.get("ruleId") or "unknown")
    rule = rules.get(rule_id, {})
    line = int(physical.get("region", {}).get("startLine") or 1)
    message = result.get("message", {}).get("text", "").strip()
    return CodeQLFinding(
        language=language,
        rule_id=rule_id,
        file_path=file_path,
        line=line,
        message=message,
        severity=_project_severity(result, rule),
        recommendation=_recommendation(rule),
    )


def _iter_findings(sarif: dict[str, Any], language: str) -> list[CodeQLFinding]:
    findings: list[CodeQLFinding] = []
    for run in sarif.get("runs", []):
        rules = _rule_map(run)
        for result in run.get("results", []):
            finding = _finding_from_result(language, result, rules)
            if finding is not None:
                findings.append(finding)
    return findings


def _fingerprint(finding: CodeQLFinding) -> str:
    raw = "|".join([
        finding.language,
        finding.rule_id,
        finding.file_path,
        str(finding.line),
        finding.message,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _description(finding: CodeQLFinding) -> str:
    return "\n".join([
        "CodeQL finding.",
        "Detailed evidence is stored in the linked LZ4-compressed CodeQL evidence row.",
        f"Fingerprint: {_fingerprint(finding)}",
    ])


def _payload(finding: CodeQLFinding) -> dict[str, Any]:
    return {
        "alert_type": finding.rule_id,
        "affected_file": f"{finding.file_path}:{finding.line}",
        "evidence": finding.message or "CodeQL reported this location.",
        "severity": finding.severity,
        "reproduction_command": DEFAULT_REPRO_COMMAND.format(language=finding.language),
        "recommended_fix": finding.recommendation,
        "true_positive_status": "needs review",
    }


def _compress_payload(finding: CodeQLFinding) -> tuple[bytes, int, int]:
    raw = json.dumps(_payload(finding), sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = lz4.frame.compress(raw)
    return compressed, len(raw), len(compressed)


def _priority(severity: str) -> float:
    return {AutoIssue.SEVERITY_CRITICAL: 0.95, AutoIssue.SEVERITY_HIGH: 0.8, AutoIssue.SEVERITY_MEDIUM: 0.55}.get(severity, 0.3)


def _upsert_finding(finding: CodeQLFinding) -> str:
    fingerprint = _fingerprint(finding)
    issue, outcome = upsert_dedup(
        canonical=fingerprint,
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"codeql::{finding.language}::{fingerprint}",
        fingerprint=fingerprint,
        title=f"CodeQL {finding.rule_id}: {finding.file_path}:{finding.line}",
        description=_description(finding),
        affected_files=[finding.file_path],
        severity=finding.severity,
        priority_score=_priority(finding.severity),
        occurrence_count=1,
        category_key=CODEQL_CATEGORY,
    )
    _ensure_codeql_metadata(issue)
    _ensure_codeql_evidence(issue, finding)
    return outcome


def _finding_exists(finding: CodeQLFinding) -> bool:
    fingerprint = _fingerprint(finding)
    return (
        CodeQLFindingEvidence.objects.filter(finding_fingerprint=fingerprint).exists()
        or AutoIssue.objects.filter(
            canonical_fingerprint=fingerprint,
            concept_tags__contains=[CODEQL_TAG],
        ).exists()
    )


def _ensure_codeql_metadata(issue: AutoIssue) -> None:
    tags = sorted({*(issue.concept_tags or []), CODEQL_TAG})
    refs = [
        ref for ref in (issue.artifact_refs or [])
        if ref.get("type") != "codeql_lz4_evidence"
    ]
    refs.append({"type": "codeql_lz4_evidence", "compression": "lz4"})
    if tags != issue.concept_tags or refs != issue.artifact_refs:
        issue.concept_tags = tags
        issue.artifact_refs = refs
        issue.save(update_fields=["concept_tags", "artifact_refs"])


def _ensure_codeql_evidence(issue: AutoIssue, finding: CodeQLFinding) -> None:
    compressed, uncompressed_bytes, compressed_bytes = _compress_payload(finding)
    CodeQLFindingEvidence.objects.update_or_create(
        finding_fingerprint=_fingerprint(finding),
        defaults={
            "issue": issue,
            "language": finding.language,
            "rule_id": finding.rule_id,
            "file_path": finding.file_path,
            "line": finding.line,
            "compression": "lz4",
            "compressed_payload": compressed,
            "uncompressed_bytes": uncompressed_bytes,
            "compressed_bytes": compressed_bytes,
        },
    )


def ingest_sarif_paths(paths: list[Path], *, language: str, max_open: int = 10) -> CodeQLIngestResult:
    """Import CodeQL findings without exceeding the open issue quota."""
    created = 0
    updated = 0
    skipped = 0
    open_count = open_codeql_issues().count()
    for path in paths:
        for finding in _iter_findings(_load_sarif(path), language):
            is_existing = _finding_exists(finding)
            if not is_existing and open_count >= max_open:
                skipped += 1
                continue
            outcome = _upsert_finding(finding)
            if outcome == "created":
                created += 1
                open_count += 1
            else:
                updated += 1
    return CodeQLIngestResult(created=created, updated=updated, skipped=skipped, total=created + updated)


def open_codeql_issues():
    """Return unresolved CodeQL-backed AutoIssues."""
    return AutoIssue.objects.filter(concept_tags__contains=[CODEQL_TAG]).exclude(
        status=AutoIssue.STATUS_RESOLVED
    )


def verify_codeql_autoissues(*, max_open: int, block_open: bool) -> list[AutoIssue]:
    """Return open CodeQL issues or raise when the commit must stop."""
    open_issues = list(open_codeql_issues().order_by("first_seen", "id"))
    if len(open_issues) > max_open:
        raise ValueError(_quota_message(open_issues, max_open))
    if block_open and open_issues:
        raise ValueError(_block_message(open_issues))
    return open_issues


def _ids(issues: list[AutoIssue], limit: int = 10) -> str:
    return ", ".join(f"#{issue.pk}" for issue in issues[:limit])


def _quota_message(issues: list[AutoIssue], max_open: int) -> str:
    return f"CodeQL has {len(issues)} open AutoIssues, above the maximum {max_open}: {_ids(issues)}"


def _block_message(issues: list[AutoIssue]) -> str:
    return f"Unresolved CodeQL AutoIssues must be fixed or reviewed before commit: {_ids(issues)}"
