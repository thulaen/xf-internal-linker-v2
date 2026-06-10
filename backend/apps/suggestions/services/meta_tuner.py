"""FR-018b — Meta-algorithm autotuner.

Companion to ``WeightTuner`` (FR-018) that adjusts the *meta-algorithm
parameters* — RRF k, BM25 k1/b, MMR lambda, similarity caps, top-K
knobs — instead of the four ranking-blend weights.

Key differences from WeightTuner
--------------------------------
- **No simplex constraint.** Meta parameters are independent (RRF k
  doesn't have to sum with anything); the optimisation is bound-
  constrained per-key, not constrained-to-sum-to-1.
- **Per-key bounds with explicit floors.** Every lower bound is
  positive and >= a per-key floor — per ``DEFAULT-ON-RULE.md`` the
  tuner cannot disable a meta-algorithm by zeroing its parameter.
- **Drift-limited per run.** Same ±5% drift rule as WeightTuner so a
  single monthly tuning can't move a knob from 60 → 200 in one go.
- **Same challenger escrow + SPRT gate + rollback watchdog.** Wires
  through the same ``RankingChallenger`` model with ``kind="meta_algorithm"``
  so the audit trail is distinct.

References
----------
- BM25 — Robertson & Zaragoza (2009), F&T in IR 3(4) §3.5 (k1, b ranges).
- RRF — Cormack et al. (2009) SIGIR'09 §3 (k = 60 default; range 20–200).
- MMR — Carbonell & Goldstein (1998) SIGIR §3 (lambda 0–1).
- Drift bound (±5%) — same constant as FR-018 (per docs/specs/fr018-auto-tuned-ranking-weights.md).
"""

from __future__ import annotations

import logging
from typing import Mapping

import numpy as np

from apps.suggestions.weight_preset_service import get_current_weights

logger = logging.getLogger(__name__)

# Per-run drift cap (±5%). Same risk profile as WeightTuner.
_META_DRIFT_PCT = 0.05

# Per-key bounds + excluded keys are now sourced from the canonical
# tunable registry at `apps.suggestions.tunable_registry`. Adding a new
# meta-algo parameter is a single edit there — this file picks it up
# automatically per docs/AUTOTUNER-FUTURE-AWARENESS.md.
from apps.suggestions.tunable_registry import (  # noqa: E402
    META_PARAMS_EXCLUDED as _AUTOTUNER_EXCLUDED,
    get_meta_param_bounds,
)


def _bounds() -> dict[str, tuple[float, float]]:
    """Lazy accessor so the registry can be reloaded in tests."""
    return get_meta_param_bounds()


# Backwards-compatible alias kept for callers that grep this name.
# Equivalent to `_bounds()` — the dict is rebuilt each call to honour
# any test-time monkeypatching of the registry.
_META_PARAM_BOUNDS = _bounds()


def get_tunable_meta_keys() -> list[str]:
    """Return the keys this tuner is allowed to adjust."""
    return sorted(_META_PARAM_BOUNDS.keys())


def get_excluded_meta_keys() -> dict[str, str]:
    """Return the keys this tuner deliberately does NOT adjust + reasons."""
    return dict(_AUTOTUNER_EXCLUDED)


def _propose_one_key(
    key: str,
    lo: float,
    hi: float,
    current_values: Mapping[str, str | float],
    rng: np.random.Generator,
) -> float | None:
    """Build one candidate value for *key*, or return ``None`` to skip.

    Returns ``None`` when:
    - the key is in ``_AUTOTUNER_EXCLUDED``
    - no current value is available
    - the current value can't be parsed as a number
    """
    if key in _AUTOTUNER_EXCLUDED:
        return None
    raw = current_values.get(key)
    if raw is None:
        return None
    try:
        current = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "meta_tuner: cannot parse current value for %s = %r — skipping",
            key,
            raw,
        )
        return None
    drift = float(rng.uniform(-_META_DRIFT_PCT, _META_DRIFT_PCT))
    candidate = float(np.clip(current * (1.0 + drift), lo, hi))
    # DEFAULT-ON-RULE invariant: never zero a parameter.
    if candidate <= 0.0:  # pragma: no cover — bounds are >0, defensive
        candidate = lo
    return candidate


def propose_meta_parameter_drift(
    current_values: Mapping[str, str | float] | None = None,
    *,
    rng: np.random.Generator | None = None,
) -> dict[str, float]:
    """Return a candidate dict of nudged meta-parameters.

    Strategy: for each tunable key, propose ``current * (1 + drift)``
    where drift ~ Uniform(−5%, +5%). Clamp to per-key bounds. Floor
    all values away from zero per DEFAULT-ON-RULE.md.

    The per-key proposal logic lives in :func:`_propose_one_key`; this
    function just walks ``_META_PARAM_BOUNDS`` and collects results.
    """
    if current_values is None:
        current_values = get_current_weights()
    if rng is None:
        rng = np.random.default_rng()

    proposed: dict[str, float] = {}
    for key, (lo, hi) in _META_PARAM_BOUNDS.items():
        candidate = _propose_one_key(key, lo, hi, current_values, rng)
        if candidate is not None:
            proposed[key] = candidate
    return proposed


def _optuna_candidate_window(
    current: float, lo: float, hi: float
) -> tuple[float, float]:
    """Per-key sampling window: the drift band, clamped to registry bounds.

    The candidate may move at most ±``_META_DRIFT_PCT`` from the current
    value (same risk profile as the random-drift V1) and never leaves the
    registry's ``[lo, hi]``. Returns ``(window_lo, window_hi)``.
    """
    window_lo = max(lo, current * (1.0 - _META_DRIFT_PCT))
    window_hi = min(hi, current * (1.0 + _META_DRIFT_PCT))
    if window_hi < window_lo:  # current already outside bounds — snap in.
        window_lo = window_hi = float(np.clip(current, lo, hi))
    return window_lo, window_hi


def propose_meta_parameters_optuna(
    current_values: Mapping[str, str | float] | None = None,
    *,
    n_trials: int = 16,
    seed: int | None = None,
) -> dict[str, float]:
    """Phase 7 — Optuna-driven candidate meta-parameter profile.

    Replaces the blind random-drift V1: an in-memory Optuna study samples
    one candidate per tunable registry key from a per-key window (the
    ±drift band clamped to the registry's ``[lo, hi]``). The registry is
    the single source of tunables, so a newly-registered key is sampled
    automatically with NO change to this function — the Phase 7 guarantee.

    §F boundary: this is offline ``ranking_train`` work. It returns a
    candidate dict the caller wraps in a ``RankingChallenger`` for the
    SPRT approval workflow; it NEVER activates, promotes, or writes the
    live preset. Activation stays gated by Rust governance + GUI approval.

    Determinism: pass ``seed`` for a reproducible draw (tests do). With no
    online objective at this layer, the study explores the drift window;
    the downstream SPRT evaluator decides whether the candidate ships.
    """
    import optuna

    if current_values is None:
        current_values = get_current_weights()

    bounds = _bounds()
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    proposed: dict[str, float] = {}

    def objective(trial: "optuna.trial.Trial") -> float:
        # Sample one value per eligible key inside its drift window. The
        # objective is constant (no online signal here) — the study's job
        # is to PROPOSE a registry-bounded candidate, not to score it.
        for key, (lo, hi) in bounds.items():
            if key in _AUTOTUNER_EXCLUDED:
                continue
            raw = current_values.get(key)
            if raw is None:
                continue
            try:
                current = float(raw)
            except (TypeError, ValueError):
                logger.warning(
                    "meta_tuner(optuna): cannot parse current value for %s = %r — skipping",
                    key,
                    raw,
                )
                continue
            window_lo, window_hi = _optuna_candidate_window(current, lo, hi)
            value = trial.suggest_float(key, window_lo, window_hi)
            # DEFAULT-ON-RULE invariant: never zero a parameter.
            if value <= 0.0:  # pragma: no cover — bounds are >0, defensive
                value = lo
            proposed[key] = value
        return 0.0

    # Silence Optuna's per-trial INFO chatter for this short in-memory study.
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(objective, n_trials=max(1, n_trials), show_progress_bar=False)

    # Return the best trial's params (keyed by registry key), re-clamped
    # defensively to registry bounds.
    best = dict(study.best_params)
    result: dict[str, float] = {}
    for key, value in best.items():
        lo, hi = bounds[key]
        result[key] = float(np.clip(value, lo, hi))
    return result


class MetaAlgorithmTuner:
    """Optuna-driven tuner that builds a candidate meta-parameter set.

    Phase 7 replaced the blind random-drift V1 with an Optuna-driven
    proposal sampled from the canonical tunable registry
    (:func:`propose_meta_parameters_optuna`). The registry is the single
    source of tunables, so a newly-registered meta-parameter is proposed
    automatically with no change to this class.

    The tuner does NOT write AppSetting directly — it produces a candidate
    dict that the caller (the Celery task) wraps in a ``RankingChallenger``
    row with ``kind="meta_algorithm"``. Activation of any candidate stays
    gated by the existing SPRT challenger evaluator + GSC rollback
    watchdog, and ultimately by Rust governance + GUI approval (§F). The
    tuner only PROPOSES; it never promotes.
    """

    def propose(self) -> dict[str, float]:
        """Build one candidate meta-parameter dict via the Optuna path."""
        return propose_meta_parameters_optuna()

    def explain_excluded(self) -> dict[str, str]:
        """Return the keys this tuner deliberately doesn't touch + reasons."""
        return get_excluded_meta_keys()
