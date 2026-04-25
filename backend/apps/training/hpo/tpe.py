"""TPE (Tree-structured Parzen Estimator) — pick #42.

Reference
---------
Bergstra, J., Bardenet, R., Bengio, Y., & Kégl, B. (2011).
"Algorithms for Hyper-Parameter Optimization." *NeurIPS 2011*,
pp. 2546-2554.

TPE is a Bayesian hyperparameter optimiser that builds two density
estimates over the parameter space — one for "good" trials, one
for "bad" — and samples next from the ratio of those two densities.
It outperforms grid search and random search on most ML tuning
problems while staying simpler than Gaussian-process Bayesian opt.

This wraps Optuna's :class:`TPESampler` so callers don't need to
construct a Study + objective manually for every tuning task.
Optuna is already pinned in requirements.txt — no new pip dep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

try:
    import optuna  # noqa: F401
    from optuna.samplers import TPESampler as _TPESampler

    HAS_OPTUNA = True
except ImportError:  # pragma: no cover — depends on pip env
    _TPESampler = None  # type: ignore[assignment]
    HAS_OPTUNA = False


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TpeResult:
    """Outcome of a TPE run — best params + best objective value."""

    best_params: dict[str, Any]
    best_value: float
    n_trials: int


def is_available() -> bool:
    """True when ``optuna`` is importable."""
    return HAS_OPTUNA


def run_tpe(
    objective: Callable[[Any], float],
    *,
    n_trials: int = 50,
    direction: str = "maximize",
    seed: int | None = None,
) -> TpeResult | None:
    """Run a TPE study with *n_trials*.

    *objective* takes an Optuna :class:`Trial` and returns a scalar
    value to maximise (or minimise — set *direction* accordingly).

    Returns ``None`` when Optuna isn't installed (cold-start safe).
    Real-data ready: install optuna and the call returns a real
    result with no other code change.
    """
    if not HAS_OPTUNA:
        logger.info("apps.training.hpo.tpe: optuna not installed")
        return None
    import optuna as _optuna

    sampler = _TPESampler(seed=seed) if seed is not None else _TPESampler()
    study = _optuna.create_study(direction=direction, sampler=sampler)
    try:
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    except Exception as exc:
        logger.warning("apps.training.hpo.tpe: optimize failed: %s", exc)
        return None
    return TpeResult(
        best_params=dict(study.best_params),
        best_value=float(study.best_value),
        n_trials=int(len(study.trials)),
    )
