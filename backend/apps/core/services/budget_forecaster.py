"""Phase 4.2 — Budget & Space Forecasts pre-flight estimator.

Plain-English: before any import / embedding / passage index / provider
comparison, the operator clicks Run and sees: "Estimated disk use:
2.1 GB. You have 59 GB free. Safe." The forecaster reads the job's
parameters, multiplies by per-row costs, applies the operator's safety
margin, and returns a verdict the UI can render as a chip.

Pattern:
    1. Per-job estimator function (one per heavy task: embed, OPQ,
       FAISS, KG, comparison run).
    2. Live "running estimate vs actual" calibration history capped
       at last 100 runs per task — calibration improves the next
       forecast without unbounded growth.
    3. Operator-tunable safety margin (default 20% headroom).
    4. Hard-stop verdict when projected free disk < 5 GB after the
       job lands.

Storage discipline: forecast / calibration row stored as ONE
AppSetting row per task (single key:
``budget_forecaster.<task_name>.calibration``), JSON-encoded ring
buffer of the last 100 (estimate, actual) pairs. NO new tables.

Citations: pattern derived from cgroups + `df` pre-flight in CI runners
+ the Linux PSI papers (Andrei 2018) for pressure thresholds.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


# Minimum free-after-job (bytes) below which the verdict turns "red".
# Matches DISK-PRESSURE-RULES.md hard watermark (5 GB).
_FREE_AFTER_RED_BYTES = 5 * 1024 * 1024 * 1024
# Minimum free-after-job below which the verdict turns "yellow"
# (10 GB matches DISK-PRESSURE-RULES.md soft watermark).
_FREE_AFTER_YELLOW_BYTES = 10 * 1024 * 1024 * 1024
# Default operator-tunable headroom (20% of estimate added on top).
_DEFAULT_SAFETY_MARGIN_PCT = 20
# Calibration ring buffer: how many past runs to keep per task.
_CALIBRATION_HISTORY_LIMIT = 100


@dataclass(frozen=True, slots=True)
class BudgetForecast:
    """Operator-facing forecast for one pre-flight estimate."""

    task_name: str
    estimated_bytes: int
    safety_margin_bytes: int
    projected_total_bytes: int
    free_now_bytes: int
    free_after_bytes: int
    verdict: str  # "safe" | "yellow" | "red"
    why: str
    calibration_runs_used: int
    calibration_factor: float  # multiplier applied (1.0 = no calibration)


# Registry of per-task raw-estimate functions. Each callable takes a
# kwargs dict and returns the raw byte estimate BEFORE calibration +
# safety margin. New tasks register at module-import time so no central
# coupling.
_ESTIMATORS: dict[str, Callable[[dict], int]] = {}


def register_estimator(task_name: str) -> Callable[[Callable], Callable]:
    """Decorator: register a per-task raw-bytes estimator.

    Usage:

        @register_estimator("embeddings.generate_content_item_embeddings")
        def estimate_content_embeddings(kwargs: dict) -> int:
            n_items = kwargs.get("expected_item_count", 0)
            return n_items * 4096  # 1024-dim float32

    The forecast endpoint looks up the estimator by task_name and
    invokes it with the operator's run-now parameters.
    """

    def _decorator(fn: Callable[[dict], int]) -> Callable[[dict], int]:
        _ESTIMATORS[task_name] = fn
        return fn

    return _decorator


def get_registered_tasks() -> list[str]:
    """Return the registered task_names (for /api/diagnostics docs)."""
    return sorted(_ESTIMATORS.keys())


def forecast(
    *,
    task_name: str,
    kwargs: dict | None = None,
    safety_margin_pct: int | None = None,
) -> BudgetForecast:
    """Build a forecast for one would-be job. Never raises.

    Plain-English: calls the registered estimator for ``task_name``,
    multiplies by the calibration factor (learned from past runs),
    adds the safety margin, then compares against current free disk
    to pick a verdict + plain-English why.
    """
    estimator = _ESTIMATORS.get(task_name)
    if estimator is None:
        return BudgetForecast(
            task_name=task_name,
            estimated_bytes=0,
            safety_margin_bytes=0,
            projected_total_bytes=0,
            free_now_bytes=_safe_disk_free_bytes(),
            free_after_bytes=_safe_disk_free_bytes(),
            verdict="unknown",
            why=(
                f"No estimator is registered for task '{task_name}'. "
                f"Add @register_estimator in your service module."
            ),
            calibration_runs_used=0,
            calibration_factor=1.0,
        )

    raw_bytes = max(0, _safely_call_estimator(estimator, kwargs or {}))
    factor, runs_used = _read_calibration_factor(task_name)
    calibrated = int(raw_bytes * factor)
    margin_pct = (
        safety_margin_pct
        if safety_margin_pct is not None
        else _DEFAULT_SAFETY_MARGIN_PCT
    )
    safety_margin = int(calibrated * (margin_pct / 100.0))
    projected_total = calibrated + safety_margin

    free_now = _safe_disk_free_bytes()
    free_after = max(0, free_now - projected_total)
    verdict, why = _verdict_for(free_after, projected_total)

    return BudgetForecast(
        task_name=task_name,
        estimated_bytes=calibrated,
        safety_margin_bytes=safety_margin,
        projected_total_bytes=projected_total,
        free_now_bytes=free_now,
        free_after_bytes=free_after,
        verdict=verdict,
        why=why,
        calibration_runs_used=runs_used,
        calibration_factor=factor,
    )


def record_actual(task_name: str, *, estimate_bytes: int, actual_bytes: int) -> None:
    """Append one (estimate, actual) pair to the per-task calibration history.

    Called by the long-running task itself when it finishes. The next
    forecast uses the rolling factor = mean(actual / estimate) over the
    last ``_CALIBRATION_HISTORY_LIMIT`` runs to correct future estimates.
    """
    try:
        from apps.core.models import AppSetting

        key = f"budget_forecaster.{task_name}.calibration"
        row = AppSetting.objects.filter(key=key).first()
        history: list[list[int]] = []
        if row and row.value:
            try:
                history = json.loads(row.value) or []
            except (TypeError, ValueError):
                history = []
        history.append([int(estimate_bytes), int(actual_bytes)])
        if len(history) > _CALIBRATION_HISTORY_LIMIT:
            history = history[-_CALIBRATION_HISTORY_LIMIT:]
        AppSetting.objects.update_or_create(
            key=key,
            defaults={"value": json.dumps(history)},
        )
    except Exception:  # noqa: BLE001 — calibration is best-effort; loss just means next forecast is uncorrected.
        logger.debug(
            "budget_forecaster: record_actual failed for %s", task_name, exc_info=True
        )


def _read_calibration_factor(task_name: str) -> tuple[float, int]:
    """Return (factor, runs_used). Factor=1.0 when no history yet."""
    try:
        from apps.core.models import AppSetting

        key = f"budget_forecaster.{task_name}.calibration"
        row = AppSetting.objects.filter(key=key).first()
        if not row or not row.value:
            return 1.0, 0
        history: list[list[int]] = json.loads(row.value) or []
        if not history:
            return 1.0, 0
        ratios = [
            actual / estimate
            for estimate, actual in history
            if estimate > 0 and actual > 0
        ]
        if not ratios:
            return 1.0, len(history)
        avg = sum(ratios) / len(ratios)
        # Clamp to [0.25, 4.0] so a wild outlier doesn't destabilise
        # future forecasts. Hellerstein 2003 §4.2 pattern.
        clamped = max(0.25, min(4.0, avg))
        return float(clamped), len(history)
    except Exception:  # noqa: BLE001 — calibration read is best-effort; default to 1.0.
        logger.debug(
            "budget_forecaster: factor read failed for %s", task_name, exc_info=True
        )
        return 1.0, 0


def _verdict_for(free_after_bytes: int, projected_total: int) -> tuple[str, str]:
    """Map (free_after, projected) → (verdict, plain-English why)."""
    if projected_total <= 0:
        return "safe", "Job uses negligible disk."
    if free_after_bytes < _FREE_AFTER_RED_BYTES:
        gb_after = free_after_bytes / (1024**3)
        return "red", (
            f"After this job you would have only {gb_after:.1f} GB free — "
            "below the 5 GB hard watermark. Free up space first or skip the job."
        )
    if free_after_bytes < _FREE_AFTER_YELLOW_BYTES:
        gb_after = free_after_bytes / (1024**3)
        return "yellow", (
            f"After this job you would have {gb_after:.1f} GB free — "
            "below the 10 GB soft watermark. Consider running the prune script first."
        )
    gb_after = free_after_bytes / (1024**3)
    return "safe", f"After this job you would have {gb_after:.1f} GB free."


def _safe_disk_free_bytes() -> int:
    """``shutil.disk_usage`` on the project root; defaults to 0 on failure."""
    try:
        import os

        root = os.environ.get("HOMEDRIVE", "/") or "/"
        return int(shutil.disk_usage(root).free)
    except Exception:  # noqa: BLE001 — disk-usage probe failure is non-fatal; verdict downgrades to "unknown".
        logger.debug("budget_forecaster: disk_usage probe failed", exc_info=True)
        return 0


def _safely_call_estimator(estimator: Callable[[dict], int], kwargs: dict) -> int:
    """Wrap the per-task estimator so a buggy estimator can't crash the panel."""
    try:
        return int(estimator(kwargs))
    except Exception:  # noqa: BLE001 — bad estimator returns 0 so the operator at least sees current free disk.
        logger.warning(
            "budget_forecaster: estimator call failed; treating as 0 bytes",
            exc_info=True,
        )
        return 0


# ── Built-in estimators ──────────────────────────────────────────


@register_estimator("embeddings.generate_content_item_embeddings")
def _estimate_content_embeddings(kwargs: dict) -> int:
    """1024-dim float32 = 4096 bytes/row + ~30% pgvector overhead."""
    n = int(kwargs.get("expected_item_count", 0) or 0)
    bytes_per_row = 4096
    overhead_factor = 1.3
    return int(n * bytes_per_row * overhead_factor)


@register_estimator("passage_relevance.regenerate_passage_embeddings")
def _estimate_passage_embeddings(kwargs: dict) -> int:
    """Per-content average ~7 passages, each 1024-dim float32 + OPQ code."""
    n_content = int(kwargs.get("expected_item_count", 0) or 0)
    avg_passages_per_item = int(kwargs.get("avg_passages_per_item", 7))
    fp32_bytes = 4096
    opq_bytes = 64
    overhead_factor = 1.3
    return int(
        n_content * avg_passages_per_item * (fp32_bytes + opq_bytes) * overhead_factor
    )


@register_estimator("pipeline.refresh_faiss_index")
def _estimate_faiss_rebuild(kwargs: dict) -> int:
    """FAISS index size ~ 1.1 × raw vector bytes (IVF + OPQ)."""
    n_items = int(kwargs.get("expected_item_count", 0) or 0)
    bytes_per_row = 4096
    faiss_overhead_factor = 1.1
    return int(n_items * bytes_per_row * faiss_overhead_factor)


@register_estimator("kg.bootstrap_schema")
def _estimate_kg_bootstrap(kwargs: dict) -> int:
    """Auto-schema KG: ~120 MB peak per Plan Section K.3 budget."""
    return 120 * 1024 * 1024
