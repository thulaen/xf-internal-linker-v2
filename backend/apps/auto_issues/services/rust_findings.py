from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.pipeline.services.rust_kernels import (
    KernelUnavailableError,
    load_kernel,
)


REQUIRED_BUG_FIELDS = frozenset({
    "bug_pattern_id",
    "title",
    "description",
    "severity",
    "category",
    "file",
    "line",
    "evidence",
    "suggested_fix",
    "confidence",
    "citation",
    "fingerprint",
    "priority_score",
})

_CATEGORY_MAP = {
    "performance": "performance",
    "correctness": "correctness",
    "concurrency": "concurrency",
    "resource": "resources",
    "security": "security",
    "runtime_pressure": "runtime-pressure",
    "hardware_recalibration": "hardware-recalibration",
    "coverage_gap": "coverage-gap",
    "mutation_survivor": "mutation-survivor",
}
_NATIVE_SIMILARITY_THRESHOLD = 0.85


@dataclass(frozen=True)
class RustImportResult:
    created: int = 0
    updated: int = 0
    stale_resolved: int = 0


class NativeDedupResolver:
    """Resolve near-duplicate Rust findings through the C++ MinHash index."""

    def __init__(self) -> None:
        native = _load_native_dedup_module()
        self._index = native.DedupIndex()
        self._issues: dict[int, AutoIssue] = {}
        for issue in _iter_existing_rust_issues():
            self.add_issue(issue)

    def add_issue(self, issue: AutoIssue) -> None:
        self._issues[int(issue.id)] = issue
        self._index.add_entry(int(issue.id), _issue_dedup_text(issue))

    def canonical_for(self, row: dict[str, Any]) -> str | None:
        hits = self._index.find_similar(
            _candidate_dedup_text(row),
            _NATIVE_SIMILARITY_THRESHOLD,
        )
        for entry_id, _score in hits:
            issue = self._issues.get(int(entry_id))
            if issue is not None:
                return str(issue.canonical_fingerprint)
        return None


def import_rust_report(path: str | Path) -> RustImportResult:
    payload = _load_report(Path(path))
    candidates = payload.get("bug_candidates", [])
    if not isinstance(candidates, list):
        raise CommandError("Rust report bug_candidates must be a list.")
    _validate_candidates(candidates)
    with transaction.atomic():
        return _upsert_candidates(
            candidates,
            NativeDedupResolver(),
            payload.get("metadata", {}),
        )


def _load_report(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CommandError(f"Unable to read Rust report: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CommandError(f"Rust report is not valid JSON: {exc}") from exc


def _validate_candidates(candidates: list[dict[str, Any]]) -> None:
    for index, row in enumerate(candidates):
        missing = REQUIRED_BUG_FIELDS.difference(row)
        if missing:
            field = sorted(missing)[0]
            raise CommandError(
                f"Rust report bug_candidates[{index}] missing required field '{field}'."
            )


def _upsert_candidates(
    candidates: list[dict[str, Any]],
    resolver: NativeDedupResolver,
    metadata: dict[str, Any] | None = None,
) -> RustImportResult:
    created = 0
    updated = 0
    observability_degraded = _observability_degraded(metadata or {})
    health_filed = False
    seen_external_ids: set[str] = set()
    prepared = [(row, _fingerprint(row)) for row in candidates]
    occurrence_counts = _existing_occurrence_counts(
        _external_id_from_fingerprint(row, fingerprint)
        for row, fingerprint in prepared
    )
    for row, fingerprint in prepared:
        issue, outcome = _upsert_candidate(
            row,
            fingerprint,
            resolver,
            occurrence_counts,
        )
        seen_external_ids.add(str(issue.external_id))
        resolver.add_issue(issue)
        if outcome == "created":
            created += 1
        else:
            updated += 1
            if observability_degraded and not health_filed:
                _file_observability_duplicate_health_issue(metadata or {})
                health_filed = True
    stale_resolved = 0
    if _stale_resolution_enabled(metadata or {}):
        stale_resolved = _resolve_stale_findbugs_rows(seen_external_ids)
    return RustImportResult(
        created=created,
        updated=updated,
        stale_resolved=stale_resolved,
    )


def _upsert_candidate(
    row: dict[str, Any],
    fingerprint: str,
    resolver: NativeDedupResolver,
    occurrence_counts: dict[str, int],
):
    canonical = resolver.canonical_for(row) or fingerprint
    external_id = _external_id_from_fingerprint(row, fingerprint)
    occurrence_count = int(occurrence_counts.get(external_id, 0)) + 1
    occurrence_counts[external_id] = occurrence_count
    issue, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_RUST_DEFECT,
        external_id=external_id,
        fingerprint=fingerprint,
        title=f"[{row['bug_pattern_id']}] {row['title']}",
        description=_description(row),
        affected_files=[str(row["file"])],
        severity=_severity(str(row["severity"])),
        priority_score=float(row["priority_score"]),
        occurrence_count=occurrence_count,
        category_key=_CATEGORY_MAP.get(str(row["category"]), str(row["category"])),
    )
    return issue, outcome


def _external_id_from_fingerprint(row: dict[str, Any], fingerprint: str) -> str:
    return f"rust_defect:{row['bug_pattern_id']}:{fingerprint}"


def _description(row: dict[str, Any]) -> str:
    payload = {
        "message": row["description"],
        "line": row["line"],
        "evidence": str(row["evidence"])[:2000],
        "suggested_fix": row["suggested_fix"],
        "confidence": row["confidence"],
        "citation": row["citation"],
        "bug_pattern_id": row["bug_pattern_id"],
    }
    return json.dumps(payload, sort_keys=True)


def _fingerprint(row: dict[str, Any]) -> str:
    stable = json.dumps(
        {
            "pattern": row["bug_pattern_id"],
            "file": row["file"],
            "line": row["line"],
            "fingerprint": row["fingerprint"],
        },
        sort_keys=True,
    )
    return hashlib.sha1(stable.encode("utf-8"), usedforsecurity=False).hexdigest()


def _candidate_dedup_text(row: dict[str, Any]) -> str:
    parts = [
        row["bug_pattern_id"],
        row["title"],
        row["description"],
        row["evidence"],
        row["suggested_fix"],
        row["file"],
    ]
    return "\n".join(str(part) for part in parts)


def _issue_dedup_text(issue: AutoIssue) -> str:
    try:
        detail = json.loads(issue.description or "{}")
    except json.JSONDecodeError:
        detail = {"message": issue.description}
    parts = [
        issue.title,
        detail.get("message", ""),
        detail.get("evidence", ""),
        detail.get("suggested_fix", ""),
        " ".join(issue.affected_files or []),
    ]
    return "\n".join(str(part) for part in parts)


def _iter_existing_rust_issues():
    return (
        AutoIssue.objects
        .filter(source=AutoIssue.SOURCE_RUST_DEFECT)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .only("id", "title", "description", "affected_files", "canonical_fingerprint")
    )


def _load_native_dedup_module():
    backend_root = Path(__file__).resolve().parents[3]
    backend_path = str(backend_root)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    try:
        return load_kernel("extensions.papertrail_dedup", "DedupIndex")
    except KernelUnavailableError as exc:
        raise CommandError(
            "Rust finding import requires the compiled papertrail_dedup Rust "
            "kernel. Rebuild it via scripts/ensure_compiled_artifacts.py in the "
            "Docker-managed compiled-tools image, then restart the backend."
        ) from exc


def _existing_occurrence_counts(external_ids: Iterable[str]) -> dict[str, int]:
    unique_ids = list(dict.fromkeys(external_ids))
    if not unique_ids:
        return {}
    rows = (
        AutoIssue.objects.filter(
            source=AutoIssue.SOURCE_RUST_DEFECT,
            external_id__in=unique_ids,
        )
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .values_list("external_id", "occurrence_count")
    )
    return {str(external_id): int(count or 0) for external_id, count in rows}


def _severity(value: str) -> str:
    lowered = value.lower()
    if lowered in dict(AutoIssue.SEVERITY_CHOICES):
        return lowered
    return AutoIssue.SEVERITY_MEDIUM


def _stale_resolution_enabled(metadata: dict[str, Any]) -> bool:
    return metadata.get("scanner_version") == "speccheck" and bool(
        metadata.get("source_roots")
    )


def _resolve_stale_findbugs_rows(seen_external_ids: set[str]) -> int:
    stale_rows = (
        AutoIssue.objects.filter(
            source=AutoIssue.SOURCE_RUST_DEFECT,
            external_id__startswith="rust_defect:",
        )
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .exclude(external_id__in=seen_external_ids)
    )
    resolved = 0
    lesson = (
        "Trap: FindBugs findings can become stale after a detector becomes quieter "
        "or the code no longer matches the bug pattern. Fix shape: resolve rows that "
        "are absent from the latest full speccheck report while keeping the lesson "
        "and occurrence history."
    )
    for issue in stale_rows:
        issue.status = AutoIssue.STATUS_RESOLVED
        issue.resolved_at = timezone.now()
        issue.resolved_by = "findbugs"
        issue.lessons_learned = lesson
        issue.save(
            update_fields=[
                "status",
                "resolved_at",
                "resolved_by",
                "lessons_learned",
            ],
        )
        resolved += 1
    return resolved


def _observability_degraded(metadata: dict[str, Any]) -> bool:
    snapshot = metadata.get("observability_snapshot", {})
    return isinstance(snapshot, dict) and snapshot.get("healthy") is False


def _file_observability_duplicate_health_issue(metadata: dict[str, Any]) -> None:
    from apps.auto_issues.services.findbugs import file_findbugs_health_issue

    snapshot = metadata.get("observability_snapshot", {})
    services = snapshot.get("degraded_services", []) if isinstance(snapshot, dict) else []
    file_findbugs_health_issue(
        reason="observability degraded during duplicate import",
        detail=(
            "FindBugs saw a duplicate finding while observability was degraded. "
            f"Degraded services: {', '.join(map(str, services)) or 'unknown'}."
        ),
        severity=AutoIssue.SEVERITY_MEDIUM,
    )
