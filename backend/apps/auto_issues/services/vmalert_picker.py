from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup

logger = logging.getLogger(__name__)


def pick_vmalert_alerts() -> int:
    alerts = _fetch_alerts()
    count = 0
    for alert in alerts:
        if _upsert_alert(alert):
            count += 1
    return count


def _fetch_alerts() -> list[dict[str, Any]]:
    url = getattr(settings, "VMALERT_API_URL", "http://vmalert:8880")
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/v1/alerts", timeout=10) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.info("vmalert_picker: unable to read alerts: %s", exc)
        return []
    data = payload.get("data", payload)
    return data.get("alerts", []) if isinstance(data, dict) else []


def _upsert_alert(alert: dict[str, Any]) -> bool:
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    name = labels.get("alertname") or alert.get("name")
    if not name:
        return False
    state = (alert.get("state") or "firing").lower()
    fingerprint = _fingerprint(name, labels)
    issue = _upsert_open_alert(name, labels, annotations, fingerprint)
    if state == "resolved":
        _resolve_issue(issue, annotations)
    return True


def _upsert_open_alert(name: str, labels: dict, annotations: dict, fingerprint: str) -> AutoIssue:
    severity = labels.get("severity", AutoIssue.SEVERITY_MEDIUM)
    if severity not in dict(AutoIssue.SEVERITY_CHOICES):
        severity = AutoIssue.SEVERITY_MEDIUM
    affected = [labels["affected_file"]] if labels.get("affected_file") else []
    issue, _ = upsert_dedup(
        canonical=fingerprint,
        source=AutoIssue.SOURCE_VMALERT,
        external_id=fingerprint,
        fingerprint=fingerprint,
        title=f"[vmalert] {name}",
        description=annotations.get("description", annotations.get("summary", "")),
        affected_files=affected,
        severity=severity,
        priority_score=_priority(severity),
        occurrence_count=_next_occurrence_count(fingerprint),
    )
    return issue


def _next_occurrence_count(fingerprint: str) -> int:
    existing = (
        AutoIssue.objects
        .filter(source=AutoIssue.SOURCE_VMALERT, external_id=fingerprint)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .first()
    )
    if existing is None:
        return 1
    return int(existing.occurrence_count or 0) + 1


def _resolve_issue(issue: AutoIssue, annotations: dict) -> None:
    trap = annotations.get("trap", "The metric alert resolved before a human wrote the lesson.")
    fix = annotations.get("fix_shape", "Keep the alert annotations specific enough for the next repair.")
    issue.status = AutoIssue.STATUS_RESOLVED
    issue.resolved_at = timezone.now()
    issue.resolved_by = "vmalert"
    issue.lessons_learned = f"Trap: {trap} Fix shape: {fix}"
    issue.save(update_fields=["status", "resolved_at", "resolved_by", "lessons_learned"])


def _fingerprint(name: str, labels: dict) -> str:
    stable = json.dumps({"alertname": name, "labels": labels}, sort_keys=True)
    return hashlib.sha1(stable.encode(), usedforsecurity=False).hexdigest()


def _priority(severity: str) -> float:
    return {
        AutoIssue.SEVERITY_CRITICAL: 0.95,
        AutoIssue.SEVERITY_HIGH: 0.8,
        AutoIssue.SEVERITY_MEDIUM: 0.55,
        AutoIssue.SEVERITY_LOW: 0.3,
    }.get(severity, 0.55)
