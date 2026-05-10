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


class MetaAlgorithmTuner:
    """Lightweight tuner that builds a candidate meta-parameter set.

    V1 strategy is deliberately conservative — propose a small drift,
    let the existing SPRT challenger evaluator + GSC rollback watchdog
    decide whether to keep it. Future versions can add Bayesian
    optimisation on the per-key (lo, hi) box.

    The tuner does NOT write AppSetting directly — it produces a
    candidate dict that the caller (the Celery task) wraps in a
    ``RankingChallenger`` row with ``kind="meta_algorithm"``.
    """

    def propose(self) -> dict[str, float]:
        """Build one candidate meta-parameter dict."""
        return propose_meta_parameter_drift()

    def explain_excluded(self) -> dict[str, str]:
        """Return the keys this tuner deliberately doesn't touch + reasons."""
        return get_excluded_meta_keys()
