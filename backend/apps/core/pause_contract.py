"""
Per-job-type safe-pause-point contracts (plan item 29).

Every worker module (imports, crawls, embeddings, broken-link scans,
spaCy/NLP, pipeline runs) should call ``should_pause_now`` at its declared
**safe boundary** — not mid-batch — so a master pause or an individual job
pause flag can take effect without leaving data in a half-done state.

Declared boundaries:

  imports              -> between page batches           (e.g., each fetched page)
  crawls               -> between URL batches            (e.g., each requests.get cohort)
  embeddings           -> between chunk batches          (e.g., each model.encode call)
  broken_link_scans    -> between segments               (e.g., each ~hundred-URL segment)
  spacy_nlp            -> between document batches       (e.g., each nlp.pipe call)
  pipeline             -> at stage or destination-batch boundaries

Callers invoke the helper exactly once at the boundary. If it returns True,
the worker should save its checkpoint and exit cleanly. The reason string is
logged so operators can see WHY the worker stopped.

This module is intentionally tiny and has zero framework-specific imports so
it can be unit-tested without Celery.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

logger = logging.getLogger(__name__)

JobType = Literal[
    "imports",
    "crawls",
    "embeddings",
    "broken_link_scans",
    "spacy_nlp",
    "pipeline",
]

_ALLOWED_JOB_TYPES: set[str] = {
    "imports",
    "crawls",
    "embeddings",
    "broken_link_scans",
    "spacy_nlp",
    "pipeline",
}


def should_pause_now(
    *,
    job_type: JobType,
    job_id: Optional[str] = None,
) -> tuple[bool, str]:
    """Return (should_pause, reason).

    Checks, in order:
      1. ``system.master_pause`` — operator hit the global pause button (item 28).
      2. Per-job pause flag on the SyncJob (``status='paused'``) if a job_id is given.

    Never raises. If anything goes wrong reading AppSetting, returns (False, "")
    so a DB outage can't accidentally pause every worker.
    """
    if job_type not in _ALLOWED_JOB_TYPES:
        # Unknown job type — be safe, never pause. Operator can still master-pause.
        logger.debug("should_pause_now called with unknown job_type=%s", job_type)

    try:
        from apps.core.models import AppSetting

        master = (
            AppSetting.objects.filter(key="system.master_pause")
            .values_list("value", flat=True)
            .first()
        )
        if master and master.lower() == "true":
            return True, "system.master_pause is on"
    except Exception:
        logger.debug("should_pause_now: AppSetting read failed", exc_info=True)

    # Per-job flag (only meaningful for SyncJob-backed work).
    if job_id and job_type in ("imports", "crawls", "broken_link_scans"):
        try:
            from apps.sync.models import SyncJob

            row = (
                SyncJob.objects.filter(job_id=job_id)
                .values_list("status", flat=True)
                .first()
            )
            if row == "paused":
                return True, f"job {job_id} was paused by user"
        except Exception:
            logger.debug("should_pause_now: SyncJob read failed", exc_info=True)

    return False, ""


def safe_boundary_label(job_type: JobType) -> str:
    """Plain-English label for which boundary this job type is allowed to pause at.

    Useful in operator-facing UI so the user understands why "Pause" did not
    take effect immediately — the worker will stop at the next safe boundary.
    """
    return {
        "imports": "next page batch",
        "crawls": "next URL batch",
        "embeddings": "next chunk batch",
        "broken_link_scans": "next segment",
        "spacy_nlp": "next document batch",
        "pipeline": "next stage or destination-batch boundary",
    }.get(job_type, "next safe boundary")
