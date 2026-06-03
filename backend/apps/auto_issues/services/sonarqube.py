"""Import SonarQube findings into the AutoIssue work queue."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.categories import get_or_create_category

DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 10
SONARQUBE_TIMEOUT_SECONDS = 15

_SEVERITY_MAP = {
    "BLOCKER": AutoIssue.SEVERITY_CRITICAL,
    "CRITICAL": AutoIssue.SEVERITY_HIGH,
    "HIGH": AutoIssue.SEVERITY_HIGH,
    "MAJOR": AutoIssue.SEVERITY_MEDIUM,
    "MEDIUM": AutoIssue.SEVERITY_MEDIUM,
    "MINOR": AutoIssue.SEVERITY_LOW,
    "LOW": AutoIssue.SEVERITY_LOW,
    "INFO": AutoIssue.SEVERITY_LOW,
}
_PRIORITY_BY_SEVERITY = {
    AutoIssue.SEVERITY_CRITICAL: 0.9,
    AutoIssue.SEVERITY_HIGH: 0.8,
    AutoIssue.SEVERITY_MEDIUM: 0.55,
    AutoIssue.SEVERITY_LOW: 0.3,
}
_SECURITY_TYPES = {"VULNERABILITY", "SECURITY_HOTSPOT"}


class SonarQubeUnavailable(RuntimeError):
    """Raised when SonarQube cannot be reached or returns bad data."""


@dataclass(frozen=True, slots=True)
class SonarImportResult:
    """Counts from one SonarQube import run."""

    created: int = 0
    updated: int = 0
    merged: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated + self.merged


def fetch_sonar_issues(
    *,
    base_url: str,
    project_key: str,
    token: str = "",
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[dict[str, Any]]:
    """Fetch unresolved SonarQube issues through the documented web API."""
    issues: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        payload = _request_issue_page(base_url, project_key, token, page, page_size)
        page_items = list(payload.get("issues") or [])
        issues.extend(page_items)
        if _is_last_page(payload, page, page_size):
            break
    return issues


def ingest_sonarqube_issues(
    project_key: str,
    issues: list[dict[str, Any]],
    *,
    base_url: str = "http://localhost:9000",
) -> SonarImportResult:
    """Create or update AutoIssues for SonarQube findings."""
    counts = {"created": 0, "updated": 0, "merged": 0}
    for issue in issues:
        _row, outcome = _upsert_sonar_issue(project_key, issue, base_url)
        if outcome.startswith("created"):
            counts["created"] += 1
        elif outcome.startswith("updated"):
            counts["updated"] += 1
        else:
            counts["merged"] += 1
    return SonarImportResult(**counts)


def sonar_file_path(issue: dict[str, Any], project_key: str) -> str:
    """Return a repo-relative path from a SonarQube component key."""
    component = str(issue.get("component") or "")
    prefix = f"{project_key}:"
    if component.startswith(prefix):
        return component[len(prefix):].lstrip("/")
    if ":" in component:
        return component.split(":", 1)[1].lstrip("/")
    return component.lstrip("/")


def map_sonar_severity(value: str) -> str:
    """Map SonarQube severity text to this project's severity values."""
    return _SEVERITY_MAP.get((value or "").upper(), AutoIssue.SEVERITY_LOW)


def _request_issue_page(
    base_url: str,
    project_key: str,
    token: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    query = urlencode({
        "componentKeys": project_key,
        "resolved": "false",
        "p": page,
        "ps": page_size,
    })
    url = f"{base_url.rstrip('/')}/api/issues/search?{query}"
    request = Request(url, headers=_headers(token), method="GET")
    try:
        with urlopen(request, timeout=SONARQUBE_TIMEOUT_SECONDS) as response:  # nosec B310
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SonarQubeUnavailable(str(exc)) from exc


def _headers(token: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _is_last_page(payload: dict[str, Any], page: int, page_size: int) -> bool:
    paging = dict(payload.get("paging") or {})
    total = int(paging.get("total") or len(payload.get("issues") or []))
    current_size = int(paging.get("pageSize") or page_size)
    return page * current_size >= total


def _upsert_sonar_issue(project_key: str, issue: dict[str, Any], base_url: str):
    file_path = sonar_file_path(issue, project_key)
    severity = _issue_severity(issue)
    title = _issue_title(issue, file_path)
    external_id = f"sonarqube:{project_key}:{issue.get('key', '')}"
    canonical = _sonar_canonical(project_key, issue, file_path)
    values = _sonar_row_values(
        issue=issue,
        project_key=project_key,
        base_url=base_url,
        file_path=file_path,
        title=title,
        severity=severity,
        canonical=canonical,
    )
    if exact := _active_sonar_external_row(external_id):
        return _refresh_sonar_row(exact, external_id, values, split_legacy=True), "updated"
    if resolved := _resolved_sonar_external_row(external_id):
        return _refresh_sonar_row(resolved, external_id, values, split_legacy=True), "updated"
    if match := _active_sonar_canonical_row(canonical):
        return _refresh_sonar_row(match, external_id, values, split_legacy=False), "merged"
    return _create_sonar_row(external_id, values), "created"


def _sonar_canonical(project_key: str, issue: dict[str, Any], file_path: str) -> str:
    parts = [
        "sonarqube:v2",
        project_key,
        str(issue.get("rule") or ""),
        file_path,
        str(_issue_line(issue)),
        " ".join(str(issue.get("message") or "").lower().split()),
    ]
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _issue_line(issue: dict[str, Any]) -> int | str:
    if issue.get("line") not in (None, ""):
        return issue["line"]
    text_range = issue.get("textRange") or {}
    return dict(text_range).get("startLine") or ""


def _active_sonar_external_row(external_id: str):
    return (
        AutoIssue.objects
        .filter(source=AutoIssue.SOURCE_SONARQUBE, external_id=external_id)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .first()
    )


def _resolved_sonar_external_row(external_id: str):
    return (
        AutoIssue.objects
        .filter(
            source=AutoIssue.SOURCE_SONARQUBE,
            external_id=external_id,
            status=AutoIssue.STATUS_RESOLVED,
        )
        .order_by("-resolved_at", "-id")
        .first()
    )


def _active_sonar_canonical_row(canonical: str):
    return (
        AutoIssue.objects
        .filter(source=AutoIssue.SOURCE_SONARQUBE, canonical_fingerprint=canonical)
        .exclude(status=AutoIssue.STATUS_RESOLVED)
        .first()
    )


def _sonar_row_values(**kwargs) -> dict[str, Any]:
    issue = kwargs["issue"]
    severity = kwargs["severity"]
    file_path = kwargs["file_path"]
    return {
        "fingerprint": kwargs["canonical"],
        "canonical_fingerprint": kwargs["canonical"],
        "title": kwargs["title"][:512],
        "description": _issue_description(
            issue, kwargs["project_key"], file_path, kwargs["base_url"]
        ),
        "affected_files": [file_path] if file_path else [],
        "severity": severity,
        "priority_score": _priority(issue, severity),
        "category": get_or_create_category(_category_key(issue)),
        "last_seen": timezone.now(),
    }


def _create_sonar_row(external_id: str, values: dict[str, Any]) -> AutoIssue:
    now = values["last_seen"]
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_SONARQUBE,
        external_id=external_id,
        occurrence_count=1,
        status=AutoIssue.STATUS_OPEN,
        source_observations=[_sonar_observation(external_id, now)],
        **values,
    )


def _refresh_sonar_row(
    row: AutoIssue,
    external_id: str,
    values: dict[str, Any],
    *,
    split_legacy: bool,
) -> AutoIssue:
    for key, value in values.items():
        setattr(row, key, value)
    row.status = AutoIssue.STATUS_OPEN
    row.resolved_at = None
    row.resolved_by = ""
    row.fix_commit_sha = ""
    row.source_observations = _next_sonar_observations(
        row.source_observations or [], external_id, values["last_seen"], split_legacy
    )
    row.occurrence_count = len(row.source_observations)
    row.save(update_fields=[
        "fingerprint", "canonical_fingerprint", "title", "description",
        "affected_files", "severity", "priority_score", "category",
        "last_seen", "source_observations", "occurrence_count",
        "status", "resolved_at", "resolved_by", "fix_commit_sha",
    ])
    return row


def _next_sonar_observations(
    observations: list, external_id: str, now, split_legacy: bool
) -> list:
    kept = [] if split_legacy else list(observations)
    for obs in kept:
        if obs.get("source") == AutoIssue.SOURCE_SONARQUBE and obs.get("external_id") == external_id:
            obs["last_seen"] = now.isoformat()
            obs["occurrence_count"] = 1
            return kept
    kept.append(_sonar_observation(external_id, now))
    return kept


def _sonar_observation(external_id: str, now) -> dict[str, Any]:
    return {
        "source": AutoIssue.SOURCE_SONARQUBE,
        "external_id": external_id,
        "first_seen": now.isoformat(),
        "last_seen": now.isoformat(),
        "occurrence_count": 1,
    }


def _issue_severity(issue: dict[str, Any]) -> str:
    value = str(issue.get("severity") or _first_impact_severity(issue))
    return map_sonar_severity(value)


def _first_impact_severity(issue: dict[str, Any]) -> str:
    impacts = issue.get("impacts") or []
    if not impacts:
        return ""
    return str(dict(impacts[0]).get("severity") or "")


def _issue_title(issue: dict[str, Any], file_path: str) -> str:
    rule = issue.get("rule") or "unknown-rule"
    return f"[sonarqube] {rule}: {file_path or 'project'}"[:512]


def _issue_description(
    issue: dict[str, Any],
    project_key: str,
    file_path: str,
    base_url: str,
) -> str:
    detail = {
        "key": issue.get("key"),
        "rule": issue.get("rule"),
        "type": issue.get("type"),
        "severity": issue.get("severity"),
        "line": issue.get("line"),
        "file": file_path,
        "message": issue.get("message"),
        "url": _issue_url(base_url, project_key, str(issue.get("key") or "")),
    }
    return json.dumps(detail, indent=2, sort_keys=True)[:4000]


def _issue_url(base_url: str, project_key: str, issue_key: str) -> str:
    query = urlencode({"id": project_key, "open": issue_key})
    return f"{base_url.rstrip('/')}/project/issues?{query}"


def _priority(issue: dict[str, Any], severity: str) -> float:
    score = _PRIORITY_BY_SEVERITY[severity]
    if str(issue.get("type") or "").upper() in _SECURITY_TYPES:
        score += 0.05
    return min(score, 0.95)


def _category_key(issue: dict[str, Any]) -> str:
    issue_type = str(issue.get("type") or "").upper()
    if issue_type in _SECURITY_TYPES:
        return "security"
    if issue_type == "BUG":
        return "correctness"
    return "maintainability"
