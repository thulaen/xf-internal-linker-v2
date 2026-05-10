"""Phase 4.5 — "Why Is This Taking So Long?" Panel backend.

Plain-English: when a long job is running, the operator clicks a
"Why's this slow?" button on the job's modal and sees a structured
panel: current step, items done, ETA, the system's bottleneck verdict
("disk-bound right now"), and a one-click action chip to address it.

This module is the BACKEND service the panel reads. It composes:

    * stage tracker — Redis-backed live state (current_stage, items_done,
      items_total, started_at) emitted by the long-running task itself
      via ``publish_stage_update()``
    * ``slowness_analyzer.analyze_slowness()`` — already shipped in
      this package; returns a one-word verdict + why-string + confidence
    * ETA computation — items_done / wall_clock_elapsed → seconds-per-item
      → multiply by remaining items

Storage discipline: live state in Redis with 1 h TTL (per plan 4.5
sub-gap 9). Auto-snapshot on stall fires from the existing OperationsFeed
emit (deferred to a later session; not in this minimal slice).

Citations: ETA pattern from Hellerstein 2003 §5 (statistical progress
estimators); stall-detection from Linux PSI papers (Andrei 2018).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from django.core.cache import cache

logger = logging.getLogger(__name__)


# Redis key prefix for live job stage state.
_STAGE_CACHE_PREFIX = "why_so_long.stage."

# 1 h TTL on stage state — long enough to outlive any reasonable job;
# short enough that stale state from a crashed worker self-evicts.
_STAGE_CACHE_TTL_SECONDS = 60 * 60

# Minimum items_done to trust the items-per-second moving average.
# Fewer than this and the ETA is too noisy to report.
_MIN_ITEMS_FOR_ETA = 5


@dataclass(frozen=True, slots=True)
class StageUpdate:
    """One stage-state snapshot emitted by the running task."""

    job_key: str
    stage_name: str
    items_done: int
    items_total: int
    started_at_epoch: float
    last_update_at_epoch: float
    plain_english_what: str = ""


@dataclass(frozen=True, slots=True)
class WhySoLongPanel:
    """Operator-facing panel state for one running job."""

    job_key: str
    found: bool
    stage: StageUpdate | None
    bottleneck_verdict: str  # cpu_bound / gpu_bound / etc, or "unknown"
    bottleneck_why: str
    bottleneck_confidence: float
    items_per_second: float | None
    eta_seconds: float | None
    elapsed_seconds: float
    progress_pct: float | None
    action_chips: list[dict[str, str]] = field(default_factory=list)


def publish_stage_update(
    *,
    job_key: str,
    stage_name: str,
    items_done: int,
    items_total: int,
    plain_english_what: str = "",
) -> None:
    """Emit a stage-state update from inside a long-running task.

    Plain-English: the task tells the panel "I'm now on step 'embedding
    pass 3 of 5', I've done 2,300 of 5,000 items, and what I'm currently
    doing is 'computing BGE-M3 vectors for posts 4500-5000'." The panel
    reads this Redis key on demand to render the operator's display.

    Best-effort — never raises. A Redis blip just means the panel shows
    stale data until the next update lands.
    """
    now = time.time()
    cache_key = _STAGE_CACHE_PREFIX + job_key
    existing = cache.get(cache_key)
    started_at = existing.started_at_epoch if isinstance(existing, StageUpdate) else now
    update = StageUpdate(
        job_key=job_key,
        stage_name=stage_name,
        items_done=int(items_done),
        items_total=int(items_total),
        started_at_epoch=started_at,
        last_update_at_epoch=now,
        plain_english_what=plain_english_what,
    )
    try:
        cache.set(cache_key, update, _STAGE_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001 — Redis blip just costs us one stage update; not worth raising.
        logger.debug("publish_stage_update: cache.set failed", exc_info=True)


def get_panel(job_key: str) -> WhySoLongPanel:
    """Build the panel state for one running job.

    Returns a panel with ``found=False`` when no stage update has been
    published for this job_key (e.g. the task hasn't reached its first
    ``publish_stage_update()`` call yet, or the cache has expired).
    Operator UI hides the panel in that case.
    """
    cache_key = _STAGE_CACHE_PREFIX + job_key
    stage = cache.get(cache_key)
    if not isinstance(stage, StageUpdate):
        return WhySoLongPanel(
            job_key=job_key,
            found=False,
            stage=None,
            bottleneck_verdict="unknown",
            bottleneck_why="No live stage update has been published for this job yet.",
            bottleneck_confidence=0.0,
            items_per_second=None,
            eta_seconds=None,
            elapsed_seconds=0.0,
            progress_pct=None,
        )

    now = time.time()
    elapsed = max(0.0, now - stage.started_at_epoch)
    items_per_sec = stage.items_done / elapsed if elapsed > 0 else None
    progress_pct = (
        (stage.items_done / stage.items_total) * 100.0
        if stage.items_total > 0
        else None
    )
    eta_seconds = _estimate_eta(stage, items_per_sec)

    verdict = _safe_analyze_slowness(task_name=job_key)
    chips = _action_chips_for_verdict(verdict.verdict)

    return WhySoLongPanel(
        job_key=job_key,
        found=True,
        stage=stage,
        bottleneck_verdict=verdict.verdict,
        bottleneck_why=verdict.why,
        bottleneck_confidence=verdict.confidence,
        items_per_second=items_per_sec,
        eta_seconds=eta_seconds,
        elapsed_seconds=elapsed,
        progress_pct=progress_pct,
        action_chips=chips,
    )


def _estimate_eta(stage: StageUpdate, items_per_sec: float | None) -> float | None:
    """Return seconds-until-done, or None when the estimate would be noisy."""
    if items_per_sec is None or items_per_sec <= 0:
        return None
    if stage.items_total <= 0:
        return None
    if stage.items_done < _MIN_ITEMS_FOR_ETA:
        return None
    remaining = max(0, stage.items_total - stage.items_done)
    return remaining / items_per_sec


def _safe_analyze_slowness(*, task_name: str):
    """Wrap analyze_slowness so a probe failure doesn't break the panel."""
    try:
        from apps.diagnostics.services.slowness_analyzer import analyze_slowness

        return analyze_slowness(task_name=task_name)
    except Exception:  # noqa: BLE001 — analyzer probe is best-effort; panel still renders the stage info.
        logger.debug("why_so_long: analyze_slowness probe failed", exc_info=True)

        @dataclass(frozen=True)
        class _NeutralVerdict:
            verdict: str = "unknown"
            why: str = "Bottleneck probe unavailable; only stage progress is shown."
            confidence: float = 0.0

        return _NeutralVerdict()


def _action_chips_for_verdict(verdict: str) -> list[dict[str, str]]:
    """Map a bottleneck verdict to one-click action chips for the operator.

    Plain-English: instead of just telling the operator "you're disk-bound",
    we hand them a button that does the right thing — e.g. "Run the Docker
    prune now" for disk pressure. Each chip declares its own POST endpoint
    via the ``action_url`` field.
    """
    chips_by_verdict: dict[str, list[dict[str, str]]] = {
        "cpu_bound": [
            {
                "label": "Pause non-essential workers",
                "action_url": "/api/system/master-pause/",
                "tooltip": "Stops scheduled jobs so the running task gets full CPU.",
            },
        ],
        "gpu_bound": [
            {
                "label": "Reclaim GPU cache",
                "action_url": "/api/diagnostics/gpu-memory-cleanup/",
                "tooltip": "Clears unused VRAM that PyTorch is hoarding.",
            },
        ],
        "disk_bound": [
            {
                "label": "Free Docker disk now",
                "action_url": "/api/prune/safe/",
                "tooltip": "Runs the safe-prune script to reclaim Docker build cache.",
            },
        ],
        "lock_waiting": [
            {
                "label": "View blocking queries",
                "action_url": "/diagnostics?focus=postgres-locks",
                "tooltip": "Shows the Postgres queries currently holding a lock.",
            },
        ],
        "thermal_throttled": [
            {
                "label": "Wait for cooldown",
                "action_url": "",
                "tooltip": "GPU is throttling above 85°C; let it cool before retrying.",
            },
        ],
        "db_bound": [
            {
                "label": "Inspect slow queries",
                "action_url": "/diagnostics?focus=slow-queries",
                "tooltip": "Top recent slow queries from pg_stat_statements.",
            },
        ],
    }
    return chips_by_verdict.get(verdict, [])
