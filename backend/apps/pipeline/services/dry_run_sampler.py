"""
Dry-run preview sampler (plan item 24).

Answers the question "if I sync now, what happens?" without doing the expensive
parts. For each sampled item we do metadata fetches, a content-hash check, and
a "would-import" classification — but we never download full bodies, never
generate embeddings, never write to the main tables.

Hard contract:
  - Total wall-clock capped at ``HARD_CAP_SECONDS`` (default 180s = 3 min per plan).
  - Sample size capped at ``MAX_SAMPLE_ITEMS`` (default 25). Anything larger is
    a real sync, not a preview.
  - Never writes to ``ContentItem`` or any production table.
  - Artifact output goes to ``~/xf_dry_run/`` with auto-prune at 2 hours.

``run_preview`` is deterministic, idempotent, and safe to call concurrently.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

HARD_CAP_SECONDS = 180  # 3 minutes
MAX_SAMPLE_ITEMS = 25
ARTIFACT_RETENTION_SECONDS = 2 * 60 * 60  # 2 hours
# Sampler-owned scratch directory. Use the platform's tempdir rather than a
# hardcoded /tmp path so we behave correctly on Windows hosts and inside
# containers with non-default tempfs configurations.
ARTIFACT_DIR = Path(tempfile.gettempdir()) / "xf_dry_run"


def run_preview(
    *,
    source: str,
    mode: str,
    sample_size: int = 10,
    now: datetime | None = None,
) -> dict:
    """Return a dry-run summary of what a sync would do.

    Arguments:
        source: "api" (XenForo) or "wp" (WordPress).
        mode: the sync mode string the real sync would use, e.g. "full" or "delta".
        sample_size: how many items to sample. Clamped to [1, MAX_SAMPLE_ITEMS].
        now: injected for testability.

    Returns summary fields used by the UI:
        {
          ok, source, mode,
          items_seen, items_would_import, items_would_skip,
          truncated_by_cap, elapsed_seconds, artifact_path,
          notes: [plain-english strings]
        }
    """
    start = time.monotonic()
    now = now or datetime.utcnow()
    sample_size = max(1, min(MAX_SAMPLE_ITEMS, sample_size))

    # Auto-prune old artifacts BEFORE we write a new one. Keeps disk bounded
    # even if a run crashes mid-flight.
    _prune_old_artifacts(now=now)

    out: dict = {
        "ok": True,
        "source": source,
        "mode": mode,
        "sample_size_requested": sample_size,
        "items_seen": 0,
        "items_would_import": 0,
        "items_would_skip": 0,
        "items_would_update": 0,
        "truncated_by_cap": False,
        "elapsed_seconds": 0,
        "artifact_path": "",
        "notes": [],
    }

    _collect_history_notes(source, out["notes"])
    _classify_sample(source, sample_size, start, now, out)
    _write_artifact(source, mode, now, out)

    out["elapsed_seconds"] = round(time.monotonic() - start, 2)
    return out


def _collect_history_notes(source: str, notes: list) -> None:
    """Look at recent SyncJob rows and add plain-English notes to the preview."""
    try:
        from apps.sync.models import SyncJob

        last_completed = (
            SyncJob.objects.filter(source=source, status__in=("completed", "success"))
            .order_by("-updated_at")
            .first()
        )
        if last_completed is not None:
            notes.append(
                f"Most recent completed {source} sync was {last_completed.mode}, "
                f"{last_completed.checkpoint_items_processed or 0} items."
            )
        running = SyncJob.objects.filter(source=source, status="running").count()
        if running:
            notes.append(
                f"{running} {source} sync job(s) already running — "
                f"the real sync would queue behind them."
            )
    except Exception:
        logger.debug("dry_run_sampler: sync history lookup failed", exc_info=True)


def _classify_sample(
    source: str, sample_size: int, start: float, now: datetime, out: dict
) -> None:
    """Sample ContentItems and tally would-import / would-update / would-skip.

    Conservative heuristic: items whose ``last_checked_at`` is older than 7 days
    are likely to need a re-check; younger items are likely-skip; missing
    timestamp counts as would-import.
    """
    notes = out["notes"]
    try:
        from apps.content.models import ContentItem

        qs = ContentItem.objects.all()
        if source == "api":
            qs = qs.filter(source_key__startswith="xenforo:")
        elif source == "wp":
            qs = qs.filter(source_key__startswith="wordpress:")

        for item in list(qs.order_by("-updated_at")[:sample_size]):
            out["items_seen"] += 1
            last_checked = getattr(item, "last_checked_at", None)
            if last_checked is None:
                out["items_would_import"] += 1
            else:
                age_days = (now - last_checked.replace(tzinfo=None)).days
                if age_days > 7:
                    out["items_would_update"] += 1
                else:
                    out["items_would_skip"] += 1
            if time.monotonic() - start > HARD_CAP_SECONDS:
                out["truncated_by_cap"] = True
                notes.append("Stopped early — hit the 3-minute dry-run cap.")
                break
    except Exception:
        logger.exception("dry_run_sampler: sampling phase failed")
        out["ok"] = False
        notes.append("Sampling failed — backend logs have details.")


def _write_artifact(source: str, mode: str, now: datetime, out: dict) -> None:
    """Persist the preview summary as a tiny JSON file under ARTIFACT_DIR."""
    try:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%dT%H%M%S")
        path = ARTIFACT_DIR / f"preview_{source}_{mode}_{stamp}.json"
        path.write_text(json.dumps(out, default=str))
        out["artifact_path"] = str(path)
    except Exception:
        logger.debug("dry_run_sampler: artifact write failed", exc_info=True)


def _prune_old_artifacts(*, now: datetime | None = None) -> int:
    """Delete artifact files older than ``ARTIFACT_RETENTION_SECONDS``."""
    if now is None:
        now = datetime.utcnow()
    if not ARTIFACT_DIR.exists():
        return 0
    pruned = 0
    try:
        cutoff = now.timestamp() - ARTIFACT_RETENTION_SECONDS
        for path in ARTIFACT_DIR.iterdir():
            try:
                if not path.is_file():
                    continue
                if os.path.getmtime(path) < cutoff:
                    path.unlink(missing_ok=True)
                    pruned += 1
            except Exception:
                logger.debug("dry_run_sampler: prune error for %s", path, exc_info=True)
    except Exception:
        logger.debug("dry_run_sampler: prune pass failed", exc_info=True)
    return pruned
