"""Pact provider-verification drift picker — Phase 6 of the test-hardening plan.

Reads the JSON output of the Django Pact provider verification test
(`backend/apps/api/tests/test_pact_provider.py`) and upserts one
AutoIssue per failed (consumer, interaction) pair.

AppSettings:
- contract_drift.pact_results_path (default: backend/reports/pact-provider-results.json)

Status: scaffolding only — the actual Pact contracts land in a
follow-up PR. This picker is wired and DEFAULT-ON so that when the
first contract verification fails, the drift surfaces in the standard
18-pick queue with `source='contract'`.

The picker is safe to schedule on a JSON file that doesn't yet exist:
it returns 0 with a log line and exits cleanly.
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
    except Exception:  # noqa: BLE001
        pass
    return default


def _resolve(p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    base = getattr(settings, "BASE_DIR", Path.cwd())
    return Path(base) / p


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.info("contract_drift picker: %s not present; skipping", path)
        return None


def pick_contract_drift() -> int:
    """Scan Pact verification results and upsert failures. Returns row count."""
    path = _resolve(_appsetting("contract_drift.pact_results_path", "backend/reports/pact-provider-results.json"))
    data = _load_json(path)
    if not data:
        return 0

    # Expected shape (pact-python ProviderVerifier output):
    #   {"failures": [{"consumer": "...", "interaction": "...", "details": "..."}]}
    failures = data.get("failures", []) if isinstance(data, dict) else []
    count = 0
    for failure in failures:
        if _upsert_failure(failure):
            count += 1
    logger.info("contract_drift picker: landed %d AutoIssue rows", count)
    return count


def _upsert_failure(failure: dict[str, Any]) -> bool:
    consumer = failure.get("consumer", "?")
    interaction = failure.get("interaction", "?")
    details = failure.get("details", "")

    title = f"[contract-drift] {consumer}: {interaction}"
    culprit = f"{consumer}|{interaction}"
    fp = canonical_fingerprint(title, culprit)
    with _tracer.start_as_current_span(
        "auto_issue.created",
        attributes={
            "source": AutoIssue.SOURCE_CONTRACT,
            "kind": "drift",
            "fingerprint": fp,
            "severity": AutoIssue.SEVERITY_HIGH,
            "tool": "pact",
        },
    ):
        try:
            upsert_dedup(
                canonical=fp,
                source=AutoIssue.SOURCE_CONTRACT,
                external_id=f"{consumer}:{interaction}",
                fingerprint=fp,
                title=title,
                description=f"Consumer: {consumer}\nInteraction: {interaction}\n\nDetails:\n{details[:2000]}",
                affected_files=[],
                severity=AutoIssue.SEVERITY_HIGH,
                priority_score=0.75,
                occurrence_count=1,
            )
        except Exception:  # noqa: BLE001
            logger.exception("contract_drift picker: upsert failed for %s/%s", consumer, interaction)
            return False
    return True
