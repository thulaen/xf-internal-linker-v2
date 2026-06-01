"""Fetch postgres-exporter metrics and file/resolve AutoIssues.

Mirrors vmalert_picker.py: fetch an endpoint, turn breaches into deduped
AutoIssue rows under SOURCE_PROMETHEUS, and resolve rows whose breach has
cleared. Pure parsing + thresholds live in pgexporter_metrics.py.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.pgexporter_metrics import (
    Finding,
    evaluate_rules,
    parse_prometheus_text,
)

logger = logging.getLogger(__name__)

_DEFAULT_URL = "http://postgres-exporter:9187/metrics"
_PRIORITY = {
    AutoIssue.SEVERITY_CRITICAL: 0.95,
    AutoIssue.SEVERITY_HIGH: 0.8,
    AutoIssue.SEVERITY_MEDIUM: 0.55,
    AutoIssue.SEVERITY_LOW: 0.3,
}


def pick_pgexporter_findings(metrics_url: str | None = None, *, dry_run: bool = False) -> dict:
    """Scrape postgres-exporter, file breaches, resolve recovered ones.

    With ``dry_run=True`` nothing is written: the result reports how many
    findings WOULD be filed via ``would_file``.
    """
    text = _safe_fetch(metrics_url)
    if text is None:
        return {"filed": 0, "resolved": 0, "open": _open_count(), "would_file": 0}
    findings = evaluate_rules(parse_prometheus_text(text))
    if dry_run:
        return {"filed": 0, "resolved": 0, "open": _open_count(), "would_file": len(findings)}
    filed = sum(1 for finding in findings if _file_finding(finding))
    resolved = _resolve_recovered({f.fingerprint for f in findings})
    return {"filed": filed, "resolved": resolved, "open": _open_count(), "would_file": len(findings)}


def _safe_fetch(metrics_url: str | None) -> str | None:
    url = metrics_url or getattr(settings, "PGEXPORTER_METRICS_URL", _DEFAULT_URL)
    try:
        return _fetch_metrics_text(url)
    except (OSError, urllib.error.URLError) as exc:
        logger.info("pgexporter_picker: unable to read metrics: %s", exc)
        return None


def _fetch_metrics_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=10) as response:  # nosec B310
        return response.read().decode("utf-8")


def _file_finding(finding: Finding) -> bool:
    upsert_dedup(
        canonical=finding.fingerprint,
        source=AutoIssue.SOURCE_PROMETHEUS,
        external_id=finding.fingerprint,
        fingerprint=finding.fingerprint,
        title=f"[pgexporter] {finding.title}",
        description=finding.description,
        affected_files=list(finding.affected),
        severity=finding.severity,
        priority_score=_PRIORITY.get(finding.severity, 0.55),
        occurrence_count=_next_occurrence_count(finding.fingerprint),
    )
    return True


def _next_occurrence_count(fingerprint: str) -> int:
    existing = (
        AutoIssue.objects
        .filter(source=AutoIssue.SOURCE_PROMETHEUS, external_id=fingerprint)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .first()
    )
    return int(existing.occurrence_count or 0) + 1 if existing else 1


def _resolve_recovered(active_fingerprints: set[str]) -> int:
    stale = (
        AutoIssue.objects
        .filter(source=AutoIssue.SOURCE_PROMETHEUS)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .exclude(external_id__in=active_fingerprints)
    )
    resolved = 0
    for issue in stale:
        issue.status = AutoIssue.STATUS_RESOLVED
        issue.resolved_at = timezone.now()
        issue.resolved_by = "pgexporter"
        issue.lessons_learned = (
            "Trap: a postgres-exporter health breach can clear on its own "
            "before anyone investigates, leaving a stale open AutoIssue. "
            "Fix shape: the picker auto-resolves a finding once its metric no "
            "longer breaches, so the row reflects live database health."
        )
        issue.save(update_fields=["status", "resolved_at", "resolved_by", "lessons_learned"])
        resolved += 1
    return resolved


def _open_count() -> int:
    return (
        AutoIssue.objects
        .filter(source=AutoIssue.SOURCE_PROMETHEUS)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .count()
    )


def format_findings_result(result: dict, *, dry_run: bool) -> str:
    """Render a pick result as the operator-facing marker line (directly tested)."""
    mode = " (dry-run)" if dry_run else ""
    return (
        f"[PGEXPORTER FINDINGS{mode}: filed={result['filed']} "
        f"resolved={result['resolved']} open={result['open']} "
        f"would_file={result['would_file']}]"
    )
