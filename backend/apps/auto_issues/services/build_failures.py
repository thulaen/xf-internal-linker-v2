"""Import compiler/build failures into deduped AutoIssues."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

import lz4.frame
from django.db.models import F

from apps.auto_issues.models import AutoIssue, BuildFailureEvidence
from apps.auto_issues.services.dedup import upsert_dedup

BUILD_COMPILE_TAG = "build_compile"
BUILD_COMPILE_CATEGORY = "build_compile_failure"
_ERROR_LINE_RE = re.compile(r"(error|fatal|failed|undefined|cannot find)", re.IGNORECASE)
_PATH_RE = re.compile(r"((?:backend|frontend|services|scripts|config|docs)/[^\s:]+)")


@dataclass(frozen=True)
class BuildFailure:
    """One failed build command after host-side output is normalized."""

    builder: str
    targets: list[str]
    command: list[str]
    exit_code: int
    stdout: str = ""
    stderr: str = ""


def ingest_build_failure(failure: BuildFailure) -> tuple[AutoIssue, str]:
    """Create or update one AutoIssue for a stable compiler failure."""
    fingerprint = _fingerprint(failure)
    issue, outcome = upsert_dedup(
        canonical=fingerprint,
        source=AutoIssue.SOURCE_AGENT,
        external_id=f"build_compile::{fingerprint}",
        fingerprint=fingerprint,
        title=_title(failure),
        description=_description(failure, fingerprint),
        affected_files=_affected_files(failure),
        severity=AutoIssue.SEVERITY_HIGH,
        priority_score=0.85,
        occurrence_count=1,
        category_key=BUILD_COMPILE_CATEGORY,
    )
    _ensure_metadata(issue)
    _ensure_evidence(issue, failure, fingerprint)
    return issue, outcome


def failure_from_payload(payload: dict[str, Any]) -> BuildFailure:
    """Validate loose JSON from the host build script into a typed object."""
    return BuildFailure(
        builder=str(payload.get("builder") or "unknown"),
        targets=[str(item) for item in payload.get("targets") or ["<all>"]],
        command=[str(item) for item in payload.get("command") or []],
        exit_code=int(payload.get("exit_code") or 1),
        stdout=str(payload.get("stdout") or ""),
        stderr=str(payload.get("stderr") or ""),
    )


def _fingerprint(failure: BuildFailure) -> str:
    parts = [
        "build-compile-v1",
        ",".join(sorted(failure.targets)),
        str(failure.exit_code),
        _signature_line(failure),
    ]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]


def _signature_line(failure: BuildFailure) -> str:
    for line in _combined_output(failure).splitlines():
        stripped = line.strip()
        if stripped and _ERROR_LINE_RE.search(stripped):
            return _normalize_line(stripped)
    return _normalize_line((_combined_output(failure).splitlines() or ["unknown failure"])[-1])


def _normalize_line(line: str) -> str:
    return re.sub(r"\b\d+:\d+\b|\bline \d+\b", "<line>", line.lower())[:500]


def _title(failure: BuildFailure) -> str:
    target = ", ".join(failure.targets or ["<all>"])
    return f"Compilation failed on {target} via {failure.builder}"


def _description(failure: BuildFailure, fingerprint: str) -> str:
    return "\n".join([
        "Compilation failure from smart build routing.",
        "Full terminal evidence is stored in the linked LZ4-compressed build evidence row.",
        f"Builder: {failure.builder}",
        f"Targets: {', '.join(failure.targets)}",
        f"Exit code: {failure.exit_code}",
        f"Fingerprint: {fingerprint}",
        "When resolving this AutoIssue, lessons_learned must include Trap: and Fix shape: notes.",
    ])


def _affected_files(failure: BuildFailure) -> list[str]:
    match = _PATH_RE.search(_combined_output(failure).replace("\\", "/"))
    return [match.group(1)] if match else []


def _combined_output(failure: BuildFailure) -> str:
    return f"{failure.stdout}\n{failure.stderr}".strip()


def _payload(failure: BuildFailure, fingerprint: str) -> dict[str, Any]:
    return {
        "alert_type": "compilation_failure",
        "builder": failure.builder,
        "targets": failure.targets,
        "command": failure.command,
        "exit_code": failure.exit_code,
        "stdout": failure.stdout,
        "stderr": failure.stderr,
        "evidence": _signature_line(failure),
        "severity": AutoIssue.SEVERITY_HIGH,
        "reproduction_command": " ".join(failure.command),
        "recommended_fix": "Fix the compiler error, rerun the same smart build command, then resolve this AutoIssue with Trap: and Fix shape: lessons.",
        "true_positive_status": "needs review",
        "fingerprint": fingerprint,
    }


def _compress_payload(failure: BuildFailure, fingerprint: str) -> tuple[bytes, int, int]:
    raw = json.dumps(_payload(failure, fingerprint), sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = lz4.frame.compress(raw)
    return compressed, len(raw), len(compressed)


def _ensure_metadata(issue: AutoIssue) -> None:
    tags = sorted({*(issue.concept_tags or []), BUILD_COMPILE_TAG})
    refs = [ref for ref in (issue.artifact_refs or []) if ref.get("type") != "build_failure_lz4_evidence"]
    refs.append({"type": "build_failure_lz4_evidence", "compression": "lz4"})
    if tags != issue.concept_tags or refs != issue.artifact_refs:
        issue.concept_tags = tags
        issue.artifact_refs = refs
        issue.save(update_fields=["concept_tags", "artifact_refs"])


def _ensure_evidence(issue: AutoIssue, failure: BuildFailure, fingerprint: str) -> None:
    compressed, uncompressed_bytes, compressed_bytes = _compress_payload(failure, fingerprint)
    evidence, created = BuildFailureEvidence.objects.update_or_create(
        failure_fingerprint=fingerprint,
        defaults={
            "issue": issue,
            "builder": failure.builder,
            "targets": failure.targets,
            "command": failure.command,
            "exit_code": failure.exit_code,
            "compression": "lz4",
            "compressed_payload": compressed,
            "uncompressed_bytes": uncompressed_bytes,
            "compressed_bytes": compressed_bytes,
        },
    )
    if not created:
        BuildFailureEvidence.objects.filter(pk=evidence.pk).update(
            occurrence_count=F("occurrence_count") + 1
        )
