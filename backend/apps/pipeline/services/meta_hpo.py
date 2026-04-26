"""Option B meta-hyperparameter HPO — Bergstra TPE via Optuna (pick #42).

Orchestrates the weekly fully-automatic study:

1. Create / load an Optuna study (SQLite storage, persists across
   laptop restarts so weeks of trial history survive).
2. Baseline NDCG@10 on the current reservoir with the live preset.
3. Run up to ``N_TRIALS`` trials with TPE sampler + MedianPruner.
4. Safety-rail check on the best trial:
   - NDCG improvement gate.
   - Per-param change clamp.
5. If rails pass, persist the new snapshot (with rollback info) and
   write the clipped + clamped params back to ``AppSetting``.
6. Return a :class:`StudyOutcome` so the scheduled job can log it.

A separate daily ``meta_hpo_rollback_watchdog`` job reads
``meta_hpo.applied_snapshot`` + observed CTR and rolls back if the
third safety rail trips.

Design principle: every write here is idempotent against study-crash
mid-run. If the process dies after step 5 but before step 6, the next
run sees the new snapshot and proceeds — no duplicated writes, no
state corruption.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import optuna
from optuna.trial import Trial

from .meta_hpo_eval import evaluate_ndcg_at_k, load_reservoir_items
from .meta_hpo_safety import (
    NDCG_IMPROVEMENT_MIN,
    ImprovementGateResult,
    clamp_param_change,
    passes_improvement_gate,
    persist_snapshot_for_rollback,
)
from .meta_hpo_search_spaces import (
    DEFAULT_N_TRIALS,
    DEFAULT_STORAGE_URL,
    SEARCH_SPACE,
    clip_params,
    make_pruner,
    make_sampler,
    sample_params,
)

logger = logging.getLogger(__name__)


#: Default study name. Single long-running study so TPE's model keeps
#: improving over time. Operators starting a "clean slate" study
#: (e.g. after a major corpus shift) can pass a different name.
DEFAULT_STUDY_NAME: str = "meta_hpo_fully_automatic"


@dataclass(frozen=True)
class StudyOutcome:
    """Summary returned by :func:`run_study_and_maybe_apply`.

    Structured so the scheduled-job message line renders a crisp
    "study ran; best NDCG=X; applied=Y" summary for operators.
    """

    applied: bool
    best_ndcg: float
    baseline_ndcg: float
    n_trials: int
    gate: ImprovementGateResult | None
    applied_params: dict[str, Any]
    study_name: str


def ensure_storage_dir(storage_url: str) -> None:
    """Create the SQLite dir for the study file if needed."""
    if not storage_url.startswith("sqlite:///"):
        return
    path = storage_url[len("sqlite:///") :]
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _current_appsetting_value(key: str) -> str | None:
    from apps.core.models import AppSetting

    return AppSetting.objects.filter(key=key).values_list("value", flat=True).first()


def _current_snapshot() -> dict[str, Any]:
    """Return the previously-applied snapshot from AppSetting (empty if none)."""
    raw = _current_appsetting_value("meta_hpo.applied_snapshot") or "{}"
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {}


def _apply_snapshot(clipped: dict[str, Any]) -> None:
    """Write every key in *clipped* back into AppSetting using its entry's serialiser."""
    from apps.core.models import AppSetting

    for entry in SEARCH_SPACE:
        key = entry.app_setting_key
        if key not in clipped:
            continue
        value = entry.to_appsetting(clipped[key])
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "description": (
                    f"meta_hpo: auto-applied (pick #{entry.pick_number}) "
                    f"— see AppSetting[meta_hpo.applied_snapshot] for full run."
                ),
            },
        )


def build_objective(cached_items=None):
    """Return a new Optuna objective bound to the current reservoir.

    We cache reservoir items once per study run so all 200 trials
    share the same eval set — eliminates sampling-noise as a source
    of trial-to-trial NDCG variation.
    """
    items = cached_items if cached_items is not None else load_reservoir_items()

    def objective(trial: Trial) -> float:
        params = sample_params(trial)
        return evaluate_ndcg_at_k(params, items=items)

    return objective


def run_study_and_maybe_apply(
    *,
    n_trials: int = DEFAULT_N_TRIALS,
    study_name: str = DEFAULT_STUDY_NAME,
    storage_url: str = DEFAULT_STORAGE_URL,
    timeout_seconds: int | None = None,
    checkpoint=None,
) -> StudyOutcome:
    """Main entrypoint — run the weekly study + apply if safety rails pass.

    Invoked by the ``meta_hyperparameter_hpo`` scheduled job.
    """
    ensure_storage_dir(storage_url)
    if checkpoint:
        checkpoint(progress_pct=0.0, message="Loading reservoir eval set")

    items = load_reservoir_items()
    # Baseline NDCG on the current live preset. Without eval data we
    # can't improve on anything, so short-circuit to "did nothing".
    if not items:
        if checkpoint:
            checkpoint(
                progress_pct=100.0,
                message="Reservoir empty — skipping study",
            )
        return StudyOutcome(
            applied=False,
            best_ndcg=0.0,
            baseline_ndcg=0.0,
            n_trials=0,
            gate=None,
            applied_params={},
            study_name=study_name,
        )

    baseline_params = _current_snapshot()
    baseline_ndcg = evaluate_ndcg_at_k(baseline_params, items=items)

    if checkpoint:
        checkpoint(
            progress_pct=10.0,
            message=f"Baseline NDCG@10={baseline_ndcg:.4f}; starting TPE study",
        )

    study = optuna.create_study(
        study_name=study_name,
        storage=storage_url,
        direction="maximize",
        sampler=make_sampler(),
        pruner=make_pruner(),
        load_if_exists=True,
    )

    objective = build_objective(cached_items=items)

    if checkpoint:

        def _optuna_heartbeat(study, trial):
            # Report progress every 10 % of trials so dashboards have
            # something live to render.
            pct = 10.0 + 80.0 * trial.number / max(n_trials, 1)
            checkpoint(
                progress_pct=min(pct, 90.0),
                message=f"Trial {trial.number + 1}/{n_trials} complete",
            )

        callbacks = [_optuna_heartbeat]
    else:
        callbacks = None

    study.optimize(
        objective,
        n_trials=n_trials,
        timeout=timeout_seconds,
        callbacks=callbacks,
        show_progress_bar=False,
    )

    best_ndcg = float(study.best_value)
    best_params = dict(study.best_params)

    if checkpoint:
        checkpoint(
            progress_pct=92.0,
            message=(
                f"Study done — best NDCG@10={best_ndcg:.4f} vs baseline {baseline_ndcg:.4f}"
            ),
        )

    gate = passes_improvement_gate(
        best_ndcg=best_ndcg,
        baseline_ndcg=baseline_ndcg,
        min_improvement=NDCG_IMPROVEMENT_MIN,
    )
    if not gate.passes:
        logger.info("meta_hpo: improvement gate blocked apply (%s)", gate.reason)
        if checkpoint:
            checkpoint(
                progress_pct=100.0,
                message=f"Gate blocked apply: {gate.reason}",
            )
        return StudyOutcome(
            applied=False,
            best_ndcg=best_ndcg,
            baseline_ndcg=baseline_ndcg,
            n_trials=n_trials,
            gate=gate,
            applied_params={},
            study_name=study_name,
        )

    # Rail 2 — clip then clamp per-param change vs baseline.
    clipped = clip_params(best_params)
    clamped: dict[str, Any] = {}
    for key, proposed in clipped.items():
        current = baseline_params.get(key)
        if isinstance(proposed, (int, float)) and isinstance(current, (int, float)):
            clamped[key] = clamp_param_change(
                key=key,
                current_value=float(current),
                proposed_value=float(proposed),
            )
        else:
            # Categorical or no prior baseline — pass through.
            clamped[key] = proposed

    if checkpoint:
        checkpoint(progress_pct=95.0, message="Writing snapshot + AppSetting")

    persist_snapshot_for_rollback(clamped)
    _apply_snapshot(clamped)

    if checkpoint:
        checkpoint(
            progress_pct=100.0,
            message=f"Auto-applied ({len(clamped)} params, Δ={gate.delta:.4f})",
        )

    logger.info(
        "meta_hpo: auto-applied new preset — NDCG %.4f → %.4f (Δ%.4f), "
        "%d params updated",
        baseline_ndcg,
        best_ndcg,
        gate.delta,
        len(clamped),
    )

    return StudyOutcome(
        applied=True,
        best_ndcg=best_ndcg,
        baseline_ndcg=baseline_ndcg,
        n_trials=n_trials,
        gate=gate,
        applied_params=clamped,
        study_name=study_name,
    )
