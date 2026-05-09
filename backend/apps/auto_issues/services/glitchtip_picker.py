"""GlitchTip → AutoIssue picker.

Reads the local `audit_errorlog` mirror (already kept fresh by the
existing `audit.sync_glitchtip_issues` Celery task, every 30 min) and
upserts the top GlitchTip-sourced rows into `auto_issues` with a
priority score from `services.scoring`.

Design decision (from SPEC § Open design decisions, item a):
We read the local mirror, NOT GlitchTip's API directly. Reasons:
  - One source of truth (the mirror is the canonical dedup point).
  - Zero new HTTP calls — the daily picker becomes a pure DB job.
  - The mirror already filters by `acknowledged=False` (unresolved only).

Design decision (item b — affected_files):
We derive `affected_files` from the `culprit` field plus a heuristic
mapping `module → file` via Python introspection. When the culprit
doesn't resolve to an importable module, we fall back to an empty list
and let the agent fill it in when picking the issue.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.scoring import Candidate, score_candidate

if TYPE_CHECKING:
    from apps.audit.models import ErrorLog

logger = logging.getLogger(__name__)

# Cap how many issues we promote into auto_issues per run. Anti-bloat
# guarantee from the SPEC.
_MAX_PER_RUN = 10


def _affected_files_for_culprit(culprit: str) -> list[str]:
    """Best-effort `culprit -> [file_path]` mapping.

    GlitchTip's `culprit` is `module.path:function_name` (Sentry-style).
    We import the module and pull `__file__`. If the import fails (e.g.
    the culprit is a stdlib path or a frame from a removed module), we
    return [].
    """
    if not culprit:
        return []
    module_name = culprit.split(":", 1)[0].split(".in.", 1)[0]
    if not module_name or "." not in module_name:
        return []
    try:
        mod = importlib.import_module(module_name)
    except (ImportError, ValueError, ModuleNotFoundError):
        return []
    file_path = getattr(mod, "__file__", "") or ""
    if not file_path:
        return []
    # Convert /app/apps/audit/tasks.py → backend/apps/audit/tasks.py for
    # repo-relative reading by humans / agents.
    if file_path.startswith("/app/"):
        return ["backend/" + file_path[len("/app/") :]]
    return [file_path]


def _candidate_from_errorlog(row: "ErrorLog", *, max_blast: int) -> Candidate:
    """Build a Candidate from a glitchtip-source ErrorLog row."""
    return Candidate(
        source=AutoIssue.SOURCE_GLITCHTIP,
        external_id=str(row.glitchtip_issue_id),
        fingerprint=row.fingerprint,
        severity=row.severity,
        last_seen=row.created_at,
        blast_observed=float(row.occurrence_count),
        blast_max=float(max(max_blast, 1)),
        num_affected_files=len(_affected_files_for_culprit(row.step or "")),
    )


def _fetch_unresolved_mirror_rows():
    """Pull unresolved GlitchTip rows from the local audit_errorlog mirror."""
    from apps.audit.models import ErrorLog

    return list(
        ErrorLog.objects.filter(
            source=ErrorLog.SOURCE_GLITCHTIP, acknowledged=False
        )
        .exclude(glitchtip_issue_id="")
        .order_by("-occurrence_count", "-created_at")
    )


def _upsert_promoted_row(score: float, cand: Candidate, row, now) -> str:
    """Cross-source-dedup upsert for one GT row. Returns 'created'/'merged'/'updated'."""
    title = (row.error_message or "")[:512]
    canonical = canonical_fingerprint(title, row.step or "")
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=cand.source,
        external_id=cand.external_id,
        fingerprint=cand.fingerprint,
        title=title,
        description=(row.how_to_fix or "")[:4000],
        affected_files=_affected_files_for_culprit(row.step or ""),
        severity=cand.severity,
        priority_score=float(score),
        occurrence_count=int(cand.blast_observed),
    )
    return outcome


def pick_glitchtip_issues(*, limit: int = _MAX_PER_RUN) -> dict:
    """Read the GT mirror, score, write top-K into auto_issues.

    Idempotent: rows are upserted via `(source, external_id)` unique
    constraint. Re-running the same day refreshes scores without dups.
    """
    rows = _fetch_unresolved_mirror_rows()
    if not rows:
        return {"status": "ok", "fetched": 0, "promoted": 0}

    max_blast = max((r.occurrence_count for r in rows), default=1)
    candidates = [_candidate_from_errorlog(r, max_blast=max_blast) for r in rows]
    scored = sorted(
        ((score_candidate(c), c, r) for c, r in zip(candidates, rows)),
        key=lambda triple: triple[0],
        reverse=True,
    )

    now = timezone.now()
    created = merged = updated = 0
    for score, cand, row in scored[:limit]:
        outcome = _upsert_promoted_row(score, cand, row, now)
        if outcome == "created":
            created += 1
        elif outcome == "merged":
            merged += 1
        else:
            updated += 1

    logger.info(
        "[auto_issues.glitchtip_picker] fetched=%d created=%d merged=%d updated=%d",
        len(rows), created, merged, updated,
    )
    return {
        "status": "ok",
        "fetched": len(rows),
        "promoted": created + merged + updated,
        "created": created,
        "merged": merged,
        "updated": updated,
    }
