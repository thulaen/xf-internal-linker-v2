"""Option B safety rails — the three guard-rails that make fully-automatic
meta-HPO safe.

Rail 1 — **NDCG improvement gate.** Only auto-apply if the best-trial
         NDCG@10 is at least ``NDCG_IMPROVEMENT_MIN`` above the NDCG
         of the currently-applied preset. Default 0.01 (1 pp).

Rail 2 — **Param-change clamp.** No single parameter may change by
         more than ``MAX_PARAM_CHANGE_FRACTION`` (default 0.25 = 25%)
         per weekly apply. Prevents a noisy run from yanking a
         hyperparameter wildly.

Rail 3 — **Rollback watchdog.** After an auto-apply, the daily
         ``meta_hpo_rollback_watchdog`` job compares observed CTR
         over the trailing 24 h to the 7-day pre-apply baseline. If
         CTR drops by more than ``ROLLBACK_CTR_DROP_THRESHOLD``
         (default 0.05 = 5 %), revert to the prior preset snapshot.
         A ``regression`` alert is raised so operators see it on the
         dashboard.

Snapshot storage
----------------
Each auto-apply writes two AppSetting rows:

- ``meta_hpo.applied_snapshot``: JSON of the params that just shipped.
- ``meta_hpo.previous_snapshot``: JSON of the params that shipped
                                  before this one (enables rollback).

These let the watchdog revert without needing a migration per apply.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


#: Minimum NDCG@10 improvement (absolute, e.g. 0.01 = 1pp). Below
#: this the study is treated as "no meaningful improvement" and the
#: auto-apply is skipped — the existing preset stays in force.
NDCG_IMPROVEMENT_MIN: float = 0.01

#: Maximum per-param change as a fraction of the current value.
#: 0.25 = 25 %. Applied after clip bounds — a proposed change that's
#: within spec bounds but too big relative to current gets halfway-clamped
#: so the preset drifts gradually.
MAX_PARAM_CHANGE_FRACTION: float = 0.25

#: CTR drop threshold that triggers automatic rollback. 0.05 = 5 %.
ROLLBACK_CTR_DROP_THRESHOLD: float = 0.05

#: Baseline window (days) for the pre-apply CTR comparison.
ROLLBACK_BASELINE_DAYS: int = 7

#: Observation window (hours) for the post-apply CTR comparison.
ROLLBACK_OBSERVATION_HOURS: int = 24


@dataclass(frozen=True)
class ImprovementGateResult:
    """Outcome of :func:`passes_improvement_gate`."""

    passes: bool
    best_ndcg: float
    baseline_ndcg: float
    delta: float
    reason: str


@dataclass(frozen=True)
class RollbackDecision:
    """Outcome of :func:`should_rollback`."""

    rollback: bool
    baseline_ctr: float
    observed_ctr: float
    drop: float
    reason: str


def passes_improvement_gate(
    *,
    best_ndcg: float,
    baseline_ndcg: float,
    min_improvement: float = NDCG_IMPROVEMENT_MIN,
) -> ImprovementGateResult:
    """Rail 1 — is the best trial actually better than what's live?

    Returns a structured result so the auto-apply job can log the
    exact delta in the History tab.
    """
    delta = best_ndcg - baseline_ndcg
    passes = delta >= min_improvement
    reason = (
        f"ndcg_improved_by_{delta:.4f}"
        if passes
        else f"ndcg_delta_{delta:.4f}_below_threshold_{min_improvement:.4f}"
    )
    return ImprovementGateResult(
        passes=passes,
        best_ndcg=best_ndcg,
        baseline_ndcg=baseline_ndcg,
        delta=delta,
        reason=reason,
    )


def clamp_param_change(
    *,
    key: str,
    current_value: float,
    proposed_value: float,
    max_change_fraction: float = MAX_PARAM_CHANGE_FRACTION,
) -> float:
    """Rail 2 — limit how far a single value can move in one apply.

    If the proposed change exceeds ``max_change_fraction`` of the
    current value's magnitude, move half-way instead of the full step.
    For categorical params (where fractional clamping doesn't apply)
    pass through unchanged — callers filter those out beforehand.
    """
    if current_value == 0:
        # Zero baseline — any non-zero proposal is "infinite" change.
        # Allow the move but log so operators notice if this becomes
        # common.
        logger.info(
            "clamp_param_change(%s): current is zero, allowing proposed=%s",
            key,
            proposed_value,
        )
        return proposed_value

    change = abs(proposed_value - current_value)
    max_abs_change = abs(current_value) * max_change_fraction
    if change <= max_abs_change:
        return proposed_value
    # Halfway clamp — bigger than the cap gets pulled back to current + cap.
    direction = 1.0 if proposed_value > current_value else -1.0
    clamped = current_value + direction * max_abs_change
    logger.info(
        "clamp_param_change(%s): proposed=%s exceeds cap; clamped to %s",
        key,
        proposed_value,
        clamped,
    )
    return clamped


def persist_snapshot_for_rollback(params: dict[str, Any]) -> None:
    """Move the existing snapshot to ``previous_snapshot`` then write the new one.

    Called after a successful auto-apply so the watchdog can revert.
    """
    from apps.core.models import AppSetting

    current_snapshot = (
        AppSetting.objects.filter(key="meta_hpo.applied_snapshot")
        .values_list("value", flat=True)
        .first()
        or "{}"
    )
    AppSetting.objects.update_or_create(
        key="meta_hpo.previous_snapshot",
        defaults={
            "value": current_snapshot,
            "description": "Last-applied meta-HPO snapshot — restored on rollback.",
        },
    )
    AppSetting.objects.update_or_create(
        key="meta_hpo.applied_snapshot",
        defaults={
            "value": json.dumps(params),
            "description": "Currently-applied meta-HPO snapshot.",
        },
    )
    AppSetting.objects.update_or_create(
        key="meta_hpo.applied_at",
        defaults={
            "value": timezone.now().isoformat(),
            "description": "Timestamp of the last auto-applied meta-HPO result.",
        },
    )


def should_rollback(
    *,
    baseline_ctr: float,
    observed_ctr: float,
    drop_threshold: float = ROLLBACK_CTR_DROP_THRESHOLD,
) -> RollbackDecision:
    """Rail 3 — has CTR dropped materially since the last apply?"""
    if baseline_ctr <= 0:
        return RollbackDecision(
            rollback=False,
            baseline_ctr=baseline_ctr,
            observed_ctr=observed_ctr,
            drop=0.0,
            reason="no_baseline_ctr_data",
        )
    drop = (baseline_ctr - observed_ctr) / baseline_ctr
    should = drop >= drop_threshold
    reason = (
        f"ctr_drop_{drop:.4f}_exceeds_threshold_{drop_threshold:.4f}"
        if should
        else f"ctr_stable_drop_{drop:.4f}_under_threshold"
    )
    return RollbackDecision(
        rollback=should,
        baseline_ctr=baseline_ctr,
        observed_ctr=observed_ctr,
        drop=drop,
        reason=reason,
    )


def restore_previous_snapshot() -> dict[str, Any]:
    """Swap ``applied_snapshot`` back to ``previous_snapshot``.

    Returns the restored params dict. Called by the rollback watchdog
    when :func:`should_rollback` fires.
    """
    from apps.core.models import AppSetting

    previous = (
        AppSetting.objects.filter(key="meta_hpo.previous_snapshot")
        .values_list("value", flat=True)
        .first()
        or "{}"
    )
    previous_params = json.loads(previous or "{}")
    AppSetting.objects.update_or_create(
        key="meta_hpo.applied_snapshot",
        defaults={
            "value": previous,
            "description": "Rolled back to previous snapshot after CTR regression.",
        },
    )
    AppSetting.objects.update_or_create(
        key="meta_hpo.rolled_back_at",
        defaults={
            "value": timezone.now().isoformat(),
            "description": "Timestamp of the last rollback.",
        },
    )
    return previous_params
