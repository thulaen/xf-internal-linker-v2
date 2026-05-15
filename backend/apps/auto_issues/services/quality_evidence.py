"""Store compact quality-check evidence and link failures to AutoIssues."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from django.db.models import F
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, QualityEvidence, QualityRawSnippet
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

SUMMARY_DEFAULT_MIN_WORDS = 200
SUMMARY_DEFAULT_MAX_WORDS = 400
SUMMARY_HARD_MAX_WORDS = 600
RAW_REPORT_MAX_BYTES = 256_000
PASSED_RETENTION_DAYS = 30
FAILED_RETENTION_DAYS = 180
HASH_VERSION = "quality-evidence-v1"
RAW_SNIPPET_KEEP_WEEKS = 12
RAW_SNIPPET_WINDOW_START_HOUR = 11
RAW_SNIPPET_WINDOW_END_HOUR = 23

_WORD_RE = re.compile(r"\b[\w'-]+\b")


@dataclass(frozen=True, slots=True)
class QualityEvidenceInput:
    """Validated input for one compact quality-check result."""

    check_type: str
    status: str
    tool_name: str
    command: str
    summary: str
    tool_version: str = ""
    source_hash: str = ""
    file_path: str = ""
    failure_fingerprint: str = ""
    target_percent: float | None = None
    actual_percent: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    raw_report_text: str = ""
    capture_raw_snippet: bool = False


def record_quality_evidence(payload: QualityEvidenceInput) -> QualityEvidence:
    """Create or update a deduped evidence row and AutoIssue for failures."""
    _validate_payload(payload)
    dedupe_key = build_dedupe_key(payload)
    raw_hash, raw_snippet = _maybe_store_raw_snippet(payload)
    evidence, created = QualityEvidence.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults=_new_evidence_defaults(payload, raw_hash, raw_snippet),
    )
    if not created:
        _update_existing_evidence(evidence, payload, raw_hash, raw_snippet)
    if payload.status == QualityEvidence.STATUS_FAILED:
        evidence.auto_issue = _upsert_quality_autoissue(payload, dedupe_key)
        evidence.save(update_fields=["auto_issue"])
    return evidence


def build_dedupe_key(payload: QualityEvidenceInput) -> str:
    """Return the stable identity for a quality result."""
    parts = [
        HASH_VERSION,
        payload.check_type,
        payload.command,
        payload.tool_name,
        payload.tool_version,
        payload.source_hash,
        payload.file_path,
        payload.failure_fingerprint,
    ]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def prune_expired_quality_evidence(*, now=None) -> int:
    """Delete compact rows past retention; AutoIssue rows keep the lesson."""
    cutoff = now or timezone.now()
    expired = QualityEvidence.objects.filter(expires_at__lt=cutoff)
    deleted_count, _ = expired.delete()
    return int(deleted_count)


def should_capture_weekly_raw_snippet(*, now=None) -> bool:
    """Return True when one weekly raw-snippet capture is due."""
    local_now = timezone.localtime(now or timezone.now())
    current_week = _week_start(local_now.date())
    previous_week = current_week - timedelta(days=7)
    latest = (
        QualityRawSnippet.objects.order_by("-last_captured_week_start")
        .values_list("last_captured_week_start", flat=True)
        .first()
    )
    if latest == current_week:
        return False
    if latest is None:
        return _inside_capture_window(local_now) or local_now.hour >= RAW_SNIPPET_WINDOW_END_HOUR
    if _inside_capture_window(local_now):
        return True
    return latest < previous_week


def prune_old_raw_snippets(*, now=None, keep_weeks: int = RAW_SNIPPET_KEEP_WEEKS) -> int:
    """Delete old weekly raw snippets that no active evidence still needs."""
    cutoff = now or timezone.now()
    weeks = list(
        QualityRawSnippet.objects.order_by("-last_captured_week_start")
        .values_list("last_captured_week_start", flat=True)
        .distinct()
    )
    stale_weeks = weeks[keep_weeks:]
    if not stale_weeks:
        return 0
    active_ids = QualityEvidence.objects.filter(
        raw_snippet__isnull=False,
        expires_at__gte=cutoff,
    ).values_list("raw_snippet_id", flat=True)
    stale = QualityRawSnippet.objects.filter(
        last_captured_week_start__in=stale_weeks,
    ).exclude(id__in=active_ids)
    deleted_count, _ = stale.delete()
    return int(deleted_count)


def summary_word_count(summary: str) -> int:
    """Count words for the 600-word hard limit."""
    return len(_WORD_RE.findall(summary or ""))


def _validate_payload(payload: QualityEvidenceInput) -> None:
    valid_types = {choice[0] for choice in QualityEvidence.CHECK_CHOICES}
    valid_statuses = {choice[0] for choice in QualityEvidence.STATUS_CHOICES}
    if payload.check_type not in valid_types:
        raise ValueError(f"Unknown check_type: {payload.check_type}")
    if payload.status not in valid_statuses:
        raise ValueError(f"Unknown status: {payload.status}")
    if not payload.tool_name.strip():
        raise ValueError("tool_name is required")
    if not payload.command.strip():
        raise ValueError("command is required")
    if summary_word_count(payload.summary) > SUMMARY_HARD_MAX_WORDS:
        raise ValueError("summary exceeds the 600-word hard max")


def _new_evidence_defaults(
    payload: QualityEvidenceInput,
    raw_hash: str,
    raw_snippet: QualityRawSnippet | None,
) -> dict[str, Any]:
    return {
        "check_type": payload.check_type,
        "status": payload.status,
        "tool_name": payload.tool_name,
        "tool_version": payload.tool_version,
        "command": payload.command,
        "source_hash": payload.source_hash,
        "file_path": payload.file_path,
        "failure_fingerprint": payload.failure_fingerprint,
        "target_percent": payload.target_percent,
        "actual_percent": payload.actual_percent,
        "summary": payload.summary,
        "details": payload.details,
        "raw_report_hash": raw_hash,
        "raw_snippet": raw_snippet,
        "expires_at": _expiry_for(payload.status),
    }


def _update_existing_evidence(
    evidence: QualityEvidence,
    payload: QualityEvidenceInput,
    raw_hash: str,
    raw_snippet: QualityRawSnippet | None,
) -> None:
    evidence.status = payload.status
    evidence.target_percent = payload.target_percent
    evidence.actual_percent = payload.actual_percent
    evidence.summary = payload.summary
    evidence.details = payload.details
    evidence.raw_report_hash = raw_hash
    if raw_snippet is not None:
        evidence.raw_snippet = raw_snippet
    evidence.expires_at = _expiry_for(payload.status)
    evidence.occurrence_count += 1
    evidence.last_seen = timezone.now()
    update_fields = [
        "status",
        "target_percent",
        "actual_percent",
        "summary",
        "details",
        "raw_report_hash",
        "expires_at",
        "occurrence_count",
        "last_seen",
    ]
    if raw_snippet is not None:
        update_fields.append("raw_snippet")
    evidence.save(update_fields=update_fields)


def _upsert_quality_autoissue(payload: QualityEvidenceInput, dedupe_key: str) -> AutoIssue:
    title = _issue_title(payload)
    culprit = payload.file_path or payload.failure_fingerprint or payload.tool_name
    canonical = canonical_fingerprint(title, culprit)
    issue, _ = upsert_dedup(
        canonical=canonical,
        source=_source_for(payload.check_type),
        external_id=f"quality:{dedupe_key[:32]}",
        fingerprint=canonical,
        title=title,
        description=_issue_description(payload),
        affected_files=[payload.file_path] if payload.file_path else [],
        severity=_severity_for(payload.check_type),
        priority_score=_priority_for(payload.check_type),
        occurrence_count=1,
        category_key=_category_for(payload.check_type),
    )
    return issue


def _issue_title(payload: QualityEvidenceInput) -> str:
    subject = payload.file_path or payload.failure_fingerprint or payload.tool_name
    return f"[quality-{payload.check_type}] {payload.tool_name} failed: {subject}"[:512]


def _issue_description(payload: QualityEvidenceInput) -> str:
    detail = {
        "target_percent": payload.target_percent,
        "actual_percent": payload.actual_percent,
        "command": payload.command,
        "details": payload.details,
    }
    return (
        f"{payload.summary.strip()}\n\n"
        f"Evidence:\n{json.dumps(detail, sort_keys=True, default=str)[:2400]}"
    )


def _maybe_store_raw_snippet(
    payload: QualityEvidenceInput,
) -> tuple[str, QualityRawSnippet | None]:
    if not payload.raw_report_text:
        return "", None
    raw_hash, raw_gzip, uncompressed_size = _pack_raw_report(payload.raw_report_text)
    existing = QualityRawSnippet.objects.filter(raw_report_hash=raw_hash).first()
    if existing is not None:
        QualityRawSnippet.objects.filter(pk=existing.pk).update(
            reference_count=F("reference_count") + 1,
            last_captured_week_start=_week_start(timezone.localdate()),
            last_seen=timezone.now(),
        )
        existing.refresh_from_db()
        return raw_hash, existing
    if payload.status != QualityEvidence.STATUS_FAILED and not payload.capture_raw_snippet:
        return raw_hash, None
    week_start = _week_start(timezone.localdate())
    snippet, _created = QualityRawSnippet.objects.get_or_create(
        raw_report_hash=raw_hash,
        defaults={
            "raw_report_gzip": raw_gzip,
            "uncompressed_bytes": uncompressed_size,
            "compressed_bytes": len(raw_gzip),
            "first_captured_week_start": week_start,
            "last_captured_week_start": week_start,
        },
    )
    return raw_hash, snippet


def _pack_raw_report(raw_text: str) -> tuple[str, bytes, int]:
    encoded = raw_text.encode("utf-8")[:RAW_REPORT_MAX_BYTES]
    raw_hash = hashlib.sha256(encoded).hexdigest()
    return raw_hash, gzip.compress(encoded), len(encoded)


def _inside_capture_window(local_now) -> bool:
    return RAW_SNIPPET_WINDOW_START_HOUR <= local_now.hour < RAW_SNIPPET_WINDOW_END_HOUR


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _expiry_for(status: str):
    days = FAILED_RETENTION_DAYS if status == QualityEvidence.STATUS_FAILED else PASSED_RETENTION_DAYS
    return timezone.now() + timedelta(days=days)


def _source_for(check_type: str) -> str:
    if check_type == QualityEvidence.CHECK_MUTATION:
        return AutoIssue.SOURCE_MUTATION
    if check_type == QualityEvidence.CHECK_FUZZ:
        return AutoIssue.SOURCE_FUZZ
    if check_type == QualityEvidence.CHECK_CI:
        return AutoIssue.SOURCE_GH_CI
    return AutoIssue.SOURCE_AGENT


def _severity_for(check_type: str) -> str:
    if check_type in {QualityEvidence.CHECK_SECURITY, QualityEvidence.CHECK_CI}:
        return AutoIssue.SEVERITY_HIGH
    if check_type in {QualityEvidence.CHECK_MUTATION, QualityEvidence.CHECK_SANITIZER}:
        return AutoIssue.SEVERITY_MEDIUM
    return AutoIssue.SEVERITY_LOW


def _priority_for(check_type: str) -> float:
    if check_type in {QualityEvidence.CHECK_SECURITY, QualityEvidence.CHECK_CI}:
        return 0.85
    if check_type in {QualityEvidence.CHECK_MUTATION, QualityEvidence.CHECK_SANITIZER}:
        return 0.65
    return 0.35


def _category_for(check_type: str) -> str:
    if check_type == QualityEvidence.CHECK_SECURITY:
        return "security"
    if check_type == QualityEvidence.CHECK_TOOL_READINESS:
        return "tooling"
    if check_type == QualityEvidence.CHECK_STATIC_ANALYSIS:
        return "maintainability"
    if check_type in {QualityEvidence.CHECK_COVERAGE, QualityEvidence.CHECK_MUTATION}:
        return "correctness"
    if check_type in {QualityEvidence.CHECK_FUZZ, QualityEvidence.CHECK_SANITIZER}:
        return "correctness"
    if check_type == QualityEvidence.CHECK_CI:
        return "correctness"
    return "tech-debt"
