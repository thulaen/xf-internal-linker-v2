"""Internal-errors picker — `audit_errorlog source='internal'` → AutoIssue.

Closes the third source-coverage gap: errors caught in-process by the
codebase's own `apps.audit.error_ingest.ingest_error()` calls (Celery
task failures, FAISS init errors, etc.) now flow into the auto_issues
table alongside GlitchTip-mirrored issues and Pyroscope regressions.

Cross-source dedup via `services.dedup.upsert_dedup` — when the same
exception is captured by both ingest_error AND GlitchTip, it lands on
ONE AutoIssue row, not two. The row's `source_observations` JSON tracks
which sources observed the error.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.scoring import Candidate, score_candidate

if TYPE_CHECKING:
    from apps.audit.models import ErrorLog

logger = logging.getLogger(__name__)

_MAX_PER_RUN = 10


def _candidate_for_internal(row: "ErrorLog", *, max_blast: int) -> Candidate:
    return Candidate(
        source=AutoIssue.SOURCE_AGENT,
        external_id=str(row.fingerprint or row.pk),
        fingerprint=row.fingerprint,
        severity=row.severity,
        last_seen=row.created_at,
        blast_observed=float(row.occurrence_count),
        blast_max=float(max(max_blast, 1)),
        num_affected_files=1 if (row.step or "") else 0,
    )


def _fetch_internal_rows():
    """Open internal-source rows from the audit_errorlog mirror."""
    from apps.audit.models import ErrorLog

    return list(
        ErrorLog.objects.filter(
            source=ErrorLog.SOURCE_INTERNAL, acknowledged=False
        ).order_by("-occurrence_count", "-created_at")
    )


def _affected_files_for_step(step: str) -> list[str]:
    """Best-effort step → file_path mapping. Same shape as glitchtip_picker."""
    if not step:
        return []
    module = step.split(":", 1)[0].split(".in.", 1)[0]
    if not module or "." not in module:
        return []
    try:
        import importlib

        mod = importlib.import_module(module)
    except (ImportError, ValueError, ModuleNotFoundError):
        return []
    file_path = getattr(mod, "__file__", "") or ""
    if not file_path:
        return []
    if file_path.startswith("/app/"):
        return ["backend/" + file_path[len("/app/"):]]
    return [file_path]


def _empty_result() -> dict:
    return {
        "status": "ok",
        "fetched": 0,
        "promoted": 0,
        "created": 0,
        "merged": 0,
        "updated": 0,
    }


def _upsert_one_internal_row(score: float, cand: Candidate, row) -> str:
    """Single upsert for one internal-source row. Returns dedup outcome."""
    title = (row.error_message or "")[:512]
    canonical = canonical_fingerprint(title, row.step or "")
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=cand.source,
        external_id=cand.external_id,
        fingerprint=cand.fingerprint,
        title=title,
        description=(row.how_to_fix or "")[:4000],
        affected_files=_affected_files_for_step(row.step or ""),
        severity=cand.severity,
        priority_score=float(score),
        occurrence_count=int(cand.blast_observed),
    )
    return outcome


def pick_internal_issues(*, limit: int = _MAX_PER_RUN) -> dict:
    """Top-K internal errors → AutoIssue (with cross-source dedup)."""
    rows = _fetch_internal_rows()
    if not rows:
        return _empty_result()

    max_blast = max((r.occurrence_count for r in rows), default=1)
    cands = [_candidate_for_internal(r, max_blast=max_blast) for r in rows]
    scored = sorted(
        ((score_candidate(c), c, r) for c, r in zip(cands, rows)),
        key=lambda triple: triple[0],
        reverse=True,
    )

    counts = {"created": 0, "merged": 0, "updated": 0}
    for score, cand, row in scored[:limit]:
        outcome = _upsert_one_internal_row(score, cand, row)
        counts[outcome] = counts.get(outcome, 0) + 1

    logger.info(
        "[auto_issues.internal_picker] fetched=%d created=%d merged=%d updated=%d",
        len(rows), counts["created"], counts["merged"], counts["updated"],
    )
    return {
        "status": "ok",
        "fetched": len(rows),
        "promoted": sum(counts.values()),
        **counts,
    }
