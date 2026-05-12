"""Mutation-testing picker — Phase 6 of the test-hardening plan.

Reads mutmut JSON (Python), Stryker JSON (TypeScript), and Mull JSON
(C++) report files and upserts one AutoIssue per surviving mutant.

Report-path AppSettings (seeded by migration 0008):
- mutation.mutmut.report_path       (default: backend/reports/mutmut.json)
- mutation.stryker.report_path      (default: frontend/reports/stryker.json)
- mutation.mull.report_path         (default: backend/extensions/reports/mull/mutants.json)

The function is split into three pure helpers (one per tool) plus a
top-level `pick_mutation_survivors()` that runs all three. Each helper
returns the list of rows it produced so the caller can sum + log.

Graceful fallback: when a report file is missing or unparseable, the
helper logs a warning and returns []. Pickers are best-effort; CI is
the safety net for real failures.
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


def _appsetting(key: str, default: str) -> str:
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
        if row and row.value:
            return str(row.value)
    except Exception:  # noqa: BLE001 — defensive at startup
        pass
    return default


def _resolve(report_path: str) -> Path:
    """Resolve a possibly-relative path against Django BASE_DIR."""
    p = Path(report_path)
    if p.is_absolute():
        return p
    base = getattr(settings, "BASE_DIR", Path.cwd())
    return Path(base) / report_path


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.info("mutation picker: %s not present or unparseable; skipping", path)
        return None


def _upsert_mutant(tool: str, kind: str, mutator: str, source_path: str, line: int, diff: str) -> bool:
    title = f"{tool} surviving mutant: {mutator} at {source_path}:{line}"
    culprit = f"{source_path}:{line}"
    fp = canonical_fingerprint(title, culprit)
    with _tracer.start_as_current_span(
        "auto_issue.created",
        attributes={
            "source": AutoIssue.SOURCE_MUTATION,
            "kind": kind,
            "fingerprint": fp,
            "severity": AutoIssue.SEVERITY_MEDIUM,
            "tool": tool,
        },
    ):
        try:
            upsert_dedup(
                canonical=fp,
                source=AutoIssue.SOURCE_MUTATION,
                external_id=f"{tool}:{mutator}:{culprit}",
                fingerprint=fp,
                title=title,
                description=f"Tool: {tool}\nKind: {kind}\n\nDiff:\n{diff[:2000]}",
                affected_files=[source_path],
                severity=AutoIssue.SEVERITY_MEDIUM,
                priority_score=0.5,
                occurrence_count=1,
            )
        except Exception:  # noqa: BLE001
            logger.exception("mutation picker: upsert failed for %s mutant %s", tool, culprit)
            return False
    return True


def _pick_mutmut() -> int:
    path = _resolve(_appsetting("mutation.mutmut.report_path", "backend/reports/mutmut.json"))
    data = _load_json(path)
    if not data:
        return 0
    # mutmut JSON format: list of mutant records with status, mutator, file, line, diff
    count = 0
    for m in (data if isinstance(data, list) else data.get("mutants", [])):
        if m.get("status") != "survived":
            continue
        if _upsert_mutant(
            tool="mutmut",
            kind="py-mutant",
            mutator=m.get("mutator", "?"),
            source_path=m.get("file") or m.get("source_path", "?"),
            line=int(m.get("line", 0)),
            diff=m.get("diff", ""),
        ):
            count += 1
    return count


def _pick_stryker() -> int:
    path = _resolve(_appsetting("mutation.stryker.report_path", "frontend/reports/stryker.json"))
    data = _load_json(path)
    if not data:
        return 0
    # Stryker schema: files dict → mutants list with status, mutatorName, location
    files = data.get("files", {}) if isinstance(data, dict) else {}
    count = 0
    for file_path, payload in files.items():
        for m in payload.get("mutants", []):
            if m.get("status") != "Survived":
                continue
            loc = m.get("location", {}).get("start", {})
            if _upsert_mutant(
                tool="stryker",
                kind="ts-mutant",
                mutator=m.get("mutatorName", "?"),
                source_path=file_path,
                line=int(loc.get("line", 0)),
                diff=m.get("replacement", "")[:500],
            ):
                count += 1
    return count


def _pick_mull() -> int:
    path = _resolve(_appsetting("mutation.mull.report_path", "backend/extensions/reports/mull/mutants.json"))
    data = _load_json(path)
    if not data:
        return 0
    # Mull schema: list of mutant records with status, mutator, location.file/line
    count = 0
    for m in (data if isinstance(data, list) else data.get("mutants", [])):
        if m.get("status") != "Survived":
            continue
        loc = m.get("location", {})
        if _upsert_mutant(
            tool="mull",
            kind="cpp-mutant",
            mutator=m.get("mutator", "?"),
            source_path=loc.get("file", "?"),
            line=int(loc.get("line", 0)),
            diff="",
        ):
            count += 1
    return count


def pick_mutation_survivors() -> int:
    """Run all three mutation-tool readers. Returns total rows landed."""
    total = _pick_mutmut() + _pick_stryker() + _pick_mull()
    logger.info("mutation picker: landed %d AutoIssue rows", total)
    return total
