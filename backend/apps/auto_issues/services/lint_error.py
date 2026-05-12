"""Super-Linter SARIF picker — Phase 6 of the test-hardening plan.

Reads `super-linter.log` (SARIF JSON) and upserts one AutoIssue per
unique (rule, file) pair above the configured severity threshold.

Tool family ('agent' source — these are static-analysis findings; the
dedicated 'mutation' / 'fuzz' / 'contract' / 'gh_ci' sources are
reserved for the higher-signal pickers).

AppSettings (seeded by migration 0008):
- lint_error.sarif_path       (default: super-linter.log)
- lint_error.min_severity     (default: warning)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.conf import settings
from opentelemetry import trace

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

_SARIF_SEVERITY_ORDER = {"note": 0, "warning": 1, "error": 2}


def _appsetting(key: str, default: str) -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
        if row and row.value:
            return str(row.value)
    except Exception:  # noqa: BLE001
        pass
    return default


def _resolve(p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    base = getattr(settings, "BASE_DIR", Path.cwd())
    return Path(base) / p


def _load_sarif(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        logger.info("lint_error picker: %s not present or unparseable; skipping", path)
        return {}


def pick_lint_errors() -> int:
    """Read the SARIF report and upsert each finding. Returns row count."""
    sarif = _load_sarif(_resolve(_appsetting("lint_error.sarif_path", "super-linter.log")))
    if not sarif:
        return 0
    min_severity = _appsetting("lint_error.min_severity", "warning").lower()
    min_rank = _SARIF_SEVERITY_ORDER.get(min_severity, 1)

    count = 0
    for run in sarif.get("runs", []):
        tool_name = run.get("tool", {}).get("driver", {}).get("name", "super-linter")
        for result in run.get("results", []):
            severity = (result.get("level") or "warning").lower()
            if _SARIF_SEVERITY_ORDER.get(severity, 1) < min_rank:
                continue
            rule = result.get("ruleId", "?")
            msg = result.get("message", {}).get("text", "")
            for loc in result.get("locations", []):
                uri = loc.get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "?")
                if _upsert_finding(tool_name, rule, uri, msg, severity):
                    count += 1
                    break  # one row per (rule, file) pair
    logger.info("lint_error picker: landed %d AutoIssue rows", count)
    return count


def _upsert_finding(tool: str, rule: str, file_uri: str, message: str, sarif_level: str) -> bool:
    title = f"[lint-error] {tool} {rule}: {file_uri}"
    culprit = f"{rule}|{file_uri}"
    fp = canonical_fingerprint(title, culprit)
    project_severity = _sarif_to_project_severity(sarif_level)
    with _tracer.start_as_current_span(
        "auto_issue.created",
        attributes={
            "source": AutoIssue.SOURCE_AGENT,
            "kind": "lint-error",
            "fingerprint": fp,
            "severity": project_severity,
            "tool": tool,
        },
    ):
        try:
            upsert_dedup(
                canonical=fp,
                source=AutoIssue.SOURCE_AGENT,
                external_id=f"{tool}:{rule}:{file_uri}",
                fingerprint=fp,
                title=title[:120],
                description=f"Tool: {tool}\nRule: {rule}\nFile: {file_uri}\n\n{message}",
                affected_files=[file_uri],
                severity=project_severity,
                priority_score=0.4,
                occurrence_count=1,
            )
        except Exception:  # noqa: BLE001
            logger.exception("lint_error picker: upsert failed for %s/%s", tool, rule)
            return False
    return True


def _sarif_to_project_severity(sarif_level: str) -> str:
    return {
        "error": AutoIssue.SEVERITY_HIGH,
        "warning": AutoIssue.SEVERITY_MEDIUM,
        "note": AutoIssue.SEVERITY_LOW,
    }.get(sarif_level.lower(), AutoIssue.SEVERITY_LOW)
